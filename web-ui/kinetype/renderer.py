"""The renderer: deterministic per-frame compositing plus the ffmpeg pipe.

The whole "quick-flash waterfall typography" look comes from four stacked
mechanisms, all re-implemented here from scratch:

1. **Grid advance** – every beat is parked at ``anchor_y``; the beats above it are
   pushed up by the sum of the heights below, so the stack grows and slides.
2. **Second-order motion** – the stack never jumps to its new position.  Each frame
   it eats a fraction of the remaining distance (``motion.scroll`` +
   ``motion.scroll_ease``), which is what produces the springy, water-like crawl the
   format is named after.
3. **Entrance / exit choreography** – pop / rise / drop / zoom / swing / typewriter
   in; shrink / fade / drift / crumble out.  The style is picked per beat, so no two
   flashes travel the same path.
4. **Camera** – slow breathe zoom, shockwave shake on emphasised beats and speed
   lines while the stack is scrolling fast.  This is the layer people usually
   mistake for "AE magic": it is just a transform on the composited stack.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from . import background as bg
from .config import RenderConfig, parse_color, rgb
from .fonts import FontSet
from .layout import Block, LayoutEngine
from .script import Chunk
from .util import (
    Rng,
    clamp,
    cushion,
    ease_in_cubic,
    ease_out_back,
    ease_out_cubic,
    ease_out_elastic,
    ease_out_expo,
    lerp,
    smoothstep,
)

OVERLAY_SCALE = 0.5


@dataclass
class Program:
    """Everything the renderer needs to know for one video."""

    chunks: list[Chunk]
    blocks: list[Block]
    duration: float
    events: list[float] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    speed: float = 1.0


class StackMotion:
    """Waterfall stack geometry.

    The stack is described **relative to the newest beat**, which is the one thing
    that never moves: it sits on the anchor and every older beat is pushed above it
    by the heights of the beats in between::

        y(i) = anchor - Σ heights(i+1 .. newest)

    That formulation is what keeps the stack bounded – a global "distance travelled"
    counter grows without limit and eventually scrolls the whole stack off the top of
    the frame.  Here older beats simply climb past the top and their sprites are
    clipped away.

    Motion: a beat *earns* its slot over ``scroll`` seconds, so at the instant it
    lands its contribution is zero (it sits exactly on the anchor) and it rises by
    its own height while the beats above glide away.  Easing a bounded, monotonically
    growing quantity keeps the whole curve monotone, which is what reads as water
    flowing rather than a slideshow.
    """

    def __init__(self, height_of, tops: list[float], scroll: float, ease: float) -> None:
        #: per-beat arrival times, ascending
        self.tops = list(tops)
        #: per-beat frozen heights, ascending
        self.heights = [float(height_of(i)) for i in range(len(self.tops))]
        self.scroll = max(1e-3, scroll)
        self.ease = ease

    def ramp(self, t: float) -> float:
        """Fraction (0..1) of the incoming beat's rise that has already happened."""
        newest = self.newest_index(t)
        if newest < 0:
            return 1.0
        return cushion((t - self.tops[newest]) / self.scroll, self.ease)

    def newest_index(self, t: float) -> int:
        newest = -1
        for i, top in enumerate(self.tops):
            if top <= t + 1e-9:
                newest = i
            else:
                break
        return newest

    def _carry(self, index: int, t: float) -> float:
        """Eased number of slots the stack has travelled since ``index`` landed."""
        newest = self.newest_index(t)
        value = 0.0
        for j in range(index + 1, newest + 1):
            value += cushion((t - self.tops[j]) / self.scroll, self.ease)
        return value

    def carry(self, index: int, t: float) -> float:
        """Slots the beat at ``index`` has climbed above the anchor."""
        return self._carry(max(0, index), t)

    def height(self, index: int) -> float:
        return self.heights[index]


# --------------------------------------------------------------------------- #


