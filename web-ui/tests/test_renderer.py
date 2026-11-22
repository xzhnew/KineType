"""Renderer tests: sprites, waterfall motion, determinism, ffmpeg output."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from kinetype.fonts import FontSet
from kinetype.layout import LayoutEngine
from kinetype.renderer import Renderer, StackMotion
from kinetype.script import assign_timeline, chunks_from_text


def _program(cfg, text: str, target: float | None = None):
    chunks = chunks_from_text(text, cfg)
    duration = assign_timeline(chunks, cfg, target=target)
    renderer = Renderer(cfg)
    return renderer, renderer.prepare(chunks, duration, [])


# --------------------------------------------------------------------------- #
# layout / sprites
# --------------------------------------------------------------------------- #
def test_blocks_render_opaque_glyphs(small_cfg):
    chunks = chunks_from_text("就是那个，[倒]了。", small_cfg)
    engine = LayoutEngine(small_cfg, FontSet(small_cfg.font), small_cfg.seed)
    blocks = engine.make_blocks(chunks, (small_cfg.output.width, small_cfg.output.height))
    assert blocks, "no block was produced"
    for block in blocks:
        assert block.image.width > 0 and block.image.height > 0
        alpha = np.array(block.image)[..., 3]
        assert alpha.max() == 255
        # a highlight box plus glyphs must leave more than a sliver of ink
        assert int((alpha > 128).sum()) > block.image.width
    # the highlighted beat is the one that gets a filler box, so it must be dense
    filled = max(blocks, key=lambda b: int((np.array(b.image)[..., 3] > 128).sum()))
    assert filled.metrics[1] > filled.metrics[0]


def test_long_beat_wraps_into_multiple_rows(small_cfg):
    chunks = chunks_from_text("先生，您能描述一下现场的具体情况吗？", small_cfg)
    engine = LayoutEngine(small_cfg, FontSet(small_cfg.font), small_cfg.seed)
    block = engine.make_blocks(chunks, (small_cfg.output.width, small_cfg.output.height))[0]
    assert block.rows >= 1
    margin = small_cfg.output.width * (1 - 2 * small_cfg.layout.margin_x) * small_cfg.font.max_line_width
    assert block.image.width <= margin * 1.12


def test_short_beat_is_rendered_large(small_cfg):
    engine = LayoutEngine(small_cfg, FontSet(small_cfg.font), small_cfg.seed)
    size = (small_cfg.output.width, small_cfg.output.height)
    short = engine.make_blocks(chunks_from_text("喂。", small_cfg), size)[0]
    long = engine.make_blocks(chunks_from_text("先生，您能描述一下现场情况吗？", small_cfg), size)[0]
    assert short.font_size > long.font_size


def test_sprite_geometry_is_deterministic(small_cfg):
    engine = LayoutEngine(small_cfg, FontSet(small_cfg.font), small_cfg.seed)
    size = (small_cfg.output.width, small_cfg.output.height)
    first = engine.make_blocks(chunks_from_text("一二三四五六七八。", small_cfg), size)[0]
    second = LayoutEngine(small_cfg, FontSet(small_cfg.font), small_cfg.seed).make_blocks(
        chunks_from_text("一二三四五六七八。", small_cfg), size
    )[0]
    assert first.image.size == second.image.size
    assert np.array_equal(np.array(first.image), np.array(second.image))


# --------------------------------------------------------------------------- #
# motion
# --------------------------------------------------------------------------- #
def test_crawl_saturates_between_zero_and_one(small_cfg):
    renderer, program = _program(small_cfg, "一句话。\n\n又一句话。\n\n第三句话。", target=4.0)
    motion: StackMotion = renderer._motion(program)
    last = len(motion.tops) - 1
    arrival = motion.tops[last]
    assert motion.ramp(arrival) == pytest.approx(0.0, abs=1e-6)
    assert motion.ramp(arrival + renderer._scroll_seconds() * 0.5) > 0.5
    assert motion.ramp(arrival + renderer._scroll_seconds() * 12) == pytest.approx(1.0, abs=1e-3)


def test_a_beat_only_ever_travels_upward(small_cfg):
    renderer, program = _program(
        small_cfg,
        "第一句话。\n\n第二句话。\n\n第三句话。\n\n第四句话。\n\n第五句话。",
        target=6.0,
    )
    motion = renderer._motion(program)
    for index in (0, 1, 2):
        climbs = []
        for t in np.linspace(motion.tops[index], program.duration, 120):
            active = renderer._active(float(t), program)
            if not active or index not in active:
                continue
            climbs.append(renderer._climb(index, active[-1], float(t), program, motion))
        assert climbs == sorted(climbs), f"beat {index} moved backwards"
        assert climbs[-1] >= climbs[0]
        assert climbs[-1] <= sum(motion.heights), "travel exceeded every slot on screen"


def test_stack_height_stays_bounded(small_cfg):
    """Guards the regression where a global travel counter pushed every beat off the
    top of the frame."""
    renderer, program = _program(
        small_cfg,
        "\n\n".join(f"第{i}句台词内容。" for i in range(40)),
        target=30.0,
    )
    motion = renderer._motion(program)
    window = sum(motion.heights[: small_cfg.layout.max_live])
    peak = 0.0
    for t in np.linspace(0.0, program.duration, 120):
        active = renderer._active(float(t), program)
        if len(active) < 2:
            continue
        peak = max(peak, renderer._climb(active[0], active[-1], float(t), program, motion))
    assert 0 < peak <= window, f"stack grew to {peak:.0f}px, visible window is {window:.0f}px"


def test_text_is_actually_on_screen_mid_video(small_cfg, sample_text):
    """The whole point: a beat must land inside the frame, not above it."""
    renderer, program = _program(small_cfg, sample_text, target=20.0)
    height = small_cfg.output.height
    for t in np.linspace(1.0, program.duration - 1.0, 24):
        active = renderer._active(float(t), program)
        assert active, f"no beat alive at {t:.2f}s"
        newest = active[-1]
        anchor = height * small_cfg.layout.anchor_y * renderer.scale
        climb = renderer._climb(newest, newest, float(t), program, renderer._motion(program))
        assert 0 <= anchor - climb <= height * renderer.scale


def test_newest_beat_lands_on_the_anchor_then_earns_its_slot(small_cfg):
    renderer, program = _program(small_cfg, "一。\n\n二。\n\n三。\n\n四。", target=5.0)
    motion = renderer._motion(program)
    last = len(motion.tops) - 1
    arrival = motion.tops[last]
    # at the instant it lands the incoming beat has climbed nothing at all
    assert motion.ramp(arrival) == pytest.approx(0.0, abs=1e-6)
    assert renderer._climb(last - 1, last, arrival, program, motion) == pytest.approx(0.0, abs=1e-6)
    # one scroll constant later the beat below it has climbed by about one slot
    settled = renderer._climb(last - 1, last, arrival + renderer._scroll_seconds() * 12, program, motion)
    assert settled == pytest.approx(motion.height(last), rel=0.02)


def test_old_beats_leave_the_frame_instead_of_piling_up(small_cfg):
    """The whole stack must stay bounded – the bug this guards against scrolled
    everything off the top of the frame."""
    renderer, program = _program(
        small_cfg,
        "\n\n".join(f"第{i}句台词内容。" for i in range(40)),
        target=30.0,
    )
    motion = renderer._motion(program)
    span = self_max = sum(motion.heights[: small_cfg.layout.max_live])
    peak = 0.0
    for t in np.linspace(0.0, program.duration, 120):
        active = renderer._active(float(t), program)
        if not active:
            continue
        climb = renderer._climb(active[0], active[-1], float(t), program, motion)
        peak = max(peak, climb)
    assert peak <= span, f"stack grew to {peak:.0f}px, visible window is {span:.0f}px"


def test_only_a_handful_of_beats_are_alive_at_once(small_cfg, sample_text):
    renderer, program = _program(small_cfg, sample_text)
    peak = 0
    for t in np.linspace(0, program.duration, 60):
        peak = max(peak, len(renderer._active(float(t), program)))
    assert 2 <= peak <= small_cfg.layout.max_live


# --------------------------------------------------------------------------- #
# frames
# --------------------------------------------------------------------------- #
def test_frame_is_the_requested_size_and_seed_stable(small_cfg, sample_text):
    renderer, program = _program(small_cfg, sample_text, target=6.0)
    a = renderer.frame(1.0, program)
    b = renderer.frame(1.0, program)
    assert a.size == (small_cfg.output.width, small_cfg.output.height)
    assert a.mode == "RGB"
    assert np.array_equal(np.array(a), np.array(b))


def test_different_seeds_give_different_frames(small_cfg, sample_text):
    renderer_a, program_a = _program(small_cfg, sample_text, target=6.0)
    small_cfg.seed = small_cfg.seed + 7
    renderer_b, program_b = _program(small_cfg, sample_text, target=6.0)
    assert not np.array_equal(np.array(renderer_a.frame(1.4, program_a)), np.array(renderer_b.frame(1.4, program_b)))


def test_frames_are_not_blank(small_cfg, sample_text):
    renderer, program = _program(small_cfg, sample_text, target=8.0)
    for t in (0.6, 2.0, 4.0, 6.5):
        frame = np.array(renderer.frame(t, program)).astype(int)
        assert frame.std() > 6.0, f"frame at {t}s looks empty"
        assert frame.max() > 150, f"frame at {t}s has no bright text"


def test_text_moves_between_consecutive_frames(small_cfg, sample_text):
    renderer, program = _program(small_cfg, sample_text, target=6.0)
    a = np.array(renderer.frame(0.45, program)).astype(np.int16)
    b = np.array(renderer.frame(1.60, program)).astype(np.int16)
    assert np.abs(a - b).mean() > 0.5, "the frame does not change over time – no animation"


def test_empty_script_is_rejected(small_cfg):
    with pytest.raises(ValueError):
        _program(small_cfg, "   \n\n  ")


# --------------------------------------------------------------------------- #
# end to end
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_render_writes_a_playable_mp4(small_cfg, sample_text, tmp_path):
    renderer, program = _program(small_cfg, sample_text, target=2.0)
    out = tmp_path / "out.mp4"
    result = renderer.write(program, out, quiet=True)
    assert Path(result).is_file()
    assert Path(result).stat().st_size > 2000
    probe = shutil.which("ffprobe")
    if probe:
        import subprocess

        raw = subprocess.run(
            [probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,nb_frames", "-of", "default=nw=1", str(out)],
            capture_output=True, text=True, check=True,
        ).stdout
        assert "width=270" in raw and "height=480" in raw


def test_stills_mode_writes_pngs(small_cfg, sample_text, tmp_path):
    renderer, program = _program(small_cfg, sample_text, target=2.0)
    result = renderer.write(program, tmp_path / "still.png", stills=3)
    paths = [Path(p) for p in result.splitlines()]
    assert len(paths) == 3
    for path in paths:
        assert path.is_file()
        image = Image.open(path)
        assert image.size == (small_cfg.output.width, small_cfg.output.height)
