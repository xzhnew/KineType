"""Small shared helpers: easing, timing, colour maths, geometry."""

from __future__ import annotations

import math
import random as _random
from typing import Iterable, Sequence


# --------------------------------------------------------------------------- #
# easing
# --------------------------------------------------------------------------- #
def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if value < lo else hi if value > hi else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(t: float) -> float:
    t = clamp(t)
    return t * t * (3.0 - 2.0 * t)


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1.0 - (1.0 - t) ** 3


def ease_in_cubic(t: float) -> float:
    t = clamp(t)
    return t**3


def ease_out_back(t: float, s: float = 1.9) -> float:
    """Overshoot then settle – the classic 'pop'."""
    t = clamp(t)
    c3 = s + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + s * (t - 1.0) ** 2


def ease_out_elastic(t: float, amplitude: float = 0.22, period: float = 0.42) -> float:
    t = clamp(t)
    if t in (0.0, 1.0):
        return t
    return 1.0 + amplitude * math.pow(2, -9 * t) * math.sin((t - period / 4) * (2 * math.pi) / period)


def ease_out_expo(t: float) -> float:
    t = clamp(t)
    return 1.0 if t >= 1.0 else 1.0 - math.pow(2, -10 * t)


#: exponential decay "cushion" – f(0)=0, f(inf)=1
def cushion(t: float, ease: float = 0.7) -> float:
    """Saturating ease-out, normalised so it is ~97 % done at ``t == 1``.

    ``ease`` behaves like a time constant in multiples of the caller's reference
    duration: smaller settles faster.  The normalisation matters because every past
    beat keeps contributing a decaying amount of motion – with a long tail the
    *sum* of those contributions overshoots the true grid position badly.
    """
    if t <= 0:
        return 0.0
    ease = max(0.05, min(4.0, ease))
    return 1.0 - math.exp(-3.5 * t / ease)


EASINGS = {
    "linear": lambda t: clamp(t),
    "smooth": smoothstep,
    "out-cubic": ease_out_cubic,
    "out-back": ease_out_back,
    "out-elastic": ease_out_elastic,
    "out-expo": ease_out_expo,
    "in-cubic": ease_in_cubic,
}


# --------------------------------------------------------------------------- #
# weighted random
# --------------------------------------------------------------------------- #
class Rng:
    """Deterministic RNG wrapper – one seed reproduces the whole video."""

    def __init__(self, seed: int = 0) -> None:
        self.seed = int(seed)
        self._rng = _random.Random(self.seed)

    def stream(self, name: str) -> "_random.Random":
        """Independent stream so adding features never shuffles other choices."""
        return _random.Random(f"{self.seed}:{name}")

    def uniform(self, lo: float, hi: float) -> float:
        return self._rng.uniform(lo, hi)

    def choice(self, items: Sequence):
        return self._rng.choice(list(items))

    def weighted(self, items: Sequence, weights: Sequence[float]):
        if not items:
            raise ValueError("weighted choice from an empty sequence")
        if len(items) != len(weights):
            weights = [1.0] * len(items)
        total = float(sum(weights))
        if total <= 0:
            return self._rng.choice(list(items))
        pick = self._rng.random() * total
        upto = 0.0
        for item, weight in zip(items, weights):
            upto += float(weight)
            if pick <= upto:
                return item
        return items[-1]

    def sign(self) -> float:
        return 1.0 if self._rng.random() < 0.5 else -1.0


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def rotate_point(x: float, y: float, deg: float, cx: float = 0.0, cy: float = 0.0) -> tuple[float, float]:
    rad = math.radians(deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy = x - cx, y - cy
    return (cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)


def fill_round_rect(draw, box, radius: float, fill) -> None:
    draw.rounded_rectangle(box, radius=max(0.0, float(radius)), fill=fill)


def hex_to_rgb_floats(value: str) -> tuple[float, float, float]:
    from .config import rgb

    r, g, b = rgb(value)
    return (r / 255.0, g / 255.0, b / 255.0)


def mix(c1: Sequence[int], c2: Sequence[int], t: float) -> tuple[int, int, int]:
    t = clamp(t)
    return (
        int(round(lerp(c1[0], c2[0], t))),
        int(round(lerp(c1[1], c2[1], t))),
        int(round(lerp(c1[2], c2[2], t))),
    )


def with_alpha(color: Sequence[int], alpha: float) -> tuple[int, ...]:
    a = int(round(clamp(alpha) * 255))
    if len(color) == 4:
        return (color[0], color[1], color[2], min(a, int(color[3])))
    return (color[0], color[1], color[2], a)


# --------------------------------------------------------------------------- #
# text metrics helpers
# --------------------------------------------------------------------------- #
def is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x2E80 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0xFE30 <= code <= 0xFE4F
        or 0xFF00 <= code <= 0xFF60
        or 0xFFE0 <= code <= 0xFFE6
        or 0x3000 <= code <= 0x303F
    )


def cjk_ratio(text: str) -> float:
    letters = [ch for ch in text if not ch.isspace()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if is_cjk(ch)) / len(letters)


def visual_width(text: str) -> float:
    """Rough advance width in 'em' units (CJK = 1, latin ≈ 0.55)."""
    total = 0.0
    for ch in text:
        if ch.isspace():
            total += 0.35
        elif is_cjk(ch):
            total += 1.0
        elif ch.isupper():
            total += 0.66
        elif ch.isdigit():
            total += 0.56
        elif ch in ".,:;!?'\"|iIljft()[]":
            total += 0.30
        else:
            total += 0.54
    return total


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m, s = divmod(seconds, 60.0)
    h, m = divmod(int(m), 60)
    if h:
        return f"{h:d}:{m:02d}:{s:05.2f}"
    return f"{m:02d}:{s:05.2f}"


def chunked(items: Iterable, size: int) -> list[list]:
    out: list[list] = []
    bucket: list = []
    for item in items:
        bucket.append(item)
        if len(bucket) >= size:
            out.append(bucket)
            bucket = []
    if bucket:
        out.append(bucket)
    return out