class Renderer:
    def __init__(self, cfg: RenderConfig, seed: int | None = None) -> None:
        self.cfg = cfg
        self.seed = int(cfg.seed if seed is None else seed)
        self.rng = Rng(self.seed)
        self.size = (int(cfg.output.width), int(cfg.output.height))
        self.fonts = FontSet(cfg.font)
        self.fonts.require()
        self.layout = LayoutEngine(cfg, self.fonts, self.seed)
        self.base_bg = bg.build_background(cfg.background, self.size, self.seed)
        self.scale = OVERLAY_SCALE
        self._ow = int(self.size[0] * self.scale) + 2
        self._oh = int(self.size[1] * self.scale) + 2
        self._tint_cache: dict[tuple[int, int, int], Image.Image] = {}
        self._base_cache: Image.Image | None = None
        self._sprite_cache: dict[tuple[int, int, int, int], Image.Image] = {}
        self._motion_cache: tuple[Program, StackMotion] | None = None
        self.program: Program | None = None
        self.timings: dict[str, float] = {}

    # -- preparation -------------------------------------------------------- #
    def prepare(
        self,
        chunks: list[Chunk],
        duration: float,
        audio_events: list[float] | None = None,
    ) -> Program:
        if not chunks:
            raise ValueError("nothing to render – the script produced zero beats")
        events = sorted(float(e) for e in (audio_events or []))
        blocks = self.layout.make_blocks(chunks, self.size, events)

        speed = 1.0
        target = self.cfg.timing.total_duration
        if target and duration > 0:
            speed = clamp(duration / target, 0.4, 1.5)

        exit_s = self._exit_seconds()
        durations = []
        for i, chunk in enumerate(chunks):
            # A beat stays in the stack for its reading time plus a couple of beats
            # of linger, so several flashes are always visible at once – that
            # overlap *is* the waterfall.  The exit animation runs after that.
            start = chunk.start
            end = chunk.end
            nxt = chunks[i + 1].start if i + 1 < len(chunks) else end + self.cfg.motion.scroll
            step = max(0.12, nxt - start)
            live = (end - start) + step * max(0.0, self.cfg.layout.linger) + exit_s * 1.2
            durations.append(max(exit_s * 1.25 + 0.12, live))
        program = Program(
            chunks=chunks,
            blocks=blocks,
            duration=duration,
            events=events,
            durations=durations,
            speed=speed,
        )
        self.program = program
        return program

    # -- public API --------------------------------------------------------- #
    def frame(self, t: float, program: Program | None = None) -> Image.Image:
        program = program or self.program
        if program is None:
            raise RuntimeError("call prepare() before frame()")
        return self._render_frame(t, program)

    def write(self, program: Program, out: str | Path | None = None, stills: int = 0, quiet: bool = False) -> str:
        """Render to ``out`` – or, with ``stills > 0``, dump spread-out PNG frames."""
        self.program = program
        cfg = self.cfg
        out_path = Path(out or cfg.output.out)
        if stills:
            return self._write_stills(program, out_path, stills)

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg not found on PATH – install it, or use --stills")
        fps = int(cfg.output.fps)
        total = max(1, int(math.ceil(program.duration * fps)))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostats", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{self.size[0]}x{self.size[1]}", "-r", str(fps), "-i", "pipe:0",
        ]
        if cfg.output.audio:
            cmd += ["-i", str(cfg.output.audio)]
        cmd += [
            "-c:v", "libx264", "-preset", cfg.output.preset, "-crf", str(cfg.output.crf),
            "-pix_fmt", cfg.output.pix_fmt, "-movflags", "+faststart",
        ]
        if cfg.output.audio:
            cmd += ["-c:a", "aac", "-b:a", cfg.output.audio_bitrate, "-shortest"]
        cmd += list(cfg.output.extra_args) + [str(out_path)]

        # ffmpeg's log goes to a temp file, never a pipe: nobody drains a pipe while
        # we are streaming frames into stdin, and a full 64 KB pipe buffer would
        # deadlock the render on a long video.
        log_path = out_path.with_suffix(out_path.suffix + ".ffmpeg.log")
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            started = time.perf_counter()
            step = max(1, total // 50)
            failure: OSError | None = None
            try:
                for i in range(total):
                    image = self.frame(i / fps, program)
                    try:
                        proc.stdin.write(image.tobytes())  # type: ignore[union-attr]
                    except OSError as exc:  # ffmpeg died – its log has the reason
                        failure = exc
                        break
                    if not quiet and (i % step == 0 or i == total - 1):
                        done = (i + 1) / total
                        elapsed = time.perf_counter() - started
                        fps_now = (i + 1) / max(1e-6, elapsed)
                        eta = (total - i - 1) / max(1e-6, fps_now)
                        sys.stderr.write(
                            f"\r  rendering {done * 100:5.1f}%  {i + 1}/{total} frames  "
                            f"{fps_now:5.1f} fps  eta {eta:5.1f}s      "
                        )
                        sys.stderr.flush()
            finally:
                if proc.stdin:
                    try:
                        proc.stdin.close()
                    except OSError:
                        pass
                code = proc.wait()
            if not quiet:
                sys.stderr.write("\n")
        if failure is not None or code != 0:
            detail = log_path.read_text(encoding="utf-8", errors="replace").strip()
            raise RuntimeError(
                f"ffmpeg failed ({code}): {failure or ''}\n{detail or '(no log output)'}\n"
                f"full log: {log_path}"
            )
        log_path.unlink(missing_ok=True)
        self.timings["render_seconds"] = time.perf_counter() - started
        return str(out_path)

    # -- timing helpers ----------------------------------------------------- #
    def _enter_seconds(self) -> float:
        return self.cfg.motion.enter_duration * self._speed()

    def _exit_seconds(self) -> float:
        return self.cfg.motion.exit_duration * self._speed()

    def _scroll_seconds(self) -> float:
        return self.cfg.motion.scroll * self._speed()

    def _speed(self) -> float:
        return self.program.speed if self.program else 1.0

    # -- state -------------------------------------------------------------- #
    def _slot(self, index: int, program: Program) -> float:
        """Vertical space a beat occupies, in overlay pixels.

        Uses the ink metrics rather than the sprite size: a sprite carries padding
        for the stroke and the drop shadow, and stacking *that* leaves a visible gap
        between two lines that should look like one flowing column.
        """
        block = program.blocks[index]
        ink = 0.0
        if block.metrics:
            first_top, last_bottom = block.metrics
            ink = max(0.0, last_bottom - first_top)
        if ink <= 0:
            ink = float(block.image.height)
        return (ink * 1.04 + max(2.0, block.font_size * 0.06)) * self.scale

    def _motion(self, program: Program) -> StackMotion:
        """Build (and memoise) the monotone displacement curve for this program."""
        cached = getattr(self, "_motion_cache", None)
        if cached is not None and cached[0] is program:
            return cached[1]
        motion = StackMotion(
            height_of=lambda i: self._slot(i, program),
            tops=[float(c.start) for c in program.chunks],
            scroll=self._scroll_seconds(),
            ease=self.cfg.motion.scroll_ease,
        )
        self._motion_cache = (program, motion)
        return motion

    def _active(self, t: float, program: Program) -> list[int]:
        chunks, durations = program.chunks, program.durations
        out: list[int] = []
        for i, chunk in enumerate(chunks):
            if chunk.start > t + 1e-6:
                break
            if i < len(durations) and chunk.start + durations[i] >= t:
                out.append(i)
        cap = self.cfg.layout.max_live
        if len(out) > cap:
            out = out[-cap:]
        return out

    def _simulate_offset(self, t: float, program: Program) -> float:
        """Total travel (pixels) of the oldest live beat – the motion measurement."""
        motion = self._motion(program)
        active = self._active(t, program)
        if not active:
            return 0.0
        return motion.carry(active[0], t) * motion.height(active[0])

    # -- frame -------------------------------------------------------------- #
    def _render_frame(self, t: float, program: Program) -> Image.Image:
        started = time.perf_counter()
        cfg = self.cfg
        scale = self.scale
        motion = self._motion(program)
        zoom, shake = self._camera(t, program)
        shift = (shake[0] * scale, shake[1] * scale)

        flash = self._flash(t, program)
        if flash is not None:
            canvas = self._tinted(self.base_bg, flash[0], flash[1]).convert("RGBA")
        else:
            canvas = self._base_rgba()

        active = self._active(t, program)
        newest = active[-1] if active else -1
        overlay = Image.new("RGBA", (self._ow, self._oh), (0, 0, 0, 0))

        for index in active:
            self._compose_beat(overlay, index, t, program, newest, motion, zoom, shift)

        if cfg.motion.rush_lines:
            self._draw_rush(overlay, t, program, motion)
        if self._progress_enabled():
            self._draw_progress(overlay, t, program)

        overlay = overlay.resize(self.size, Image.Resampling.BILINEAR)
        canvas = Image.alpha_composite(canvas, overlay)
        self.timings["compose"] = self.timings.get("compose", 0.0) + (time.perf_counter() - started)
        return canvas.convert("RGB")

    def _base_rgba(self) -> Image.Image:
        if self._base_cache is None:
            self._base_cache = self.base_bg.convert("RGBA")
        return self._base_cache.copy()

    # -- camera ------------------------------------------------------------- #
    def _camera(self, t: float, program: Program) -> tuple[float, tuple[float, float]]:
        cfg = self.cfg.camera
        phase = clamp(t / max(0.001, program.duration))
        zoom = 1.0 + cfg.slow_zoom * phase
        if "breathe" in cfg.mode:
            zoom += cfg.breathe * 0.5 * math.sin(2 * math.pi * phase + math.pi / 3)
        beat = self._latest_beat(t, program)
        shake = (0.0, 0.0)
        if beat is not None:
            age = max(0.0, t - beat)
            if "bounce" in cfg.mode:
                zoom += cfg.shake * 0.12 * math.exp(-age / 0.22)
            if cfg.shake > 0:
                decay = math.exp(-age / max(0.05, cfg.shake_decay))
                shake = (
                    math.sin(age * 47.0) * cfg.shake * 26.0 * decay,
                    math.cos(age * 39.0) * cfg.shake * 20.0 * decay,
                )
        return zoom, shake

    def _latest_beat(self, t: float, program: Program) -> float | None:
        best = None
        for event in program.events:
            if event <= t and (best is None or event > best):
                best = event
        return best

    def _flash(self, t: float, program: Program) -> tuple[str, float] | None:
        palette = self.cfg.background.beats
        if not self.cfg.motion.flash or not palette:
            return None
        beat = self._latest_beat(t, program)
        if beat is None:
            return None
        window = 0.34
        age = t - beat
        if age > window:
            return None
        strength = self.cfg.motion.flash_strength * (1.0 - age / window) ** 2
        if strength <= 0.004:
            return None
        index = program.events.index(beat) if beat in program.events else 0
        return palette[index % len(palette)], strength

    def _tinted(self, base: Image.Image, color: str, strength: float) -> Image.Image:
        key = rgb(color)
        cached = self._tint_cache.get(key)
        if cached is None:
            cached = bg.tinted(base, color, 0.55)
            if len(self._tint_cache) < 8:
                self._tint_cache[key] = cached
        # quantised so a decaying flash reuses the same blend a few frames running
        return Image.blend(base, cached, round(clamp(strength / 0.55), 2))

    def _progress_enabled(self) -> bool:
        return self.cfg.background.bar_height <= 0 and self.cfg.background.kind != "solid"

    # -- one beat ----------------------------------------------------------- #
    def _compose_beat(
        self,
        overlay: Image.Image,
        index: int,
        t: float,
        program: Program,
        newest: int,
        motion: StackMotion,
        zoom: float,
        shift: tuple[float, float],
    ) -> None:
        cfg = self.cfg
        chunk = program.chunks[index]
        block = program.blocks[index]
        hint = block.hint
        scale = self.scale
        lifetime = program.durations[index] if index < len(program.durations) else chunk.duration
        remaining = (chunk.start + lifetime) - t
        if remaining <= 0:
            return
        age = max(0.0, t - chunk.start)
        enter = self._enter_seconds()
        exit_s = min(self._exit_seconds(), max(0.12, lifetime * 0.9))

        opacity, sprite_scale = 1.0, 1.0
        dx = dy = rot = 0.0
        wipe = 1.0
        if age < enter:
            u = clamp(age / max(1e-4, enter))
            opacity, sprite_scale, dx, dy, rot, wipe = self._entrance(hint, u, block)
        elif remaining < exit_s:
            u = clamp(1.0 - remaining / exit_s)
            opacity, sprite_scale, dx, dy, rot = self._exit(hint, u, block)

        # keep a slow, permanent drift so nothing looks frozen
        drift = cfg.motion.drift * block.font_size
        if drift > 0 and age > enter:
            grow = clamp((age - enter) / max(0.25, self._scroll_seconds() * 3.0))
            dx += hint.get("drift_dir", 1.0) * drift * grow * 0.35
            dy -= drift * grow * 0.25

        depth = max(0, newest - index)
        if cfg.layout.depth_fade > 0:
            opacity *= max(0.0, 1.0 - cfg.layout.depth_fade * depth)
        if cfg.layout.depth_shrink > 0:
            sprite_scale *= max(0.2, 1.0 - cfg.layout.depth_shrink * depth)
        if opacity <= 0.004:
            return

        if index == newest:
            # how much of this beat's own rise is still to come
            sway = 1.0 - motion.ramp(t)
            if sway > 0:
                dy += hint.get("bow", 0.5) * block.font_size * 0.35 * sway
                dx += hint.get("x_off", 0.0) * self.size[0] * sway
            climb = 0.0
        else:
            climb = self._climb(index, newest, t, program, motion)

        anchor_x = (self.size[0] * 0.5 + dx) * scale + shift[0]
        anchor_y = (self.size[1] * cfg.layout.anchor_y + dy) * scale + shift[1] - climb
        if cfg.camera.parallax > 0:
            dist = anchor_y - self.size[1] * scale
            anchor_y = self.size[1] * scale + dist * lerp(1.0, zoom, clamp(cfg.camera.parallax))

        self._blit(overlay, block, anchor_x, anchor_y, sprite_scale * zoom, opacity, rot, scale, wipe)

    def _climb(self, index: int, newest: int, t: float, program: Program, motion: StackMotion) -> float:
        """Pixels beat ``index`` has risen above the anchor (eased, bounded).

        This is the one place the waterfall geometry is evaluated, so the motion tests
        can assert on it directly.
        """
        newest = min(newest, len(motion.tops) - 1)
        index = min(index, newest)
        value = 0.0
        for j in range(index + 1, newest + 1):
            value += motion.height(j) * cushion((t - motion.tops[j]) / motion.scroll, motion.ease)
        return value

    def _entrance(self, hint: dict, u: float, block: Block) -> tuple[float, float, float, float, float, float]:
        style = hint.get("enter", "pop")
        size = block.font_size
        opacity, sprite_scale = 1.0, 1.0
        dx = dy = rot = 0.0
        wipe = 1.0
        e = ease_out_cubic(u)
        if style == "pop":
            sprite_scale = lerp(0.58, 1.0, ease_out_back(u, 2.1))
            opacity = clamp(e * 1.5)
        elif style == "rise":
            dy = lerp(size * 1.5, 0.0, ease_out_back(u, 1.35))
            sprite_scale = lerp(0.94, 1.0, e)
            opacity = clamp(e * 1.4)
        elif style == "drop":
            dy = lerp(-size * 1.6, 0.0, ease_out_expo(u))
            sprite_scale = lerp(0.92, 1.0, e)
            opacity = clamp(e * 1.6)
        elif style == "zoom":
            sprite_scale = lerp(1.75, 1.0, ease_out_elastic(u, 0.16))
            opacity = clamp(e * 1.8)
        elif style == "swing":
            rot = lerp(-9.0, 0.0, ease_out_back(u, 1.6))
            dx = lerp(-size * 0.6, 0.0, ease_out_back(u, 1.4))
            sprite_scale = lerp(0.9, 1.0, e)
            opacity = clamp(e * 1.4)
        elif style == "typewriter":
            wipe = clamp(u * 1.25)
            sprite_scale = lerp(1.06, 1.0, e)
        return opacity, sprite_scale, dx, dy, rot, wipe

    def _exit(self, hint: dict, u: float, block: Block) -> tuple[float, float, float, float, float]:
        style = hint.get("exit", "shrink")
        size = block.font_size
        opacity, sprite_scale = 1.0, 1.0
        dx = dy = rot = 0.0
        if style == "shrink":
            sprite_scale = lerp(1.0, 0.6, ease_in_cubic(u))
            opacity = 1.0 - smoothstep(clamp((u - 0.25) / 0.75))
        elif style == "fade":
            opacity = 1.0 - smoothstep(u)
        elif style == "drift":
            dx = -size * 2.2 * ease_in_cubic(u)
            opacity = 1.0 - smoothstep(clamp((u - 0.2) / 0.8))
            rot = -4.0 * u
        elif style == "crumble":
            sprite_scale = lerp(1.0, 1.12, ease_out_cubic(u))
            opacity = 1.0 - smoothstep(u)
            rot = 3.0 * u
        return opacity, sprite_scale, dx, dy, rot

    # -- blitting ----------------------------------------------------------- #
    def _sprite(self, block: Block, key: tuple[int, int, int, int], scale: float, rotation: float, layer_scale: float) -> Image.Image:
        cached = self._sprite_cache.get(key)
        if cached is not None:
            return cached
        image = block.image
        target_w = max(1, int(round(image.width * scale * layer_scale)))
        target_h = max(1, int(round(image.height * scale * layer_scale)))
        image = image.resize((target_w, target_h), Image.Resampling.BILINEAR)
        if rotation:
            image = image.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
        if len(self._sprite_cache) < 512:
            self._sprite_cache[key] = image
        return image

    def _blit(
        self,
        overlay: Image.Image,
        block: Block,
        anchor_x: float,
        anchor_y: float,
        scale: float,
        opacity: float,
        rotation: float,
        layer_scale: float,
        wipe: float = 1.0,
    ) -> None:
        key = (id(block), int(round(scale * layer_scale * 1000)), int(round(opacity * 100)), int(round(rotation * 5)))
        image = self._sprite(block, key, scale, rotation, layer_scale)
        if image.width > overlay.width + block.image.width or image.height > overlay.height + block.image.height:
            return
        if opacity < 0.999:
            image = image.copy()
            image.putalpha(image.getchannel("A").point(lambda v: int(v * clamp(opacity))))
        if wipe < 0.995:
            image = image.crop((0, 0, max(1, int(round(image.width * wipe))), image.height))

        paste_x = anchor_x - image.width * block.ax
        paste_y = anchor_y - image.height * block.ay
        if paste_x > overlay.width or paste_y > overlay.height or paste_x + image.width < 0 or paste_y + image.height < 0:
            return
        if paste_x < 0 or paste_y < 0 or paste_x + image.width > overlay.width or paste_y + image.height > overlay.height:
            self._paste_clipped(overlay, image, int(round(paste_x)), int(round(paste_y)))
        else:
            overlay.alpha_composite(image, (int(round(paste_x)), int(round(paste_y))))

    @staticmethod
    def _paste_clipped(overlay: Image.Image, image: Image.Image, x: int, y: int) -> None:
        src = (
            max(0, -x),
            max(0, -y),
            min(image.width, overlay.width - x),
            min(image.height, overlay.height - y),
        )
        if src[2] <= src[0] or src[3] <= src[1]:
            return
        overlay.alpha_composite(image.crop(src), (max(0, x), max(0, y)))

    # -- decorations -------------------------------------------------------- #
    def _draw_rush(self, overlay: Image.Image, t: float, program: Program, motion: StackMotion) -> None:
        dt = 1.0 / 90.0
        active = self._active(t, program)
        if not active:
            return
        head = active[0]
        velocity = abs(
            motion.carry(head, t + dt) * motion.height(head) - motion.carry(head, t) * motion.height(head)
        ) / dt
        ref = self.size[1] * self.scale * 0.6
        strength = clamp((velocity - ref * 0.7) / max(1.0, ref))
        if strength <= 0.02:
            return
        rng = Rng(self.seed ^ int(round(strength * 997)))
        draw = ImageDraw.Draw(overlay)
        width, height = overlay.size
        for _ in range(int(6 + 24 * strength)):
            angle = rng.uniform(0, 2 * math.pi)
            inner = rng.uniform(0.10, 0.45)
            length = rng.uniform(0.10, 0.34) * (0.4 + strength)
            x0 = width * (0.5 + math.cos(angle) * inner)
            y0 = height * (0.5 + math.sin(angle) * inner * 1.15)
            x1 = x0 + math.cos(angle) * width * length
            y1 = y0 + math.sin(angle) * height * length * 0.6
            draw.line((x0, y0, x1, y1), fill=(255, 255, 255, int(36 * strength)), width=max(1, int(2 * strength) + 1))

    def _draw_progress(self, overlay: Image.Image, t: float, program: Program) -> None:
        if program.duration <= 0:
            return
        width, height = overlay.size
        share = clamp(t / program.duration)
        bar_h = max(2, int(height * 0.005))
        color = parse_color(self.cfg.style.accent)
        ImageDraw.Draw(overlay).rectangle((0, height - bar_h, int(width * share), height), fill=color + (190,))

    # -- stills -------------------------------------------------------------- #
    def _write_stills(self, program: Program, out: Path, count: int) -> str:
        stem = out.with_suffix("")
        made = []
        for i in range(count):
            t = program.duration * (i + 0.5) / count
            path = Path(f"{stem}_{i:02d}.png")
            self.frame(t, program).save(path)
            made.append(str(path))
        return "\n".join(made)
