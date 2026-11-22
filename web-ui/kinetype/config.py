"""Kinetype configuration: dataclass options, presets and JSON (de)serialisation.

Everything the renderer needs is expressed by :class:`RenderConfig` so a look can
be reproduced exactly from a single JSON file or CLI flag set.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# colour helpers
# --------------------------------------------------------------------------- #

NAMED_COLORS: dict[str, str] = {
    "white": "#FFFFFF",
    "black": "#000000",
    "ink": "#101014",
    "paper": "#F6F1E7",
    "cream": "#FFF6E5",
    "yellow": "#FFD84D",
    "gold": "#FFC24B",
    "orange": "#FF8A3D",
    "red": "#FF4D5E",
    "pink": "#FF6FB5",
    "magenta": "#FF3D9A",
    "purple": "#A06BFF",
    "blue": "#4DA3FF",
    "cyan": "#35E1E8",
    "teal": "#2EC4B6",
    "green": "#4CD964",
    "lime": "#B8E986",
    "sky": "#7FD1FF",
    "navy": "#1B2A4A",
    "grey": "#8A8F98",
    "gray": "#8A8F98",
    "silver": "#C9CDD6",
}


def parse_color(value: Any) -> tuple[int, int, int] | tuple[int, int, int, int]:
    """``"#FFD84D"`` / ``"yellow"`` / ``[255,216,77]`` -> RGB(A) tuple."""
    if value is None:
        raise ValueError("colour value is None")
    if isinstance(value, (tuple, list)):
        parts = [int(v) for v in value]
        if len(parts) == 3:
            return (parts[0], parts[1], parts[2])
        if len(parts) == 4:
            return (parts[0], parts[1], parts[2], parts[3])
        raise ValueError(f"colour sequence must have 3 or 4 parts, got {value!r}")
    text = str(value).strip()
    low = text.lower()
    if low in NAMED_COLORS:
        text = NAMED_COLORS[low]
    if text.startswith("rgb(") and text.endswith(")"):
        parts = [int(float(p)) for p in text[4:-1].split(",")]
        return (parts[0], parts[1], parts[2])
    if not text.startswith("#"):
        text = "#" + text
    body = text[1:]
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    if len(body) == 8:  # RRGGBBAA
        rgba = tuple(int(body[i : i + 2], 16) for i in (0, 2, 4, 6))
        return rgba  # type: ignore[return-value]
    if len(body) != 6:
        raise ValueError(f"cannot parse colour {value!r}")
    return tuple(int(body[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb(value: Any) -> tuple[int, int, int]:
    c = parse_color(value)
    if len(c) == 3:
        return c  # type: ignore[return-value]
    r, g, b, a = c  # type: ignore[misc]
    if a >= 255:
        return (r, g, b)
    # composite over black for simplicity (only used for opaque surfaces)
    return (r * a // 255, g * a // 255, b * a // 255)


# --------------------------------------------------------------------------- #
# sub-configs
# --------------------------------------------------------------------------- #


@dataclass
class FontConfig:
    cjk: list[str] = field(
        default_factory=lambda: [
            "C:/Windows/Fonts/msyhbd.ttc",  # Microsoft YaHei Bold
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "Noto Sans CJK SC",
        ]
    )
    latin: list[str] = field(
        default_factory=lambda: [
            "C:/Windows/Fonts/ariblk.ttf",  # Arial Black
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/impact.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    )
    #: scale of the "big" size relative to the base size
    base_size: float = 44.0
    #: per-chunk size range as a multiplier of ``base_size``
    size_range: list[float] = field(default_factory=lambda: [0.80, 1.00, 1.22, 1.46])
    #: weights used when picking a random size from ``size_range``
    size_weights: list[float] = field(default_factory=lambda: [3.0, 4.0, 2.0, 1.0])
    #: size multiplier for a chunk that already counts as "long" (3+ keys)
    long_keys_factor: float = 0.78
    #: keyword (highlighted) text is drawn this much larger
    key_emphasis_factor: float = 1.16
    #: shrink to fit when a visual line would be wider than this share of width
    max_line_width: float = 0.94
    #: line height multiplier
    line_height: float = 1.20
    #: extra space (px) between two keys on the same visual line
    word_gap: float = 0.28  # × font size


@dataclass
class StyleConfig:
    palette: list[str] = field(
        default_factory=lambda: [
            "#FFFFFF",
            "#FFD84D",
            "#FF8A3D",
            "#4DA3FF",
            "#4CD964",
            "#FF6FB5",
            "#35E1E8",
        ]
    )
    weights: list[float] = field(default_factory=lambda: [5.0, 3.0, 2.0, 2.0, 1.6, 1.6, 1.2])
    #: colour used for ``[highlighted]`` keys
    accent: str = "#FFD84D"
    #: fraction of random picks that use ``accent``
    accent_chance: float = 0.22
    #: text fill (``"auto"`` = pick from palette, or a fixed colour)
    fill: str = "auto"
    stroke_color: str = "#0B0B10"
    stroke_width: float = 0.085  # × font size
    #: highlight box behind ``[keywords]``
    highlight_box: bool = True
    highlight_box_color: str = "#FFD84D"
    highlight_box_pad: float = 0.22  # × font size
    highlight_text_color: str = "#101014"
    shadow: float = 0.55  # 0 = off, 1 = strong
    rotation_range: float = 3.2  # degrees of per-key random tilt
    jitter_x: float = 0.06  # × font size, per-key horizontal wobble
    glow: bool = False


@dataclass
class MotionConfig:
    #: entrance style: pop | rise | drop | zoom | typewriter | random
    enter: str = "random"
    enter_duration: float = 0.30
    #: exit style: shrink | fade | drift | crumble
    exit: str = "shrink"
    exit_duration: float = 0.26
    #: keyframe scroll: time (s) until the stack glides up by one slot
    scroll: float = 0.34
    #: settle time constant as a multiple of ``scroll`` – smaller = snappier
    scroll_ease: float = 0.45
    #: 0..1, how much a chunk drifts/shrinks forever after settling (anti-burn-in)
    drift: float = 0.06
    #: per-key stagger when a chunk has several keys
    stagger: float = 0.055
    #: weight of the random horizontal offset (× screen width)
    x_scatter: float = 0.06
    #: weight of the random vertical offset (× stack height)
    y_scatter: float = 0.10
    #: how far a chunk bows outward while entering (0..1 of a slot)
    bow: float = 0.55
    #: speed-line / rush-line overlay
    rush_lines: bool = True
    #: extra colour flash on emphasised beats
    flash: bool = True
    flash_strength: float = 0.18


@dataclass
class CameraConfig:
    #: ``scroll`` sinks the whole stack upward, ``still`` pins it, ``breathe`` adds
    #: a slow push-in, ``bounce`` shakes on emphasised beats.
    mode: str = "scroll+breathe"
    breathe: float = 0.045  # total zoom delta over the whole video
    shake: float = 0.10  # on-beat shake strength
    shake_decay: float = 0.55
    slow_zoom: float = 0.0  # extra linear zoom across the video
    parallax: float = 1.0  # 0 = no zoom response on text, 1 = full


@dataclass
class BackgroundConfig:
    kind: str = "gradient"  # solid | gradient | radial | dots | noise
    colors: list[str] = field(default_factory=lambda: ["#12121A", "#1E2140"])
    beats: list[str] = field(default_factory=list)  # colour-flash palette
    angle: float = 90.0  # gradient angle in degrees
    dot_spacing: float = 48.0
    dot_radius: float = 2.0
    dot_color: str = "#FFFFFF"
    dot_opacity: float = 0.07
    vignette: float = 0.40
    noise: float = 0.05
    #: optional bar overlay drawn at the top/bottom (0 disables)
    bar_height: float = 0.0
    bar_color: str = "#000000"


@dataclass
class LayoutConfig:
    #: where the newest chunk sits, share of height from the top
    anchor_y: float = 0.66
    margin_x: float = 0.07
    #: maximum number of chunks kept alive at once
    max_live: int = 10
    #: how many beat-gaps an old flash lingers before it starts leaving, so that
    #: several beats are visible at the same time (this is the "waterfall" part)
    linger: float = 1.5
    #: progressive scale falloff for older chunks (1.0 = off)
    depth_shrink: float = 0.0
    #: fade older chunks as they age
    depth_fade: float = 0.0


@dataclass
class OutputConfig:
    out: str = "kinetype.mp4"
    width: int = 1080
    height: int = 1920
    fps: int = 60
    preset: str = "veryfast"
    crf: int = 18
    pix_fmt: str = "yuv420p"
    audio: str | None = None
    audio_offset: float = 0.0
    audio_bitrate: str = "192k"
    extra_args: list[str] = field(default_factory=list)


@dataclass
class TimingConfig:
    #: characters (CJK) or words (latin) per second used to guess durations
    cps_cjk: float = 13.0
    cps_latin: float = 5.5
    min_duration: float = 0.30
    max_duration: float = 3.20
    #: gap inserted after terminal punctuation
    pause: float = 0.06
    pause_strong: float = 0.16
    lead_in: float = 0.25
    tail: float = 0.90
    #: force the video to exactly fill ``duration`` (e.g. the audio length)
    total_duration: float | None = None


@dataclass
class TextConfig:
    #: punch | tight | balanced | wide
    chunk_mode: str = "tight"
    max_keys: int = 5
    min_keys: int = 1
    allow_latin: bool = True
    uppercase_latin: bool = False


# --------------------------------------------------------------------------- #
# root config
# --------------------------------------------------------------------------- #


@dataclass
class RenderConfig:
    seed: int = 20260214
    font: FontConfig = field(default_factory=FontConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    text: TextConfig = field(default_factory=TextConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    # -- serialisation ----------------------------------------------------- #
    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self, path: str | Path | None = None) -> str:
        blob = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        if path is not None:
            Path(path).write_text(blob, encoding="utf-8")
        return blob

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenderConfig":
        cfg = cls()
        _apply(cfg, data)
        return cfg

    @classmethod
    def from_json(cls, path: str | Path) -> "RenderConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def merged(self, data: dict[str, Any]) -> "RenderConfig":
        """Return a copy of this config with ``data`` layered on top."""
        clone = RenderConfig.from_dict(self.to_dict())
        _apply(clone, data)
        return clone

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.output.width <= 0 or self.output.height <= 0:
            problems.append("output width/height must be positive")
        if not 1 <= self.output.fps <= 240:
            problems.append("output fps must be within 1..240")
        if self.layout.max_live < 2:
            problems.append("layout.max_live must be >= 2")
        if self.text.max_keys < 1:
            problems.append("text.max_keys must be >= 1")
        if self.text.chunk_mode not in {"punch", "tight", "balanced", "wide"}:
            problems.append("text.chunk_mode must be punch|tight|balanced|wide")
        if self.motion.enter != "random" and self.motion.enter not in MOTION_ENTERS:
            problems.append(f"motion.enter must be one of {sorted(MOTION_ENTERS)} or 'random'")
        if self.motion.exit not in MOTION_EXITS:
            problems.append(f"motion.exit must be one of {sorted(MOTION_EXITS)}")
        if self.background.kind not in BACKGROUND_KINDS:
            problems.append(f"background.kind must be one of {sorted(BACKGROUND_KINDS)}")
        return problems


MOTION_ENTERS = {"pop", "rise", "drop", "zoom", "typewriter", "swing"}
MOTION_EXITS = {"shrink", "fade", "drift", "crumble"}
BACKGROUND_KINDS = {"solid", "gradient", "radial", "dots", "noise"}


def _apply(cfg: Any, data: dict[str, Any]) -> None:
    """Recursively overlay a plain dict on a dataclass instance."""
    known = {f.name: f for f in fields(cfg)}
    for key, value in (data or {}).items():
        if key not in known:
            raise KeyError(f"unknown config key: {key!r}")
        current = getattr(cfg, key)
        if dataclasses.is_dataclass(current) and isinstance(value, dict):
            _apply(current, value)
        else:
            setattr(cfg, key, value)


# --------------------------------------------------------------------------- #
# presets – the "looks" people actually want
# --------------------------------------------------------------------------- #

PRESETS: dict[str, dict[str, Any]] = {
    # 抖音爆款：黑底 + 高饱和撞色 + 弹入 + 抖屏
    "meme-punch": {
        "style": {
            "palette": ["#FFFFFF", "#FFFFFF", "#FFD84D", "#FF4D5E", "#4DA3FF", "#4CD964", "#FF6FB5"],
            "weights": [5.0, 4.0, 3.5, 2.4, 2.0, 1.6, 1.6],
            "accent": "#FFD84D",
            "accent_chance": 0.12,
            "stroke_width": 0.095,
            "highlight_box": True,
            "highlight_box_color": "#FFD84D",
            "highlight_text_color": "#101014",
            "shadow": 0.7,
            "rotation_range": 4.5,
        },
        "motion": {
            "enter": "random",
            "enter_duration": 0.26,
            "scroll": 0.30,
            "stagger": 0.05,
            "x_scatter": 0.05,
            "rush_lines": True,
            "flash": True,
            "flash_strength": 0.22,
        },
        "camera": {"mode": "scroll+bounce", "breathe": 0.06, "shake": 0.16},
        "background": {"kind": "gradient", "colors": ["#20222E", "#0A0A0F"], "angle": 100.0, "vignette": 0.30},
        "font": {"base_size": 45.0, "size_range": [0.80, 1.0, 1.16, 1.32], "long_keys_factor": 0.86},
        "layout": {"anchor_y": 0.68, "linger": 1.5},
    },
    # 日系小清新：奶油底 + 马卡龙色 + 飘入
    "sakura-pop": {
        "style": {
            "palette": ["#3A3A46", "#FF6FA5", "#6FB3FF", "#63C9A8", "#F2A03D"],
            "weights": [4.0, 2.2, 2.0, 1.8, 1.4],
            "accent": "#FF4D8D",
            "accent_chance": 0.3,
            "stroke_color": "#FFFFFF",
            "stroke_width": 0.13,
            "highlight_box": True,
            "highlight_box_color": "#FFE1EE",
            "highlight_text_color": "#C2316A",
            "shadow": 0.25,
            "rotation_range": 5.0,
        },
        "motion": {
            "enter": "rise",
            "enter_duration": 0.42,
            "scroll": 0.46,
            "stagger": 0.07,
            "drift": 0.1,
            "rush_lines": False,
            "flash": False,
        },
        "camera": {"mode": "scroll+breathe", "breathe": 0.03, "shake": 0.04},
        "background": {
            "kind": "dots",
            "colors": ["#FFF7F1", "#FFE9F2"],
            "dot_color": "#FF9EC4",
            "dot_opacity": 0.18,
            "vignette": 0.12,
        },
        "font": {"base_size": 42.0, "size_range": [0.86, 1.0, 1.14, 1.3]},
    },
    # 电报/新闻：白底黑字 + 单一强调色
    "broadcast": {
        "style": {
            "fill": "#111111",
            "accent": "#E4002B",
            "accent_chance": 0.16,
            "stroke_color": "#FFFFFF",
            "stroke_width": 0.02,
            "highlight_box": True,
            "highlight_box_color": "#111111",
            "highlight_text_color": "#FFFFFF",
            "shadow": 0.0,
            "rotation_range": 0.0,
            "jitter_x": 0.0,
        },
        "motion": {
            "enter": "rise",
            "enter_duration": 0.24,
            "scroll": 0.28,
            "stagger": 0.03,
            "x_scatter": 0.0,
            "y_scatter": 0.0,
            "bow": 0.0,
            "rush_lines": False,
            "flash": False,
        },
        "camera": {"mode": "scroll", "breathe": 0.0, "shake": 0.0},
        "background": {"kind": "solid", "colors": ["#F7F7F5"], "vignette": 0.0},
        "font": {"base_size": 43.0, "size_range": [0.9, 1.0, 1.1, 1.24]},
        "layout": {"anchor_y": 0.68},
    },
    # 终端/极客：黑底绿字等宽感
    "neon-terminal": {
        "style": {
            "palette": ["#C8FFD4", "#7CFFB2", "#4CE0C8", "#E9FF70"],
            "weights": [4.0, 2.6, 1.8, 1.2],
            "accent": "#E9FF70",
            "accent_chance": 0.2,
            "stroke_color": "#04140C",
            "stroke_width": 0.07,
            "highlight_box": True,
            "highlight_box_color": "#4CE0C8",
            "highlight_text_color": "#04140C",
            "shadow": 0.9,
            "rotation_range": 1.2,
            "glow": True,
        },
        "motion": {
            "enter": "typewriter",
            "enter_duration": 0.22,
            "scroll": 0.26,
            "stagger": 0.10,
            "rush_lines": False,
            "flash": True,
            "flash_strength": 0.1,
        },
        "camera": {"mode": "scroll", "breathe": 0.02, "shake": 0.05},
        "background": {
            "kind": "dots",
            "colors": ["#04120B", "#071D12"],
            "dot_color": "#4CE0C8",
            "dot_opacity": 0.14,
            "dot_spacing": 40.0,
            "vignette": 0.5,
            "noise": 0.08,
        },
        "font": {"base_size": 39.0, "size_range": [0.84, 0.98, 1.1, 1.24]},
    },
    # 复古印刷：米黄纸 + 墨黑 + 描边
    "retro-print": {
        "style": {
            "palette": ["#1A1A1A", "#C0392B", "#1F4E79", "#7A5C2E"],
            "weights": [5.0, 1.4, 1.4, 1.0],
            "accent": "#C0392B",
            "accent_chance": 0.2,
            "stroke_color": "#F3E9D2",
            "stroke_width": 0.03,
            "highlight_box": True,
            "highlight_box_color": "#1A1A1A",
            "highlight_text_color": "#F3E9D2",
            "shadow": 0.15,
            "rotation_range": 2.0,
        },
        "motion": {
            "enter": "swing",
            "enter_duration": 0.36,
            "scroll": 0.4,
            "stagger": 0.06,
            "rush_lines": False,
            "flash": False,
        },
        "camera": {"mode": "scroll+breathe", "breathe": 0.025, "shake": 0.06},
        "background": {
            "kind": "noise",
            "colors": ["#F3E9D2", "#E8DAB8"],
            "noise": 0.16,
            "vignette": 0.22,
        },
        "font": {"base_size": 42.0, "size_range": [0.88, 1.0, 1.12, 1.3]},
    },
    # 音乐节拍卡点：颜色随节拍跳变
    "beat-flash": {
        "style": {
            "fill": "#FFFFFF",
            "accent": "#00E5FF",
            "accent_chance": 0.3,
            "stroke_color": "#000000",
            "stroke_width": 0.09,
            "highlight_box": True,
            "highlight_box_color": "#FF2E63",
            "highlight_text_color": "#FFFFFF",
            "shadow": 0.8,
            "rotation_range": 6.0,
        },
        "motion": {
            "enter": "random",
            "enter_duration": 0.18,
            "scroll": 0.2,
            "stagger": 0.04,
            "bow": 0.8,
            "rush_lines": True,
            "flash": True,
            "flash_strength": 0.3,
        },
        "camera": {"mode": "scroll+bounce", "breathe": 0.09, "shake": 0.22},
        "background": {
            "kind": "radial",
            "colors": ["#20003A", "#05000C"],
            "beats": ["#FF2E63", "#00E5FF", "#7C4DFF", "#FFD400"],
            "vignette": 0.45,
        },
        "font": {"base_size": 47.0, "size_range": [0.8, 1.0, 1.26, 1.55]},
        "layout": {"anchor_y": 0.64, "max_live": 12},
    },
}

DEFAULT_PRESET = "meme-punch"


def load_config(
    preset: str | None = None,
    config_path: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> RenderConfig:
    """Build a config from preset -> json file -> overrides, in that order."""
    data: dict[str, Any] = {}
    if preset:
        if preset not in PRESETS:
            raise KeyError(f"unknown preset {preset!r}; available: {', '.join(sorted(PRESETS))}")
        data = json.loads(json.dumps(PRESETS[preset]))  # deep copy
    if config_path:
        _deep_update(data, json.loads(Path(config_path).read_text(encoding="utf-8")))
    if overrides:
        _deep_update(data, overrides)
    return RenderConfig.from_dict(data)


def _deep_update(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base
