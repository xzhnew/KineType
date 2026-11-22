"""Config, colour parsing, presets and JSON round-trip tests."""

from __future__ import annotations

import json

import pytest

from kinetype.config import (
    DEFAULT_PRESET,
    PRESETS,
    RenderConfig,
    load_config,
    parse_color,
    rgb,
)


def test_parse_color_accepts_every_documented_form():
    assert parse_color("#FFD84D") == (255, 216, 77)
    assert parse_color("FFD84D") == (255, 216, 77)
    assert parse_color("#fd4") == (255, 221, 68)
    assert parse_color("yellow") == (255, 216, 77)
    assert parse_color([1, 2, 3]) == (1, 2, 3)
    assert parse_color("#11223344") == (17, 34, 51, 68)
    assert parse_color("rgb(10,20,30)") == (10, 20, 30)


def test_parse_color_rejects_nonsense():
    with pytest.raises(ValueError):
        parse_color("not-a-colour")


def test_rgb_strips_alpha():
    assert rgb("#FFD84D80") == (255 * 0x80 // 255, 216 * 0x80 // 255, 77 * 0x80 // 255)


def test_every_preset_loads_and_validates():
    for name in PRESETS:
        cfg = load_config(name)
        assert cfg.validate() == [], f"{name} has invalid fields"


def test_default_preset_exists():
    assert DEFAULT_PRESET in PRESETS


def test_unknown_preset_is_rejected():
    with pytest.raises(KeyError):
        load_config("does-not-exist")


def test_unknown_key_is_rejected():
    with pytest.raises(KeyError):
        load_config(DEFAULT_PRESET, None, {"style": {"nope": 1}})


def test_json_round_trip_is_lossless(tmp_path):
    cfg = load_config("beat-flash")
    cfg.style.accent = "#00E5FF"
    cfg.output.fps = 24
    path = tmp_path / "c.json"
    cfg.to_json(path)
    again = RenderConfig.from_json(path)
    assert again.to_dict() == cfg.to_dict()
    assert again.style.accent == "#00E5FF"


def test_layering_order_is_preset_then_file_then_cli(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"style": {"accent": "#111111"}, "output": {"fps": 25}}), encoding="utf-8")
    cfg = load_config("meme-punch", str(path), {"style": {"accent": "#222222"}})
    assert cfg.style.accent == "#222222"   # CLI wins
    assert cfg.output.fps == 25            # file wins over preset


def test_validate_flags_bad_values():
    cfg = RenderConfig()
    cfg.output.fps = 0
    cfg.text.chunk_mode = "nonsense"
    cfg.motion.exit = "explode"
    problems = cfg.validate()
    assert len(problems) >= 3


def test_preset_palettes_match_their_weight_lists():
    for name in PRESETS:
        cfg = load_config(name)
        assert len(cfg.style.palette) == len(cfg.style.weights), name
        assert len(cfg.font.size_range) == len(cfg.font.size_weights), name
