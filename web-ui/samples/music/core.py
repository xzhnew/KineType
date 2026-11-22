"""Minimal KISS core: primitives used by the example tracks."""

from __future__ import annotations

import numpy as np

SR = 44100


def env(n: int, attack: float = 0.005, decay: float = 0.25, curve: float = 2.0) -> np.ndarray:
    """Simple attack/decay envelope of ``n`` samples."""
    t = np.arange(n) / SR
    a = np.clip(t / max(1e-4, attack), 0.0, 1.0)
    d = np.exp(-np.clip(t / max(1e-4, decay), 0.0, 40.0) * curve)
    return (a * d).astype(np.float32)


def note(midi: float, dur: float, kind: str = "saw", detune: float = 0.0) -> np.ndarray:
    freq = 440.0 * 2.0 ** ((midi - 69.0) / 12.0)
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    f = freq * (1.0 + detune)
    if kind == "sine":
        wave = np.sin(2 * np.pi * f * t)
    elif kind == "tri":
        wave = 2.0 * np.abs(2.0 * ((f * t) % 1.0) - 1.0) - 1.0
    elif kind == "square":
        wave = np.sign(np.sin(2 * np.pi * f * t))
    else:
        phase = (f * t) % 1.0
        wave = 2.0 * phase - 1.0
    return (wave * env(n, decay=dur * 0.55, curve=2.4)).astype(np.float32)


def kick(dur: float = 0.24, f0: float = 118.0, f1: float = 44.0) -> np.ndarray:
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.032)
    phase = np.cumsum(2 * np.pi * f / SR)
    body = np.sin(phase) * env(n, attack=0.001, decay=0.10, curve=2.0)
    return (body * 1.15).astype(np.float32)


def hat(dur: float = 0.055, tone: float = 0.0) -> np.ndarray:
    n = max(1, int(SR * dur))
    rng = np.random.default_rng(int(1000 + tone * 97))
    noise = rng.standard_normal(n).astype(np.float32)
    noise = np.diff(noise, prepend=noise[:1])  # high-pass-ish
    return (noise * env(n, attack=0.0005, decay=0.02, curve=3.0) * 0.42).astype(np.float32)


def snare(dur: float = 0.2) -> np.ndarray:
    n = max(1, int(SR * dur))
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n).astype(np.float32)
    body = np.sin(2 * np.pi * 186.0 * np.arange(n) / SR).astype(np.float32) * 0.35
    return ((noise * 0.7 + body) * env(n, attack=0.001, decay=0.075, curve=2.2)).astype(np.float32)


def place(track: np.ndarray, sample: np.ndarray, at: float, gain: float = 1.0) -> None:
    start = int(at * SR)
    if start >= track.size:
        return
    end = min(track.size, start + sample.size)
    track[start:end] += sample[: end - start] * gain


def pad_chord(midi_notes: list[float], dur: float, gain: float = 0.22) -> np.ndarray:
    n = max(1, int(SR * dur))
    out = np.zeros(n, dtype=np.float32)
    for i, midi in enumerate(midi_notes):
        voice = note(midi, dur, kind="saw", detune=0.0)
        voice2 = note(midi, dur, kind="saw", detune=0.004)
        out[: voice.size] += (voice + voice2) * 0.5
    fade = int(SR * min(0.6, dur * 0.3))
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        out[:fade] *= ramp
        out[-fade:] *= ramp[::-1]
    return (out * gain / max(1, len(midi_notes))).astype(np.float32)


def finish(track: np.ndarray, peak: float = 0.85, fade_out: float = 1.2) -> np.ndarray:
    n = int(SR * fade_out)
    if 0 < n < track.size:
        track[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
    high = float(np.max(np.abs(track))) or 1.0
    return (track / high * peak).astype(np.float32)


def write_wav(path, samples: np.ndarray, rate: int = SR) -> None:
    import wave

    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


#: minor pentatonic in semitones, useful for "talking" beeps
PENTA = [0, 3, 5, 7, 10, 12]


def beep(midi: float, dur: float = 0.19, gain: float = 0.5, kind: str = "tri") -> np.ndarray:
    return (note(midi, dur, kind=kind) * gain).astype(np.float32)
