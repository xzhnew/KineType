"""KineType – turn a script into a waterfall-typography video with one command.

    kinetype render script.txt --preset meme-punch --audio voice.wav

The CLI is intentionally boring: everything interesting lives in ``kinetype``
package modules (script → layout → renderer → ffmpeg).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .audio import analyse, wav_duration
from .config import DEFAULT_PRESET, PRESETS, RenderConfig, load_config
from .fonts import FontSet
from .renderer import Renderer
from .script import assign_timeline, chunks_from_text, describe, load_script


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kinetype",
        description="Render snappy waterfall / rapid-flash typography videos from plain text.",
    )
    parser.add_argument("--version", action="version", version="KineType 0.1.0")
    sub = parser.add_subparsers(dest="command")

    # -- render ---------------------------------------------------------- #
    render = sub.add_parser("render", help="render a video or a batch of stills")
    render.add_argument("script", nargs="?", help="path to .txt/.srt/.json, or the script itself")
    render.add_argument("-o", "--out", help="output file (default: kinetype.mp4)")
    render.add_argument("-t", "--text", help="script text passed directly on the command line")
    render.add_argument("-p", "--preset", default=DEFAULT_PRESET, choices=sorted(PRESETS))
    render.add_argument("-c", "--config", help="JSON config layered on top of the preset")
    render.add_argument("-s", "--set", action="append", default=[], metavar="KEY=VALUE",
                        help="config override, e.g. -s style.accent=#FF2E63 -s motion.scroll=0.24")
    render.add_argument("-a", "--audio", help="audio track; also used for beat flashes and duration")
    render.add_argument("--size", help="WxH, e.g. 1080x1920 / 1920x1080 / 1080x1080")
    render.add_argument("--fps", type=int)
    render.add_argument("--seed", type=int, help="change the random look")
    render.add_argument("--duration", type=float, help="force the total video length in seconds")
    render.add_argument("--fit-audio", action="store_true",
                        help="stretch the timeline so the last beat lands on the end of the audio")
    render.add_argument("--stills", type=int, metavar="N", help="write N spread-out PNG frames instead of a video")
    render.add_argument("--dry-run", action="store_true", help="print the beat sheet and exit")
    render.add_argument("--dump-config", metavar="PATH", help="write the resolved config as JSON")
    render.add_argument("-q", "--quiet", action="store_true")

    # -- preview --------------------------------------------------------- #
    preview = sub.add_parser("preview", help="quick low-res stills for iterating on a look")
    preview.add_argument("script", nargs="?")
    preview.add_argument("-t", "--text")
    preview.add_argument("-p", "--preset", default=DEFAULT_PRESET, choices=sorted(PRESETS))
    preview.add_argument("-c", "--config")
    preview.add_argument("-s", "--set", action="append", default=[])
    preview.add_argument("-n", "--frames", type=int, default=6)
    preview.add_argument("--size", default="540x960")
    preview.add_argument("--seed", type=int)
    preview.add_argument("--out", default="preview.png")

    # -- inspect --------------------------------------------------------- #
    presets = sub.add_parser("presets", help="list the built-in looks")
    presets.add_argument("--json", action="store_true")
    sub.add_parser("fonts", help="show which font files KineType resolved")

    sheet = sub.add_parser("sheet", help="grab N frames from a video into one contact sheet")
    sheet.add_argument("video", help="an mp4 produced by KineType")
    sheet.add_argument("-n", "--frames", type=int, default=12)
    sheet.add_argument("-o", "--out", default="sheet.png")
    sheet.add_argument("--cols", type=int, default=6)
    sheet.add_argument("--cell-width", type=int, default=270)
    sheet.add_argument("--start", type=float, default=0.0)
    sheet.add_argument("--end", type=float, default=None)
    sheet.add_argument("--gif", metavar="PATH", help="also write an animated preview gif")
    sheet.add_argument("--gif-fps", type=float, default=10.0)
    sheet.add_argument("--gif-width", type=int, default=420)

    demo = sub.add_parser("demo", help="render the bundled sample script")
    demo.add_argument("-p", "--preset", default=DEFAULT_PRESET, choices=sorted(PRESETS))
    demo.add_argument("-o", "--out", default="demo.mp4")
    demo.add_argument("--size", default="1080x1920")
    demo.add_argument("--fps", type=int, default=60)
    demo.add_argument("--stills", type=int, default=0)
    demo.add_argument("--seed", type=int)
    return parser

# --------------------------------------------------------------------------- #


def _overrides(pairs: list[str]) -> dict:
    out: dict = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set expects KEY=VALUE, got {pair!r}")
        key, _, raw = pair.partition("=")
        value = _coerce(raw)
        node = out
        parts = key.strip().split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


def _coerce(raw: str):
    text = raw.strip()
    low = text.lower()
    if low in {"true", "yes", "on"}:
        return True
    if low in {"false", "no", "off"}:
        return False
    if low in {"none", "null"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    if text.startswith("[") or text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    if "," in text and not text.startswith("#"):
        return [_coerce(part) for part in text.split(",")]
    return text


def _config_from_args(args) -> RenderConfig:
    cfg = load_config(getattr(args, "preset", None), getattr(args, "config", None), _overrides(args.set))
    if getattr(args, "size", None):
        width, _, height = args.size.lower().partition("x")
        cfg.output.width, cfg.output.height = int(width), int(height)
    if getattr(args, "fps", None):
        cfg.output.fps = args.fps
    if getattr(args, "seed", None) is not None:
        cfg.seed = args.seed
    if getattr(args, "audio", None):
        cfg.output.audio = args.audio
    if getattr(args, "duration", None):
        cfg.timing.total_duration = args.duration
    if getattr(args, "out", None):
        cfg.output.out = args.out
    problems = cfg.validate()
    if problems:
        raise SystemExit("config problems:\n  - " + "\n  - ".join(problems))
    return cfg


def _prepare(script: str | None, text: str | None, cfg: RenderConfig, fit_audio: bool):
    chunks = load_script(script, cfg, text)
    if not chunks:
        raise SystemExit("no beats found – is the script empty?")
    target = cfg.timing.total_duration
    if target is None and cfg.output.audio:
        length = wav_duration(cfg.output.audio)
        if length and fit_audio:
            cfg.timing.total_duration = max(0.5, length - cfg.output.audio_offset)
            target = cfg.timing.total_duration
        elif length:
            cfg.timing.total_duration = max(0.5, length)
            target = cfg.timing.total_duration
    duration = assign_timeline(chunks, cfg, target)
    events: list[float] = []
    if cfg.output.audio:
        events = analyse(cfg.output.audio, cfg.output.audio_offset)
    return chunks, duration, events


# --------------------------------------------------------------------------- #


def cmd_render(args) -> int:
    cfg = _config_from_args(args)
    chunks, duration, events = _prepare(args.script, args.text, cfg, args.fit_audio)
    if args.dump_config:
        cfg.to_json(args.dump_config)
        print(f"config written to {args.dump_config}")
    if args.dry_run:
        print(f"# {len(chunks)} beats, {duration:.2f}s, preset look from seed {cfg.seed}")
        print(describe(chunks))
        if events:
            print(f"# {len(events)} audio beats detected")
        return 0

    renderer = Renderer(cfg)
    program = renderer.prepare(chunks, duration, events)
    if not args.quiet:
        print(
            f"kinetype · {len(chunks)} beats · {duration:.2f}s · "
            f"{cfg.output.width}x{cfg.output.height}@{cfg.output.fps} · {cfg.output.out}"
        )
    result = renderer.write(program, args.out, stills=args.stills or 0, quiet=args.quiet)
    if args.stills:
        print(result)
    else:
        print(f"done -> {result}  ({renderer.timings.get('render_seconds', 0):.1f}s)")
    return 0


def cmd_preview(args) -> int:
    width, _, height = args.size.lower().partition("x")
    overrides = _overrides(args.set)
    overrides.setdefault("output", {})
    base = load_config(args.preset, args.config, overrides)
    base.output.width, base.output.height = int(width), int(height)
    if args.seed is not None:
        base.seed = args.seed
    chunks = load_script(args.script, base, args.text)
    if not chunks:
        raise SystemExit("no beats found")
    duration = assign_timeline(chunks, base)
    renderer = Renderer(base)
    program = renderer.prepare(chunks, duration, [])
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    stem = target.with_suffix("")
    for i in range(args.frames):
        t = duration * (i + 0.5) / args.frames
        path = Path(f"{stem}_{i:02d}.png")
        renderer.frame(t, program).save(path)
        print(path)
    return 0


def cmd_presets(args) -> int:
    if args.json:
        print(json.dumps(PRESETS, ensure_ascii=False, indent=2))
        return 0
    print("built-in looks:\n")
    for name, data in sorted(PRESETS.items()):
        style = data.get("style", {})
        motion = data.get("motion", {})
        palette = " ".join(style.get("palette", [])[:5]) or style.get("fill", "")
        print(f"  {name:<14} enter={motion.get('enter', 'random'):<11} palette: {palette}")
    print("\nuse one with:  kinetype render script.txt -p <name>")
    return 0


def cmd_fonts(_args) -> int:
    fonts = FontSet(load_config(DEFAULT_PRESET).font)
    print(fonts.describe())
    fonts.require()
    return 0


def cmd_sheet(args) -> int:
    """Pull frames out of a rendered video with ffmpeg and tile them."""
    from PIL import Image

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found on PATH")
    start = max(0.0, args.start)
    with tempfile.TemporaryDirectory() as tmp:
        pattern = str(Path(tmp) / "f_%03d.png")
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}",
        ]
        if args.end is not None:
            cmd += ["-t", f"{max(0.05, args.end - start):.3f}"]
        cmd += ["-i", args.video, pattern]
        subprocess.run(cmd, check=True)
        files = sorted(Path(tmp).glob("f_*.png"))
        if not files:
            raise SystemExit("ffmpeg produced no frames")
        picks = [files[round(i * (len(files) - 1) / max(1, args.frames - 1))] for i in range(args.frames)]
        images = [Image.open(p).convert("RGB") for p in picks]
        gif_frames: list[Image.Image] = []
        if args.gif:
            span_end = args.end if args.end is not None else start + len(files) / max(1.0, _video_fps(args.video))
            gif_pattern = str(Path(tmp) / "g_%03d.png")
            gif_cmd = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}",
                "-t", f"{max(0.1, span_end - start):.3f}", "-i", args.video,
                "-vf", f"fps={max(1.0, args.gif_fps):g}", gif_pattern,
            ]
            subprocess.run(gif_cmd, check=True)
            for path in sorted(Path(tmp).glob("g_*.png")):
                frame = Image.open(path).convert("RGB")
                if frame.width <= 0:
                    continue
                width = args.gif_width
                gif_frames.append(frame.resize((width, max(1, int(width * frame.height / frame.width))), Image.Resampling.LANCZOS))
    cell_w = args.cell_width
    cell_h = int(round(cell_w * images[0].height / images[0].width))
    cols = max(1, args.cols)
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cell_w * cols, cell_h * rows), (10, 10, 14))
    for i, image in enumerate(images):
        out.paste(image.resize((cell_w, cell_h), Image.Resampling.LANCZOS), ((i % cols) * cell_w, (i // cols) * cell_h))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.save(args.out)
    print(f"{len(images)} frames from {args.video} -> {args.out}  ({out.width}x{out.height})")
    if args.gif and gif_frames:
        gif_path = Path(args.gif)
        gif_path.parent.mkdir(parents=True, exist_ok=True)
        gif_frames[0].save(
            gif_path,
            save_all=True,
            append_images=gif_frames[1:],
            duration=int(1000 / max(1.0, args.gif_fps)),
            loop=0,
            optimize=True,
        )
        print(f"gif -> {gif_path}  ({len(gif_frames)} frames)")
    return 0


def _video_fps(path: str) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 30.0
    try:
        raw = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=r_frame_rate", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        num, _, den = raw.partition("/")
        return float(num) / float(den or 1) if num else 30.0
    except Exception:
        return 30.0


def cmd_demo(args) -> int:
    """Render the bundled 倒鸭子 sample, using the bundled beat track when present."""
    here = Path(__file__).resolve().parent
    # kinetype/ lives directly under <web-ui>, next to samples/.
    sample = here.parent / "samples" / "daoyazi.zh.txt"
    if not sample.is_file():
        raise SystemExit(f"sample script missing: {sample}")
    width, _, height = args.size.lower().partition("x")
    cfg = load_config(args.preset, None, {})
    cfg.output.width, cfg.output.height, cfg.output.fps = int(width), int(height), args.fps
    cfg.output.out = args.out
    if args.seed is not None:
        cfg.seed = args.seed
    beat = sample.parent / "music" / "daoyazi_beat.wav"
    if beat.is_file():
        cfg.output.audio = str(beat)
        cfg.output.audio_offset = 0.05
    chunks, duration, events = _prepare(str(sample), None, cfg, fit_audio=False)
    renderer = Renderer(cfg)
    program = renderer.prepare(chunks, duration, events)
    print(f"kinetype demo · {len(chunks)} beats · {duration:.2f}s · {cfg.output.out}")
    print(renderer.write(program, args.out, stills=args.stills))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    handlers = {
        "render": cmd_render,
        "preview": cmd_preview,
        "presets": cmd_presets,
        "fonts": cmd_fonts,
        "sheet": cmd_sheet,
        "demo": cmd_demo,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
