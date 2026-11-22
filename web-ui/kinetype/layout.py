"""Layout + text rasterisation.

A beat becomes one :class:`Block`: a pre-rendered RGBA sprite plus the anchor
inside it that the animation pivots around.  Rasterising a block is the only
expensive step in the pipeline, so it happens exactly once per beat and the
per-frame work stays pure compositing.
"""

from __future__ import annotations

import math
import random as _random
from dataclasses import dataclass
from typing import Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .config import MOTION_ENTERS, MOTION_EXITS, RenderConfig, parse_color
from .fonts import FontSet
from .script import Chunk, Key
from .util import Rng, clamp, with_alpha

# --------------------------------------------------------------------------- #


@dataclass
class Block:
    """Rendered, ready-to-composite sprite for one beat."""

    image: Image.Image
    #: fraction of width where the anchor sits (always the horizontal centre)
    ax: float
    #: fraction of height where the anchor sits (the last baseline)
    ay: float
    font_size: float
    rows: int
    #: screen scale factor this block was laid out for
    factor: float
    hint: dict
    #: (first ink row, last ink row) inside the sprite – used for stack spacing
    metrics: tuple[int, int] = (0, 0)


@dataclass
class Row:
    keys: list[Key]
    width: float
    dx: float = 0.0


# --------------------------------------------------------------------------- #


