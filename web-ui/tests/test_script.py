"""Script parsing, beat segmentation and timing tests."""

from __future__ import annotations

import pytest

from kinetype.script import (
    Chunk,
    Key,
    assign_timeline,
    chunks_from_text,
    load_json_script,
    load_srt,
    parse_inline,
)


# --------------------------------------------------------------------------- #
# inline markup
# --------------------------------------------------------------------------- #
def test_cjk_segments_never_drop_characters():
    keys = parse_inline("倒鸭子")
    assert "".join(k.text for k in keys) == "倒鸭子"


def test_punctuation_is_glued_to_the_previous_key():
    keys = parse_inline("它倒了。")
    assert "".join(k.text for k in keys) == "它倒了。"
    assert keys[-1].text.endswith("。")
    assert all(k.text.strip() for k in keys), "no punctuation-only keys allowed"


def test_latin_words_keep_their_spacing():
    keys = parse_inline("the insurance company")
    joined = "".join(k.text for k in keys)
    assert joined.strip() == "the insurance company"
    assert "the " in joined


def test_highlight_bold_and_colour_markup():
    keys = parse_inline("[倒]了 *真的* {#FF0000:红色}")
    by_text = {k.text: k for k in keys if k.text.strip()}
    assert any(k.highlight and k.text == "倒" for k in keys)
    assert any(k.bold and k.text == "真的" for k in keys)
    assert any(k.color and k.color.upper().endswith("FF0000") for k in keys)
    assert by_text


def test_escaped_brackets_are_literal():
    keys = parse_inline(r"\[不是高亮\]")
    assert "".join(k.text for k in keys) == "[不是高亮]"
    assert not any(k.highlight for k in keys)


def test_line_break_markup_produces_two_rows():
    keys = parse_inline("上半|下半")
    assert any(k.newline for k in keys)


# --------------------------------------------------------------------------- #
# segmentation
# --------------------------------------------------------------------------- #
def test_blank_lines_make_hard_beat_breaks(small_cfg):
    chunks = chunks_from_text("第一段话。\n\n第二段话。", small_cfg)
    assert len(chunks) == 2


def test_comment_lines_are_ignored(small_cfg):
    chunks = chunks_from_text("# a comment\n真正的内容。", small_cfg)
    assert len(chunks) == 1
    assert chunks[0].plain == "真正的内容。"


def test_every_character_survives_segmentation(small_cfg, sample_text):
    chunks = chunks_from_text(sample_text, small_cfg)
    kept_lines = [ln for ln in sample_text.split("\n") if not ln.lstrip().startswith("#")]
    body = "".join(kept_lines)
    for markup in ("[", "]", "**", "|"):
        body = body.replace(markup, "")
    seen = "".join(c.plain for c in chunks)
    stripped = "".join(ch for ch in seen if not ch.isspace())
    expected = "".join(ch for ch in body if not ch.isspace())
    assert stripped == expected


def test_beats_are_short_enough_to_read(small_cfg, sample_text):
    chunks = chunks_from_text(sample_text, small_cfg)
    assert 20 <= len(chunks) <= 60
    for chunk in chunks:
        glyphs = sum(1 for ch in chunk.plain if not ch.isspace())
        assert glyphs <= 30, f"beat too long: {chunk.plain!r}"


def test_tight_mode_makes_more_beats_than_wide(small_cfg, sample_text):
    small_cfg.text.chunk_mode = "tight"
    tight = chunks_from_text(sample_text, small_cfg)
    small_cfg.text.chunk_mode = "wide"
    wide = chunks_from_text(sample_text, small_cfg)
    assert len(tight) > len(wide)


def test_latin_script_segments_by_words(small_cfg, root):
    text = (root / "samples" / "daoyazi.en.txt").read_text(encoding="utf-8")
    chunks = chunks_from_text(text, small_cfg)
    assert len(chunks) > 10
    for chunk in chunks:
        assert len(chunk.plain.split()) <= small_cfg.text.max_keys + 2


# --------------------------------------------------------------------------- #
# timing
# --------------------------------------------------------------------------- #
def test_timeline_is_monotonic_and_ordered(small_cfg, sample_text):
    chunks = chunks_from_text(sample_text, small_cfg)
    total = assign_timeline(chunks, small_cfg)
    assert total > 1.0
    previous_end = -1.0
    for chunk in chunks:
        assert chunk.start >= previous_end - 1e-9
        assert chunk.end > chunk.start
        previous_end = chunk.end
    assert total >= chunks[-1].start


def test_target_duration_is_respected(small_cfg, sample_text):
    chunks = chunks_from_text(sample_text, small_cfg)
    total = assign_timeline(chunks, small_cfg, target=12.0)
    assert total == pytest.approx(12.0, rel=0.02)


def test_long_beat_gets_more_reading_time(small_cfg):
    chunks = chunks_from_text("短。\n\n这是一段明显更长的句子内容。", small_cfg)
    assign_timeline(chunks, small_cfg)
    assert chunks[1].duration > chunks[0].duration


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def test_srt_loader_uses_file_timings(tmp_path):
    srt = tmp_path / "a.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,500\n喂，您好。\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n[倒鸭子]？\n",
        encoding="utf-8",
    )
    chunks = load_srt(srt)
    assert len(chunks) == 2
    assert chunks[0].start == pytest.approx(1.0)
    assert chunks[0].end == pytest.approx(2.5)
    assert chunks[1].fixed
    assert any(k.highlight for k in chunks[1].keys)


def test_json_loader_accepts_strings_and_objects(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(
        '{"chunks": ["第一句。", {"text": "第二句。", "start": 2, "end": 3}]}',
        encoding="utf-8",
    )
    chunks = load_json_script(path)
    assert len(chunks) == 2
    assert chunks[1].fixed and chunks[1].start == 2.0


def test_loaded_beats_get_sequential_indices(tmp_path):
    """Every loader must number its beats – the layout seeds per-beat styling from it."""
    srt = tmp_path / "a.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n一。\n\n2\n00:00:03,000 --> 00:00:04,000\n二。\n",
        encoding="utf-8",
    )
    data = tmp_path / "a.json"
    data.write_text('["一。", "二。", {"text": "三。"}]', encoding="utf-8")
    for loaded in (load_srt(srt), load_json_script(data)):
        assert [c.index for c in loaded] == list(range(len(loaded)))


def test_partially_timed_beats_are_interpolated(tmp_path, small_cfg):
    """A beat sheet may pin a few beats and let the rest flow."""
    path = tmp_path / "a.json"
    path.write_text(
        '["开头。", {"text": "锚点。", "start": 5, "end": 6}, "结尾。"]',
        encoding="utf-8",
    )
    chunks = load_json_script(path)
    total = assign_timeline(chunks, small_cfg)
    assert chunks[1].start == 5.0 and chunks[1].end == 6.0
    assert chunks[0].start < 5.0
    assert chunks[0].end <= 5.0 + 1e-9
    assert chunks[2].start >= 6.0 - 1e-9
    assert total > chunks[2].end
    assert chunks[0].start < chunks[0].end < chunks[1].start < chunks[1].end <= chunks[2].start


def test_key_weight_counts_cjk_as_one():
    assert Key("倒").weight() == pytest.approx(1.0)
    assert Key("abc").weight() > 0


def test_chunk_plain_and_duration():
    chunk = Chunk(keys=[Key("倒"), Key("了")], start=1.0, end=2.5)
    assert chunk.plain == "倒了"
    assert chunk.duration == pytest.approx(1.5)
