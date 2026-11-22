"""Audio helpers.

Two jobs only:

* ``wav_duration`` – so a voice-over can set the video length.
* ``analyse``      – find beat onsets, used for on-beat colour flashes, shake and
  keyword emphasis.

Deliberately dependency-light: WAV via the standard library, everything else left
to ffmpeg.  Onset detection is a plain energy-flux detector, which is plenty for
speech and for music with a clear kick.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

TARGET_RATE = 16000


def wav_duration(path: str | Path) -> float | None:
    """Length in seconds, or ``None`` when the file is not a readable PCM wav."""
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / float(handle.getframerate())
    except Exception:
        return None


def decode(path: str | Path, rate: int = TARGET_RATE) -> tuple[np.ndarray, int] | None:
    """Decode any audio file to mono float32.  Non-wav input goes through ffmpeg."""
    path = Path(path)
    if not path.is_file():
        return None
    data = _read_wav(path, rate)
    if data is None:
        data = _read_via_ffmpeg(path, rate)
    return data


def _read_wav(path: Path, rate: int) -> tuple[np.ndarray, int] | None:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            source_rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except Exception:
        return None
    if width not in (1, 2, 3, 4) or not frames:
        return None
    try:
        if width == 1:
            samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif width == 2:
            samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        elif width == 3:
            raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
            packed = (raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16))
            packed = np.where(packed >= 1 << 23, packed - (1 << 24), packed)
            samples = packed.astype(np.float32) / float(1 << 23)
        else:
            samples = np.frombuffer(frames, dtype="<i4").astype(np.float32) / float(1 << 31)
    except ValueError:
        return None
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if source_rate != rate:
        samples = resample(samples, source_rate, rate)
    return samples, rate


def _read_via_ffmpeg(path: Path, rate: int) -> tuple[np.ndarray, int] | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(rate), "pipe:1"]
    try:
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    except Exception:
        return None
    if not raw:
        return None
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0, rate


def resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or samples.size == 0:
        return samples
    duration = samples.size / float(source_rate)
    count = max(1, int(round(duration * target_rate)))
    try:
        return np.interp(
            np.linspace(0.0, duration, count, endpoint=False),
            np.linspace(0.0, duration, samples.size, endpoint=False),
            samples,
        ).astype(np.float32)
    except Exception:
        return samples


# --------------------------------------------------------------------------- #
# onset detection
# --------------------------------------------------------------------------- #


def envelope(samples: np.ndarray, rate: int, hop: float = 0.01) -> tuple[np.ndarray, float]:
    step = max(1, int(round(rate * hop)))
    usable = samples.size - (samples.size % step)
    if usable <= 0:
        return np.zeros(1, dtype=np.float32), hop
    frames = samples[:usable].reshape(-1, step)
    rms = np.sqrt(np.maximum(1e-12, (frames**2).mean(axis=1)))
    return rms.astype(np.float32), step / float(rate)


def analyse(
    path: str | Path,
    offset: float = 0.0,
    sensitivity: float = 1.35,
    min_gap: float = 0.22,
) -> list[float]:
    """Return onset times (seconds) – used for flashes, shake and emphasis."""
    decoded = decode(path)
    if decoded is None:
        return []
    samples, rate = decoded
    if samples.size < rate // 4:
        return []
    rms, hop = envelope(samples, rate)
    if rms.size < 8:
        return []
    # energy flux: positive change in loudness
    flux = np.diff(rms, prepend=rms[:1])
    flux = np.maximum(flux, 0.0)
    window = max(3, int(round(0.35 / hop)))
    kernel = np.ones(window, dtype=np.float32) / window
    local = np.convolve(flux, kernel, mode="same")
    threshold = local * sensitivity + 1e-4
    peaks: list[float] = []
    last = -1e9
    for i in range(1, flux.size - 1):
        if flux[i] < threshold[i]:
            continue
        if flux[i] < flux[i - 1] or flux[i] < flux[i + 1]:
            continue
        t = i * hop + offset
        if t - last < min_gap:
            continue
        peaks.append(round(float(t), 4))
        last = t
    return peaks


def describe(samples_path: str | Path) -> str:
    decoded = decode(samples_path)
    if decoded is None:
        return f"{samples_path}: could not decode"
    samples, rate = decoded
    rms, hop = envelope(samples, rate)
    events = analyse(samples_path)
    return (
        f"{Path(samples_path).name}: {samples.size / rate:.2f}s @ {rate}Hz, "
        f"peak {float(np.abs(samples).max()):.2f}, {len(events)} onsets"
    )


def _selftest() -> None:  # pragma: no cover - manual smoke test
    if len(sys.argv) < 2:
        print("usage: python -m kinetype.audio <file>")
        return
    print(describe(sys.argv[1]))


if __name__ == "__main__":  # pragma: no cover
    _selftest()
