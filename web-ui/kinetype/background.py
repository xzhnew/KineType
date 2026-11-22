"""Procedural background generation (cached – the renderer never re-does this)."""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from .config import BackgroundConfig, rgb
from .util import clamp, mix, smoothstep, with_alpha


def build_background(cfg: BackgroundConfig, size: tuple[int, int], seed: int = 0) -> Image.Image:
    """Return the opaque base background."""
    width, height = size
    kind = cfg.kind
    colors = [rgb(c) for c in (cfg.colors or ["#000000"])]
    if len(colors) == 1:
        colors = [colors[0], colors[0]]

    if kind == "solid":
        base = Image.new("RGB", size, colors[0])
    elif kind == "radial":
        base = _radial(size, colors[0], colors[1])
    elif kind == "gradient":
        base = _linear(size, colors, cfg.angle)
    elif kind in {"dots", "noise"}:
        base = _linear(size, colors, cfg.angle)
    else:
        raise ValueError(f"unknown background kind {kind!r}")

    if kind == "dots":
        base = _dots(base, cfg)
    if kind in {"noise", "dots"} or cfg.noise > 0:
        amount = cfg.noise if kind != "dots" else cfg.noise
        if amount > 0:
            base = _noise(base, amount, seed)
    if cfg.vignette > 0:
        base = _vignette(base, cfg.vignette)
    if cfg.bar_height > 0:
        base = _bars(base, cfg)
    return base.convert("RGB")


def tinted(base: Image.Image, color: str, strength: float) -> Image.Image:
    """Screen-blend ``color`` over ``base`` – used for on-beat colour flashes."""
    strength = clamp(strength)
    if strength <= 0.001:
        return base
    overlay = Image.new("RGB", base.size, rgb(color))
    return Image.blend(base, Image.blend(base, overlay, 0.55), strength)


# --------------------------------------------------------------------------- #


def _linear(size: tuple[int, int], colors: list[tuple[int, int, int]], angle: float) -> Image.Image:
    """Two-stop (or multi-stop) linear gradient rendered by rotating a strip."""
    width, height = size
    stops = colors[:4]
    span = int(max(width, height) * 1.5)
    strip = Image.new("RGB", (span, 1))
    draw = ImageDraw.Draw(strip)
    n = len(stops) - 1
    for x in range(span):
        t = x / max(1, span - 1)
        pos = t * n
        i = min(n - 1, int(pos))
        local = pos - i
        draw.point((x, 0), fill=mix(stops[i], stops[i + 1], smoothstep(local)))
    strip = strip.resize((span, span), Image.Resampling.BILINEAR)
    strip = strip.rotate(-angle + 90.0, resample=Image.Resampling.BICUBIC, expand=False)
    left = (span - width) // 2
    top = (span - height) // 2
    return strip.crop((left, top, left + width, top + height))


def _radial(size: tuple[int, int], inner: tuple[int, int, int], outer: tuple[int, int, int]) -> Image.Image:
    width, height = size
    small = (max(8, width // 24), max(8, height // 24))
    mask = Image.new("L", small, 0)
    pixels = mask.load()
    cx, cy = (small[0] - 1) / 2.0, (small[1] - 1) / 2.0
    max_d = math.hypot(cx, cy)
    for y in range(small[1]):
        for x in range(small[0]):
            d = math.hypot(x - cx, y - cy) / max_d
            pixels[x, y] = int(255 * clamp(d) ** 1.15)
    mask = mask.resize(size, Image.Resampling.BICUBIC)
    return Image.composite(Image.new("RGB", size, outer), Image.new("RGB", size, inner), mask)


def _dots(base: Image.Image, cfg: BackgroundConfig) -> Image.Image:
    width, height = base.size
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    color = with_alpha(rgb(cfg.dot_color), cfg.dot_opacity)
    spacing = max(6.0, cfg.dot_spacing)
    radius = max(0.5, cfg.dot_radius)
    y = spacing / 2
    row = 0
    while y < height:
        x = spacing / 2 + (spacing / 2 if row % 2 else 0.0)
        while x < width:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
            x += spacing
        y += spacing
        row += 1
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def _noise(base: Image.Image, amount: float, seed: int) -> Image.Image:
    """Cheap grain: a small noise tile resized up, blended in."""
    width, height = base.size
    scale = max(2, min(5, round(min(width, height) / 260)))
    small = (max(4, width // scale), max(4, height // scale))
    rng = random.Random(seed * 7919 + 13)
    grey = Image.new("L", small)
    grey.putdata([rng.randrange(256) for _ in range(small[0] * small[1])])
    grey = grey.resize(base.size, Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(0.6))
    layer = Image.merge("RGB", (grey, grey, grey))
    return Image.blend(base, Image.blend(base, layer, 0.5), clamp(amount))


def _vignette(base: Image.Image, strength: float) -> Image.Image:
    width, height = base.size
    small = (max(8, width // 24), max(8, height // 24))
    mask = Image.new("L", small, 0)
    pixels = mask.load()
    cx, cy = (small[0] - 1) / 2.0, (small[1] - 1) / 2.0
    max_d = math.hypot(cx, cy)
    for y in range(small[1]):
        for x in range(small[0]):
            d = math.hypot(x - cx, y - cy) / max_d
            falloff = smoothstep(clamp((d - 0.35) / 0.65))
            pixels[x, y] = int(255 * clamp(falloff) * clamp(strength))
    mask = mask.resize(base.size, Image.Resampling.BICUBIC)
    return Image.composite(Image.new("RGB", base.size, (0, 0, 0)), base, mask)


def _bars(base: Image.Image, cfg: BackgroundConfig) -> Image.Image:
    width, height = base.size
    draw = ImageDraw.Draw(base)
    bar = max(1, int(cfg.bar_height * height))
    color = rgb(cfg.bar_color)
    draw.rectangle((0, 0, width, bar), fill=color)
    draw.rectangle((0, height - bar, width, height), fill=color)
    return base
