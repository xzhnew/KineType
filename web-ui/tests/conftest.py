"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kinetype.config import RenderConfig, load_config  # noqa: E402


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture()
def small_cfg() -> RenderConfig:
    """A config that renders fast enough for tests (tiny canvas, low fps)."""
    cfg = load_config("meme-punch")
    cfg.output.width = 270
    cfg.output.height = 480
    cfg.output.fps = 12
    cfg.font.base_size = 44.0
    cfg.layout.max_live = 6
    return cfg


@pytest.fixture(scope="session")
def sample_text(root: Path) -> str:
    return (root / "samples" / "daoyazi.zh.txt").read_text(encoding="utf-8")
