"""CLI tests – the commands users actually type."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from kinetype.cli import _coerce, _overrides, main


def test_presets_command_lists_every_look(capsys):
    assert main(["presets"]) == 0
    out = capsys.readouterr().out
    for name in ("meme-punch", "beat-flash", "neon-terminal", "sakura-pop", "broadcast", "retro-print"):
        assert name in out


def test_presets_json_is_valid(capsys):
    assert main(["presets", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "meme-punch" in data


def test_fonts_command_reports_paths(capsys):
    assert main(["fonts"]) == 0
    out = capsys.readouterr().out
    assert "CJK:" in out and "latin:" in out


def test_dry_run_prints_a_beat_sheet(sample_path, capsys):
    assert main(["render", str(sample_path), "--dry-run", "-p", "meme-punch"]) == 0
    out = capsys.readouterr().out
    assert "beats" in out
    assert "倒鸭子" in out


def test_overrides_parse_types_and_nesting():
    data = _overrides(["style.accent=#FF2E63", "motion.scroll=0.24", "output.fps=30", "style.glow=true"])
    assert data["style"]["accent"] == "#FF2E63"
    assert data["motion"]["scroll"] == pytest.approx(0.24)
    assert data["output"]["fps"] == 30
    assert data["style"]["glow"] is True


def test_coerce_handles_lists_and_bools():
    assert _coerce("true") is True
    assert _coerce("3") == 3
    assert _coerce("2.5") == pytest.approx(2.5)
    assert _coerce("#fff") == "#fff"
    assert _coerce('["#a","#b"]') == ["#a", "#b"]


def test_bad_override_syntax_exits():
    with pytest.raises(SystemExit):
        _overrides(["nonsense"])


def test_dump_config_round_trips(tmp_path, sample_path, capsys):
    out = tmp_path / "c.json"
    assert main(["render", str(sample_path), "--dry-run", "--dump-config", str(out)]) == 0
    capsys.readouterr()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["output"]["width"] == 1080
    assert "motion" in data


def test_preview_writes_stills(tmp_path, sample_path, capsys):
    out = tmp_path / "p.png"
    assert main(["preview", str(sample_path), "-n", "2", "--size", "180x320", "--out", str(out)]) == 0
    capsys.readouterr()
    made = sorted(tmp_path.glob("p_*.png"))
    assert len(made) == 2
    assert all(p.stat().st_size > 500 for p in made)


def test_unknown_preset_is_rejected():
    with pytest.raises(SystemExit):
        main(["render", "hello", "-p", "not-a-preset"])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_sheet_command_makes_a_contact_sheet(tmp_path, sample_path, capsys):
    video = tmp_path / "v.mp4"
    assert main(["render", str(sample_path), "--size", "180x320", "--fps", "12",
                 "--duration", "2", "-q", "-o", str(video)]) == 0
    out = tmp_path / "sheet.png"
    assert main(["sheet", str(video), "-n", "4", "-o", str(out), "--cols", "2"]) == 0
    capsys.readouterr()
    assert out.is_file()
    image = Image.open(out)
    assert image.width > 0 and image.height > 0


def test_demo_command_uses_the_bundled_script(tmp_path, capsys):
    out = tmp_path / "d.png"
    assert main(["demo", "--stills", "1", "-o", str(out)]) == 0
    capsys.readouterr()
    assert list(tmp_path.glob("d_*.png"))


@pytest.fixture()
def sample_path(root: Path) -> Path:
    return root / "samples" / "daoyazi.zh.txt"
