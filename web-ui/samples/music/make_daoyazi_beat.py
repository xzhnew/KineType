"""Build a speak-along beat track for the 倒鸭子 demo.

    python examples/music/make_daoyazi_beat.py examples/music/daoyazi_beat.wav

The beeps are placed on the **real** beat times Kinetype computes for the demo
script, not on hand-copied timestamps – so the audio can never drift out of sync
with the typography when the cadence is retuned.  Everything here is synthesised,
so the demo carries no third-party audio.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from core import PENTA, SR, beep, finish, hat, kick, place, snare, write_wav  # noqa: E402

SCRIPT = HERE.parent / "daoyazi.zh.txt"


def beat_times() -> tuple[list[float], float]:
    """Ask Kinetype for the exact beat times of the demo script."""
    from kinetype.config import load_config
    from kinetype.script import assign_timeline, load_script

    cfg = load_config("meme-punch")
    chunks = load_script(str(SCRIPT), cfg)
    duration = assign_timeline(chunks, cfg)
    return [chunk.start for chunk in chunks], duration


def build(times: list[float], duration: float, bpm: float = 100.0) -> np.ndarray:
    track = np.zeros(int(SR * (duration + 1.5)), dtype=np.float32)
    step = 60.0 / bpm

    # drums on a steady grid
    t = 0.0
    index = 0
    while t < duration:
        place(track, kick(), t, 0.85 if index % 4 == 0 else 0.62)
        if index % 4 == 2:
            place(track, snare(), t, 0.45)
        place(track, hat(tone=index % 2), t + step * 0.5, 0.42)
        place(track, hat(tone=index % 3), t + step * 0.25, 0.22)
        t += step
        index += 1

    # a warm pad so the video is not just clicks
    bar = step * 4
    for i in range(int(duration / bar) + 1):
        root = 45 + (0 if i % 4 < 2 else -3)
        voice = beep(root, bar, gain=0.09, kind="saw")
        start = int(i * bar * SR)
        end = min(track.size, start + voice.size)
        track[start:end] += voice[: end - start]

    # one beep per typographic beat – this is what the onset detector locks onto
    for i, start in enumerate(times):
        midi = 62 + PENTA[i % len(PENTA)]
        place(track, beep(midi, 0.19, gain=0.34), start, 1.0)
        place(track, beep(midi, 0.14, gain=0.18, kind="sine"), start + 0.11, 1.0)

    return finish(track, peak=0.82, fade_out=1.4)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "daoyazi_beat.wav")
    if not SCRIPT.is_file():
        print(f"demo script missing: {SCRIPT}")
        return 1
    times, duration = beat_times()
    samples = build(times, duration)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_wav(out, samples)
    print(f"wrote {out}  {samples.size / SR:.2f}s  {len(times)} beats  (script is {duration:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
