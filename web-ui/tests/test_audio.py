"""Audio helpers: wav decoding, duration, onset detection."""

from __future__ import annotations

import wave

import numpy as np
import pytest

from kinetype.audio import analyse, decode, envelope, resample, wav_duration


def _write_wav(path, samples: np.ndarray, rate: int = 16000) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def _click_track(rate: int = 16000, duration: float = 4.0, period: float = 0.5) -> np.ndarray:
    samples = np.zeros(int(rate * duration), dtype=np.float32)
    n = int(rate * 0.02)
    t = np.arange(n) / rate
    click = (np.sin(2 * np.pi * 900 * t) * np.exp(-t * 90)).astype(np.float32)
    for start in np.arange(0.2, duration - 0.1, period):
        i = int(start * rate)
        samples[i : i + n] += click
    return samples


def test_wav_duration(tmp_path):
    path = tmp_path / "a.wav"
    _write_wav(path, np.zeros(16000, dtype=np.float32))
    assert wav_duration(path) == pytest.approx(1.0, abs=0.01)


def test_wav_duration_returns_none_for_non_wav(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("not audio", encoding="utf-8")
    assert wav_duration(path) is None


def test_decode_stereo_is_downmixed(tmp_path):
    path = tmp_path / "s.wav"
    left = np.full(8000, 0.5, dtype=np.float32)
    right = np.full(8000, -0.5, dtype=np.float32)
    stereo = np.stack([left, right], axis=1).reshape(-1)
    pcm = (stereo * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(pcm.tobytes())
    decoded = decode(path, rate=8000)
    assert decoded is not None
    samples, rate = decoded
    assert rate == 8000
    assert abs(float(samples.mean())) < 0.02
    assert samples.size == 8000


def test_analyse_finds_the_clicks(tmp_path):
    path = tmp_path / "clicks.wav"
    _write_wav(path, _click_track())
    events = analyse(path, min_gap=0.2)
    assert len(events) >= 5
    # the first click sits at 0.2s
    assert any(abs(e - 0.2) < 0.08 for e in events)
    assert events == sorted(events)
    for a, b in zip(events, events[1:]):
        assert b - a >= 0.19


def test_analyse_ignores_tiny_files(tmp_path):
    path = tmp_path / "tiny.wav"
    _write_wav(path, np.zeros(100, dtype=np.float32))
    assert analyse(path) == []


def test_envelope_shape():
    samples = np.ones(16000, dtype=np.float32)
    rms, hop = envelope(samples, 16000, hop=0.01)
    assert rms.size == 100
    assert hop == pytest.approx(0.01)


def test_resample_changes_length_not_loudness():
    samples = np.sin(np.linspace(0, 40, 1000)).astype(np.float32)
    out = resample(samples, 1000, 2000)
    assert out.size == pytest.approx(2000, abs=2)
    assert np.abs(out).max() == pytest.approx(np.abs(samples).max(), rel=0.05)
