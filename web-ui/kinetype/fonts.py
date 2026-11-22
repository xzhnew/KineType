"""Font resolution and small text-drawing helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .config import FontConfig
from .util import cjk_ratio

#: directories scanned when a config entry is a bare family name
SEARCH_DIRS = [
    "C:/Windows/Fonts",
    os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts"),
    "/System/Library/Fonts",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.local/share/fonts"),
    ".",
]

_EXT = {".ttf", ".otf", ".ttc", ".otc", ".TTF", ".OTF", ".TTC"}


def _fuzzy_find(name: str) -> str | None:
    """Best-effort lookup of a font file from a family name."""
    needle = "".join(ch for ch in name.lower() if ch.isalnum())
    if len(needle) < 3:
        return None
    for folder in SEARCH_DIRS:
        base = Path(folder)
        if not base.is_dir():
            continue
        try:
            entries = list(base.rglob("*"))
        except OSError:
            continue
        for entry in entries:
            if entry.suffix not in _EXT:
                continue
            hay = "".join(ch for ch in entry.stem.lower() if ch.isalnum())
            if needle in hay or hay in needle:
                return str(entry)
    return None


@lru_cache(maxsize=256)
def _load(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


class FontSet:
    """Resolves the CJK / latin faces once, then hands out sized fonts."""

    def __init__(self, cfg: FontConfig) -> None:
        self.cfg = cfg
        self.cjk_path = self._resolve(cfg.cjk, "CJK")
        self.latin_path = self._resolve(cfg.latin, "latin") or self.cjk_path

    @staticmethod
    def _resolve(candidates: list[str], label: str) -> str | None:
        for candidate in candidates:
            path = Path(candidate)
            if path.is_file():
                return str(path)
            found = _fuzzy_find(candidate)
            if found:
                return found
        return None

    def for_text(self, text: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        size = max(6, int(round(size)))
        if not text.strip():
            return _load(self.cjk_path or self.latin_path, size)  # type: ignore[arg-type]
        path = self.cjk_path if cjk_ratio(text) > 0.25 else self.latin_path
        if bold and path == self.latin_path:
            path = self._latin_bold() or path
        return _load(path, size)  # type: ignore[arg-type]

    def _latin_bold(self) -> str | None:
        for candidate in self.cfg.latin:
            low = Path(candidate).name.lower()
            if "black" in low or "bold" in low or "bd" in low:
                path = Path(candidate)
                if path.is_file():
                    return str(path)
        return None

    def describe(self) -> str:
        return f"CJK: {self.cjk_path or '<none found>'}\nlatin: {self.latin_path or '<none found>'}"

    def require(self) -> None:
        if not self.cjk_path and not self.latin_path:
            raise RuntimeError(
                "no usable font found – pass --font-cjk / --font-latin with an explicit .ttf/.ttc path"
            )


def text_bbox(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int, int, int]:
    return font.getbbox(text)


def advance(font: ImageFont.FreeTypeFont, text: str) -> float:
    try:
        return float(font.getlength(text))
    except AttributeError:  # pragma: no cover – very old Pillow
        return float(font.getsize(text)[0])