class LayoutEngine:
    def __init__(self, cfg: RenderConfig, fonts: FontSet, seed: int = 0) -> None:
        self.cfg = cfg
        self.fonts = fonts
        self.rng = Rng(seed ^ 0x5EED)
        self._style_cache: dict[int, _random.Random] = {}

    # -- public ----------------------------------------------------------- #
    @staticmethod
    def screen_factor(size: tuple[int, int]) -> float:
        width, height = size
        return min(width / 1080.0, height / 1920.0)

    def make_blocks(self, chunks: Sequence[Chunk], size: tuple[int, int], audio_events: Sequence[float] = ()) -> list[Block]:
        factor = self.screen_factor(size)
        return [self._build_block(c, size, factor, audio_events) for c in chunks]

    def rng_for(self, chunk: Chunk) -> _random.Random:
        """Stable per-beat RNG so re-rendering reproduces the same look."""
        state = self._style_cache.get(chunk.index)
        if state is None:
            state = _random.Random(f"{self.rng.seed}:beat:{chunk.index}")
            self._style_cache[chunk.index] = state
        return state

    # -- block building ---------------------------------------------------- #
    def _build_block(
        self,
        chunk: Chunk,
        size: tuple[int, int],
        factor: float,
        audio_events: Sequence[float],
    ) -> Block:
        rng = self.rng_for(chunk)
        base_px = self._chunk_font_px(chunk, factor)
        max_width = size[0] * (1.0 - 2 * self.cfg.layout.margin_x) * self.cfg.font.max_line_width
        text = "".join(k.text for k in chunk.keys)
        is_latin = _looks_latin(text)

        hint = self._pick_style(chunk, rng, audio_events)
        rows, px = self._fit(chunk, base_px, max_width, factor, is_latin)
        image, ay, rows_n = self._rasterise(chunk, rows, px, factor, hint, rng)
        hint["width_frac"] = image.width / size[0]
        return Block(
            image=image,
            ax=0.5,
            ay=ay,
            font_size=px,
            rows=rows_n,
            factor=factor,
            hint=hint,
            metrics=_ink_extent(image),
        )

    def _chunk_font_px(self, chunk: Chunk, factor: float) -> float:
        font_cfg = self.cfg.font
        rng = self.rng_for(chunk)
        scale = rng.choices(font_cfg.size_range, weights=font_cfg.size_weights)[0]
        if len(chunk.keys) >= 3:
            scale *= font_cfg.long_keys_factor
        if any(k.highlight for k in chunk.keys):
            scale *= 1.07
        return max(14.0, font_cfg.base_size * factor * scale)

    def _pick_style(self, chunk: Chunk, rng: _random.Random, audio_events: Sequence[float]) -> dict:
        style = self.cfg.style
        motion = self.cfg.motion
        on_beat = self._nearest_event(chunk.start, audio_events) is not None
        if style.fill and style.fill != "auto":
            fill = parse_color(style.fill)[:3]
        elif rng.random() < style.accent_chance + (0.4 if chunk.emphasis else 0.0):
            fill = parse_color(style.accent)[:3]
        else:
            weights = style.weights if len(style.weights) == len(style.palette) else [1.0] * len(style.palette)
            fill = parse_color(rng.choices(style.palette, weights=weights)[0])[:3]
        enter = (
            rng.choices(sorted(MOTION_ENTERS), weights=[4.0, 3.0, 1.2, 1.5, 1.0, 1.4])[0]
            if motion.enter == "random"
            else motion.enter
        )
        exit_style = (
            rng.choices(sorted(MOTION_EXITS), weights=[5.0, 2.0, 1.5, 1.0])[0]
            if motion.exit == "random"
            else motion.exit
        )
        return {
            "fill": fill,
            "on_beat": on_beat,
            "enter": enter,
            "exit": exit_style,
            "x_off": rng.uniform(-1.0, 1.0) * motion.x_scatter,
            "y_off": rng.uniform(-1.0, 1.0) * motion.y_scatter,
            "bow": rng.uniform(0.35, 1.0),
            "tilt": rng.uniform(-1.0, 1.0) * 0.6,
            "drift_dir": rng.choice((-1.0, 1.0)),
            "stagger": rng.uniform(0.5, 1.6) * motion.stagger,
        }

    @staticmethod
    def _nearest_event(t: float, events: Sequence[float], window: float = 0.12) -> float | None:
        best: tuple[float, float] | None = None
        for event in events:
            delta = abs(event - t)
            if delta <= window and (best is None or delta < best[0]):
                best = (delta, event)
        return best[1] if best else None

    # -- fitting ----------------------------------------------------------- #
    def _measure(self, keys: Sequence[Key], px: float, bold_scale: bool) -> float:
        total = 0.0
        for key in keys:
            size = px * key.scale * (1.12 if (bold_scale and key.bold) else 1.0)
            total += float(self.fonts.for_text(key.text, size).getlength(key.text))
        return total

    def _fit(
        self,
        chunk: Chunk,
        base_px: float,
        max_width: float,
        factor: float,
        is_latin: bool,
    ) -> tuple[list[Row], float]:
        gap_ratio = self.cfg.font.word_gap
        min_px = max(12.0, self.cfg.font.base_size * factor * 0.45)

        def layout(px: float) -> list[Row]:
            gap = px * gap_ratio
            rows: list[Row] = []
            current: list[Key] = []
            width = 0.0
            for key in chunk.keys:
                if not key.text:
                    continue
                key_w = self._measure([key], px, True)
                if current and width + gap + key_w > max_width:
                    rows.append(Row(current, width))
                    current, width = [key], key_w
                else:
                    width += key_w if not current else key_w + gap
                    current.append(key)
            if current:
                rows.append(Row(current, width))
            return rows

        px = base_px
        rows = layout(px)
        guard = 0
        while max((r.width for r in rows), default=0.0) > max_width and px > min_px and guard < 24:
            px *= 0.9
            rows = layout(px)
            guard += 1
        while len(rows) > 3 and px > min_px and guard < 48:
            px *= 0.92
            rows = layout(px)
            guard += 1

        # a very short beat is allowed to get huge –half the charm of the format
        if len(chunk.keys) <= 2:
            wide = max((r.width for r in rows), default=0.0)
            if 0 < wide < max_width * 0.58:
                boost = min(1.45, (max_width * 0.74) / wide)
                if boost > 1.02:
                    boosted = layout(base_px * boost)
                    if max((r.width for r in boosted), default=0.0) <= max_width and boosted:
                        px, rows = base_px * boost, boosted

        if is_latin and self.cfg.text.uppercase_latin:
            for row in rows:
                for key in row.keys:
                    key.text = key.text.upper()
        return rows, px

    # -- rasterisation ----------------------------------------------------- #
    def _rasterise(
        self,
        chunk: Chunk,
        rows: list[Row],
        px: float,
        factor: float,
        hint: dict,
        rng: _random.Random,
    ) -> tuple[Image.Image, float, int]:
        style = self.cfg.style
        stroke_w = max(0.0, style.stroke_width * px)
        pad = int(math.ceil(stroke_w + abs(style.shadow) * 6.0)) + 3

        row_images: list[Image.Image] = []
        row_offsets: list[float] = []
        for row in rows:
            img, _baseline = self._render_row(row, px, stroke_w, pad, hint)
            row_images.append(img)
            row_offsets.append(rng.uniform(-1.0, 1.0) * style.jitter_x * px)

        height = int(sum(im.height for im in row_images)) + 2 * pad
        width = int(max((im.width for im in row_images), default=1)) + 2 * pad
        canvas = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))

        y = float(pad)
        last_baseline = y
        for img, dx in zip(row_images, row_offsets):
            x = (canvas.width - img.width) / 2.0 + dx
            canvas.alpha_composite(img, (int(round(x)), int(round(y))))
            last_baseline = y + img.height * 0.78
            y += img.height
        ay = clamp(last_baseline / max(1, canvas.height), 0.05, 0.98)
        return canvas, ay, len(rows)

    def _render_row(
        self,
        row: Row,
        px: float,
        stroke_w: float,
        pad: int,
        hint: dict,
    ) -> tuple[Image.Image, float]:
        style = self.cfg.style
        gap = px * self.cfg.font.word_gap
        probe = self.fonts.for_text("汉Ag", int(round(px)))
        ascent, descent = probe.getmetrics()
        samples = [k.text for k in row.keys if k.text] or ["汉Ag"]
        bboxes = [probe.getbbox(s) for s in samples]
        top_extent = max(0, -min(b[1] for b in bboxes))
        bottom_extent = max(b[3] for b in bboxes)
        ascent = max(ascent, top_extent)
        descent = max(descent, bottom_extent - ascent, 0)

        widths = [self._measure([k], px, True) for k in row.keys]
        total_w = sum(widths) + gap * max(0, len(row.keys) - 1)
        img = Image.new(
            "RGBA",
            (int(math.ceil(total_w + 2 * pad + 2)), int(math.ceil(ascent + descent + 2 * pad + 2))),
            (0, 0, 0, 0),
        )
        draw = ImageDraw.Draw(img)
        baseline = pad + ascent

        x = float(pad)
        for key, key_w in zip(row.keys, widths):
            font = self.fonts.for_text(key.text, px * key.scale * (1.12 if key.bold else 1.0))
            fill = parse_color(key.color)[:3] if key.color else hint["fill"]
            stroked = stroke_w
            if key.highlight and style.highlight_box:
                box_pad = style.highlight_box_pad * px
                box_color = parse_color(style.highlight_box_color)[:3]
                draw.rounded_rectangle(
                    (
                        x - box_pad,
                        baseline - ascent - box_pad * 0.35,
                        x + key_w + box_pad,
                        baseline + descent + box_pad * 0.45,
                    ),
                    radius=max(4.0, px * 0.14),
                    fill=box_color + (255,),
                )
                # Dark-on-yellow only reads with a light keyline between glyph and
                # box, so draw the keyline *before* the glyph.  The keyline is the
                # box colour itself (a slightly expanded glyph), four times over, so
                # it never bleeds onto the surrounding text of the same beat.
                lum = 0.299 * box_color[0] + 0.587 * box_color[1] + 0.114 * box_color[2]
                if lum > 128:
                    self._keyline(img, font, key.text, x, baseline, max(2.0, px * 0.055), box_color)
                fill = (12, 12, 16) if lum > 128 else (250, 250, 250)
            self._draw_key(
                img,
                font,
                key.text,
                x,
                baseline,
                stroke_w,
                fill,
                skip_stroke=bool(key.highlight and style.highlight_box),
            )
            x += key_w + gap
        return img, baseline

    @staticmethod
    def _keyline(img: Image.Image, font, text: str, x: float, baseline: float, width: float, color) -> None:
        """Fat glyph in the box colour, painted under the dark glyph on top of it."""
        if width <= 0.4:
            return
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(
            (x, baseline),
            text,
            font=font,
            anchor="ls",
            fill=tuple(color) + (255,),
            stroke_width=int(round(width)),
            stroke_fill=tuple(color) + (255,),
        )
        img.alpha_composite(layer)

    def _draw_key(
        self,
        img: Image.Image,
        font,
        text: str,
        x: float,
        baseline: float,
        stroke_w: float,
        fill,
        skip_stroke: bool = False,
    ) -> None:
        style = self.cfg.style
        stroke = parse_color(style.stroke_color)[:3]
        shadow = clamp(style.shadow, 0.0, 2.0)

        if shadow > 0.02 and not skip_stroke:
            offset = max(1.0, stroke_w * 0.9 + 2.0)
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).text(
                (x + offset, baseline + offset),
                text,
                font=font,
                anchor="ls",
                fill=(0, 0, 0, int(150 * shadow)),
                stroke_width=int(round(stroke_w)),
                stroke_fill=(0, 0, 0, int(150 * shadow)),
            )
            img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(max(1.0, stroke_w + 2.0))))

        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        if stroke_w > 0.4 and not skip_stroke:
            draw.text(
                (x, baseline),
                text,
                font=font,
                anchor="ls",
                fill=stroke + (255,),
                stroke_width=int(round(stroke_w)),
                stroke_fill=stroke + (255,),
            )
        draw.text((x, baseline), text, font=font, anchor="ls", fill=tuple(fill) + (255,))

        if style.glow:
            # glow first, glyphs after – multiply() would crush a dark fill to a blob
            halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(halo).text(
                (x, baseline),
                text,
                font=font,
                anchor="ls",
                fill=with_alpha(fill, 0.8),
                stroke_width=int(max(1, round(stroke_w * 0.6))),
                stroke_fill=with_alpha(fill, 0.8),
            )
            blurred = halo.filter(ImageFilter.GaussianBlur(max(2.0, stroke_w * 1.6 + 3.0)))
            if shadow > 0.02:
                # a second, wider pass makes the halo read as light rather than blur
                wide = halo.filter(ImageFilter.GaussianBlur(max(6.0, stroke_w * 4.0 + 8.0)))
                wide.putalpha(wide.getchannel("A").point(lambda v: int(v * 0.45)))
                blurred = Image.alpha_composite(blurred, wide)
            img.alpha_composite(blurred)

        img.alpha_composite(layer)


def _ink_extent(image: Image.Image) -> tuple[int, int]:
    """First and last row of the sprite that actually contains ink."""
    bbox = image.getchannel("A").getbbox()
    if not bbox:
        return (0, image.height)
    return (bbox[1], bbox[3])


def _looks_latin(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 4:
        return False
    return sum(1 for ch in letters if ch.isascii()) / len(letters) > 0.7
