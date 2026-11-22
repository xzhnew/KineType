"""Script parsing: plain text / SRT / JSON  ->  list[Chunk].

Three input levels exist on purpose:

* ``plain``  – a wall of text; Kinetype splits it into beats and guesses timing so
  you can drop a script in and export a video with no manual work at all.
* ``srt``    – real subtitle timings (e.g. exported from 剪映 / CapCut), so the
  flashing text stays glued to a voice-over.
* ``json``   – frame-accurate control over every beat and every word.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import RenderConfig
from .util import cjk_ratio, visual_width

# --------------------------------------------------------------------------- #
# data model
# --------------------------------------------------------------------------- #


@dataclass
class Key:
    """One glyph run – the smallest animated unit inside a beat."""

    text: str
    bold: bool = False
    highlight: bool = False
    color: str | None = None
    #: extra multiplier on the font size
    scale: float = 1.0
    #: true when this key came from an explicit ``\n`` / line break
    newline: bool = False
    #: true for sentence-final punctuation glued to the previous key
    tail_punct: bool = False

    def weight(self) -> float:
        return visual_width(self.text)


@dataclass
class Chunk:
    """A beat: one flash of text, possibly split over several visual lines."""

    keys: list[Key]
    start: float = 0.0
    end: float = 1.0
    #: set for SRT/JSON input where the timing is authoritative
    fixed: bool = False
    index: int = 0
    emphasis: bool = False
    #: filled in by the layout engine
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def plain(self) -> str:
        return "".join(k.text for k in self.keys)

    def letters(self) -> int:
        return sum(1 for ch in self.plain if not ch.isspace())


# --------------------------------------------------------------------------- #
# inline markup
# --------------------------------------------------------------------------- #

_MARKUP_RE = re.compile(
    r"""
    \|                                    # explicit line break
  | \\(?P<esc>[\\\[\]\*\{\}\|~])          # escaped literal
  | \[(?P<hi>[^\[\]]+)\]                  # [highlight]
  | \*\*(?P<bold2>[^*]+)\*\*              # **bold**
  | \*(?P<bold1>[^*]+)\*                  # *bold*
  | \{(?P<color>[\#A-Za-z0-9]+):(?P<ctext>[^{}]+)\}   # {#FF0000:text}
    """,
    re.VERBOSE,
)

#: sentence-final punctuation that gets glued onto the previous key
_TAIL_PUNCT = "。！？…～!?%》」』】)）"
#: CJK punctuation that always ends a segment/beat
_SEGMENT_BREAK = "，。！？；：、…—～"
#: default soft cap for one CJK key (glyphs) – overridden per chunk mode
_CJK_SEGMENT = 9


def parse_inline(text: str, segment: int = _CJK_SEGMENT) -> list[Key]:
    """Turn one raw line into styled :class:`Key` objects.

    ``segment`` caps how many CJK glyphs one key may hold; the chunker passes its own
    beat budget so a key can never outgrow a beat.
    """
    keys: list[Key] = []
    pos = 0
    pending: list[tuple[str, dict[str, Any]]] = []

    def push(raw: str, style: dict[str, Any] | None = None) -> None:
        if raw:
            pending.append((raw, style or {}))

    for match in _MARKUP_RE.finditer(text):
        push(text[pos : match.start()])
        pos = match.end()
        escaped = match.group("esc")
        if escaped is not None:
            push(escaped)
        elif match.group("hi") is not None:
            push(match.group("hi"), {"highlight": True})
        elif match.group("bold2") is not None:
            push(match.group("bold2"), {"bold": True})
        elif match.group("bold1") is not None:
            push(match.group("bold1"), {"bold": True})
        elif match.group("ctext") is not None:
            push(match.group("ctext"), {"color": match.group("color")})
        else:
            push("\n")
    push(text[pos:])

    # split styled runs into keys at CJK boundaries / latin word boundaries
    for raw, style in pending:
        for piece, is_break in _split_run(raw, segment):
            if is_break:
                keys.append(Key(text="", newline=True))
            else:
                keys.append(
                    Key(
                        text=piece,
                        bold=bool(style.get("bold", False)),
                        highlight=bool(style.get("highlight", False)),
                        color=style.get("color"),
                    )
                )
    return _glue_punctuation(keys)


def _split_run(raw: str, segment: int = _CJK_SEGMENT) -> Iterable[tuple[str, bool]]:
    """Split a styled run into keys.

    Latin: one key per word, trailing space kept so words never collapse into each
    other.  CJK: one key per *phrase*, found by greedily cutting at punctuation and
    never letting a key outgrow ``segment`` glyphs – a key that outgrows a beat would
    be chopped into single glyphs later, and single glyphs flash as gibberish.
    """
    if raw == "\n":
        yield "", True
        return
    if not raw:
        return

    buf: list[str] = []
    mode: str | None = None  # "cjk" | "latin"
    boundary = 0  # index in ``buf`` just after the last punctuation-ish char

    def flush() -> Iterable[tuple[str, bool]]:
        nonlocal buf, mode, boundary
        if buf:
            yield "".join(buf), False
        buf = []
        mode = None
        boundary = 0

    for ch in raw:
        if ch == "\n":
            yield from flush()
            yield "", True
            continue
        if cjk_ratio(ch) > 0.5:
            if mode == "latin":
                yield from flush()
            mode = "cjk"
            if ch.isspace():
                continue
            buf.append(ch)
            if ch in _SEGMENT_BREAK or ch in _TAIL_PUNCT:
                boundary = len(buf)
            if len(buf) >= segment:
                if boundary:
                    head = "".join(buf[:boundary])
                    yield head, False
                    buf = buf[boundary:]
                    boundary = 0
                else:
                    yield from flush()
        else:
            if mode == "cjk":
                yield from flush()
            mode = "latin"
            buf.append(ch)
            if ch.isspace():
                yield from flush()
    yield from flush()


def _glue_punctuation(keys: list[Key]) -> list[Key]:
    """Fold punctuation-only keys into the neighbouring key.

    Nothing looks worse in this format than a lone ``。`` flashing on its own beat,
    so punctuation is always welded onto the word it belongs to.
    """
    out: list[Key] = []
    for key in keys:
        if key.newline or not key.text:
            out.append(key)
            continue
        core = [ch for ch in key.text if not ch.isspace()]
        if core and all(ch in _TAIL_PUNCT for ch in core) and out and not out[-1].newline:
            previous = out[-1]
            joiner = "" if cjk_ratio(previous.text) > 0.4 else " "
            out[-1] = Key(
                text=previous.text + (joiner if not previous.text.endswith(" ") else "") + key.text.lstrip(),
                bold=previous.bold,
                highlight=previous.highlight,
                color=previous.color,
                scale=previous.scale,
                tail_punct=True,
            )
            continue
        out.append(key)
    return out


# --------------------------------------------------------------------------- #
# chunking (the "beat" rhythm)
# --------------------------------------------------------------------------- #

_STRONG = "。！？!?；;…"
_WEAK = "，,、：:—–~~"
#: chunk_mode -> (letters per CJK beat, words per latin beat)
#: The latin budget looks large but a Latin key is one *word*, so 6 words ≈ the
#: same screen mass as 8 CJK glyphs.  ``punch`` is the cadence of the classic
#: 倒鸭子 videos: three or four glyphs at a time, flashing roughly twice a second.
_MODE_BUDGET = {
    "punch": (4, 2.5),
    "tight": (6, 4.0),
    "balanced": (8, 5.5),
    "wide": (13, 9.0),
}
_MODE_MAX_KEYS = {"punch": 2, "tight": 4, "balanced": 5, "wide": 8}


class Chunker:
    """Turns prose into beats.

    The unit of measure is *reading weight*, not key count: a Chinese beat of five
    一-character words is four times as long on screen as a single ``喂``, so the
    budget is expressed in letters (CJK) or words (latin).
    """

    def __init__(self, cfg: RenderConfig) -> None:
        self.cfg = cfg
        self.budget = _MODE_BUDGET[cfg.text.chunk_mode]
        self.max_keys = max(1, min(cfg.text.max_keys, _MODE_MAX_KEYS[cfg.text.chunk_mode]))
        # A CJK key is a phrase.  Allow it a little more room than one beat so a
        # natural phrase boundary (a comma) is still reachable, but never so much
        # that the phrase has to be chopped into single glyphs to fit the budget.
        self.cjk_segment = max(2, int(round(self.budget[0] * 1.5)))

    # -- public ---------------------------------------------------------- #
    def split_sections(self, raw: str) -> list[list[str]]:
        """Blank lines become hard beat boundaries."""
        sections: list[list[str]] = []
        current: list[str] = []
        for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                if current:
                    sections.append(current)
                    current = []
                continue
            current.append(stripped)
        if current:
            sections.append(current)
        return sections

    def chunk_lines(self, lines: Sequence[str]) -> list[list[Key]]:
        """Group the keys of one section into beats.

        A beat closes on strong punctuation, on an explicit ``|`` break, or once it
        reaches the mode's reading budget – that is what creates the punchy,
        slightly irregular rhythm of the format.
        """
        groups: list[list[Key]] = []
        paragraph: list[Key] = []
        for line in lines:
            for key in parse_inline(line, self.cjk_segment):
                if key.newline:
                    self._flush(paragraph, groups)
                    paragraph = []
                    continue
                paragraph.append(key)
                if self._is_break(key, paragraph):
                    self._flush(paragraph, groups)
                    paragraph = []
        self._flush(paragraph, groups)
        return groups

    # -- internals -------------------------------------------------------- #
    def _limits(self, paragraph: Sequence[Key]) -> tuple[float, float]:
        """(budget in the paragraph's unit, hard ceiling)."""
        text = "".join(k.text for k in paragraph)
        ratio = cjk_ratio(text)
        if ratio >= 0.4:
            return float(self.budget[0]), float(self.budget[0]) * 1.75
        return float(self.budget[1]), float(self.budget[1]) * 1.8

    @staticmethod
    def _units(paragraph: Sequence[Key]) -> float:
        """Reading weight of the paragraph: glyphs for CJK, words for latin."""
        text = "".join(k.text for k in paragraph).strip()
        if not text:
            return 0.0
        if cjk_ratio(text) >= 0.4:
            return float(sum(1 for ch in text if not ch.isspace()))
        return float(max(1, len(text.split())))

    def _is_break(self, key: Key, paragraph: Sequence[Key]) -> bool:
        budget, ceiling = self._limits(paragraph)
        units = self._units(paragraph)
        tail = key.text.strip()
        if any(ch in _STRONG for ch in tail):
            return units >= max(1.0, budget * 0.4)
        if units >= ceiling:
            return True
        if units >= budget:
            # prefer closing on a natural word boundary instead of mid-word
            return _is_word_end(key) or len(paragraph) >= self.max_keys
        if units >= budget * 0.68 and _is_word_end(key) and _next_differs(paragraph):
            return True
        if tail and tail[-1] in _WEAK and units >= budget * 0.75:
            return True
        return False

    def _flush(self, paragraph: list[Key], groups: list[list[Key]]) -> None:
        if not paragraph:
            return
        for beat in self._split_oversized(paragraph):
            self._append(beat, groups)

    def _append(self, beat: list[Key], groups: list[list[Key]]) -> None:
        """Push a beat, merging it backwards when it is too small to read.

        Without this a stray strong-punctuation cut can leave a one-word beat
        (``the``) flashing alone, which reads as a glitch rather than a rhythm.
        """
        if groups:
            small = self._units(beat) < self._min_units(beat)
            fits = len(groups[-1]) + len(beat) <= self.max_keys
            if small and fits:
                groups[-1].extend(beat)
                return
        groups.append(beat)

    def _min_units(self, beat: Sequence[Key]) -> float:
        budget, _ = self._limits(beat)
        return max(1.0, budget * 0.42)

    def _split_oversized(self, keys: list[Key]) -> list[list[Key]]:
        """Hard ceiling: never let a single beat exceed ``max_keys`` keys."""
        beats: list[list[Key]] = []
        bucket: list[Key] = []
        for key in keys:
            bucket.append(key)
            if len(bucket) >= self.max_keys:
                beats.append(bucket)
                bucket = []
        if bucket:
            if beats and len(bucket) < max(1, self.cfg.text.min_keys) and len(beats[-1]) < self.max_keys + 1:
                beats[-1].extend(bucket)
            else:
                beats.append(bucket)
        return beats


def _is_word_end(key: Key) -> bool:
    """True when the beat may safely be cut *after* this key.

    Latin keys already end on a word boundary; CJK has no spaces, so a 2–3 glyph
    run is treated as a word (保险, 鸭子 …) and cut after it.  A lone 1-glyph key is
    usually just one syllable, so cutting there would split a real word in half.
    """
    stripped = key.text.strip()
    if not stripped:
        return False
    if cjk_ratio(stripped) < 0.4:
        return True
    return 1 < len(stripped) <= 3


def _next_differs(paragraph: Sequence[Key]) -> bool:
    """A styling change (e.g. a [highlight]) is always a good place to cut."""
    return bool(paragraph and paragraph[-1].highlight)


# --------------------------------------------------------------------------- #
# timing
# --------------------------------------------------------------------------- #


def estimate_durations(chunks: list[Chunk], cfg: RenderConfig) -> None:
    """Reading time per beat: glyphs/second for CJK, words/second for latin."""
    t_cfg = cfg.timing
    for chunk in chunks:
        ratio = cjk_ratio(chunk.plain)
        if ratio >= 0.4:
            units = float(sum(1 for ch in chunk.plain if not ch.isspace()))
            cps = t_cfg.cps_cjk
        else:
            units = float(max(1, len(chunk.plain.split())))
            cps = t_cfg.cps_latin
        duration = units / max(0.5, cps)
        duration = max(t_cfg.min_duration, min(t_cfg.max_duration, duration))
        chunk.extra["duration"] = duration


def _fill_gaps(chunks: list[Chunk], cfg: RenderConfig) -> float | None:
    """Resolve a beat sheet where only some beats carry explicit times.

    Explicit beats keep their times; the untimed ones are interpolated from the
    nearest anchors so you can pin a few key flashes and let the rest flow.
    Returns ``None`` when nothing is anchored at all.
    """
    estimate_durations(chunks, cfg)
    anchors = [i for i, c in enumerate(chunks) if c.fixed]
    if not anchors:
        return None

    # trailing untimed beats, spread after the last anchor
    cursor = chunks[anchors[-1]].end
    for chunk in chunks[anchors[-1] + 1 :]:
        chunk.start = cursor
        chunk.end = cursor + chunk.extra["duration"]
        cursor = chunk.end

    for left, right in zip(anchors, anchors[1:]):
        span = chunks[right].start - chunks[left].end
        between = list(range(left + 1, right))
        if not between or span <= 0:
            continue
        weights = [chunks[i].extra["duration"] for i in between]
        total_weight = sum(weights) or 1.0
        cursor = chunks[left].end
        for i, weight in zip(between, weights):
            share = span * (weight / total_weight)
            chunks[i].start = cursor
            chunks[i].end = cursor + share
            cursor += share
    return max(chunk.end for chunk in chunks) + cfg.timing.tail


def _finalize(chunks: list[Chunk]) -> list[Chunk]:
    """Assign the beat index every downstream stage keys its styling off."""
    for i, chunk in enumerate(chunks):
        chunk.index = i
        chunk.emphasis = any(k.highlight for k in chunk.keys)
    return chunks


def assign_timeline(chunks: list[Chunk], cfg: RenderConfig, target: float | None = None) -> float:
    """Fill in ``start``/``end`` for every chunk; returns the total duration.

    Explicit timings (SRT, or ``start``/``end`` in a JSON beat sheet) win.
    """
    if not chunks:
        return cfg.timing.tail
    t_cfg = cfg.timing

    if any(c.fixed for c in chunks):
        total = _fill_gaps(chunks, cfg)
        if total is not None:
            return total
    estimate_durations(chunks, cfg)
    # pause budget per chunk
    natural = 0.0
    for chunk in chunks:
        pause = 0.0
        tail_char = chunk.plain[-1:] if chunk.plain else ""
        if tail_char and tail_char in _STRONG:
            pause = t_cfg.pause_strong
        elif tail_char and tail_char in _WEAK:
            pause = t_cfg.pause
        chunk.extra["pause"] = pause
        natural += chunk.extra["duration"] + pause

    if target is not None:
        budget = max(0.05, target - t_cfg.lead_in - t_cfg.tail * 0.25)
        scale = budget / natural if natural > 0 else 1.0
    else:
        scale = 1.0

    cursor = t_cfg.lead_in
    for chunk in chunks:
        duration = chunk.extra["duration"] * scale
        duration = max(0.16, duration)
        chunk.start = cursor
        chunk.end = cursor + duration
        cursor += duration + chunk.extra.get("pause", 0.0) * scale

    total = cursor + t_cfg.tail
    if target is not None:
        stretch = target / total if total > 0 else 1.0
        if abs(stretch - 1.0) > 0.005:
            for chunk in chunks:
                chunk.start *= stretch
                chunk.end *= stretch
            total = target
    else:
        # leave a beat of silence worth of extra time when no target was given
        total = cursor + max(t_cfg.tail, 0.6)
    return total


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #

_SRT_TIME = re.compile(r"(\d{1,2}):(\d{1,2}):(\d{1,2})[,.](\d{1,3})")


def _parse_ts(value: str) -> float:
    m = _SRT_TIME.search(value)
    if not m:
        raise ValueError(f"bad timestamp {value!r}")
    h, mi, s, ms = (int(g) for g in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def load_srt(path: str | Path) -> list[Chunk]:
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    chunks: list[Chunk] = []
    for block in re.split(r"\n\s*\n", raw.replace("\r\n", "\n").replace("\r", "\n")):
        lines = [ln.strip("\ufeff").strip() for ln in block.strip().split("\n") if ln.strip()]
        if not lines:
            continue
        if lines[0].isdigit() and len(lines) > 1:
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        left, _, right = lines[0].partition("-->")
        start, end = _parse_ts(left), _parse_ts(right)
        text = "|".join(lines[1:])
        keys = [k for k in parse_inline(text) if k.text or k.newline]
        if not keys:
            continue
        chunks.append(Chunk(keys=keys, start=start, end=end, fixed=True))
    return _finalize(chunks)


def load_json_script(path: str | Path) -> list[Chunk]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("chunks") or data.get("beats") or data.get("script") or []
    chunks: list[Chunk] = []
    for item in data:
        if isinstance(item, str):
            keys = [k for k in parse_inline(item) if k.text or k.newline]
            chunks.append(Chunk(keys=keys))
            continue
        text = item.get("text") or item.get("line") or ""
        keys = [k for k in parse_inline(str(text)) if k.text or k.newline]
        chunk = Chunk(keys=keys)
        if "start" in item and "end" in item:
            chunk.start = float(item["start"])
            chunk.end = float(item["end"])
            chunk.fixed = True
        elif "duration" in item:
            chunk.extra["duration"] = float(item["duration"])
        chunk.emphasis = bool(item.get("emphasis", False)) or any(k.highlight for k in keys)
        chunks.append(chunk)
    return _finalize(chunks)


def load_script(
    source: str | None,
    cfg: RenderConfig,
    text: str | None = None,
) -> list[Chunk]:
    """Load beats from a file path, raw text, or an SRT/JSON document."""
    if text is None and source:
        candidate = Path(source)
        if candidate.exists():
            suffix = candidate.suffix.lower()
            if suffix == ".srt":
                return load_srt(candidate)
            if suffix == ".json":
                return load_json_script(candidate)
            text = candidate.read_text(encoding="utf-8-sig", errors="replace")
        else:
            text = source
    if text is None:
        raise ValueError("no script provided")
    return chunks_from_text(text, cfg)


def chunks_from_text(raw: str, cfg: RenderConfig) -> list[Chunk]:
    chunker = Chunker(cfg)
    chunks: list[Chunk] = []
    for section in chunker.split_sections(raw):
        for beat in chunker.chunk_lines(section):
            if any(k.text.strip() for k in beat):
                chunks.append(Chunk(keys=beat))
    return _finalize(chunks)


def describe(chunks: list[Chunk]) -> str:
    lines = []
    for chunk in chunks:
        lines.append(
            f"{chunk.index:>3}  {chunk.start:6.2f}->{chunk.end:6.2f} "
            f"({chunk.duration:4.2f}s)  {chunk.plain}"
        )
    return "\n".join(lines)
