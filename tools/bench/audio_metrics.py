"""Objective clip measurements for the Edge TTS benchmark (numpy + ffmpeg only)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

FFMPEG = None
FFPROBE = None


def _binary(name: str) -> str:
    import shutil

    found = shutil.which(name)
    if found:
        return found
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    matches = list(winget.glob(f"Gyan.FFmpeg*/**/{name}.exe"))
    if matches:
        return str(matches[0])
    raise RuntimeError(f"{name} is not installed")


def ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        FFMPEG = _binary("ffmpeg")
    return FFMPEG


def ffprobe() -> str:
    global FFPROBE
    if FFPROBE is None:
        FFPROBE = _binary("ffprobe")
    return FFPROBE


def decode(path: Path, sample_rate: int = 24000) -> np.ndarray:
    raw = subprocess.run(
        [ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "-"],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            ffprobe(), "-v", "error",
            "-show_entries", "format=format_name,duration,size,bit_rate",
            "-show_entries", "stream=codec_name,channels,sample_rate,bits_per_raw_sample",
            "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format", {})
    return {
        "codec_name": stream.get("codec_name"),
        "channels": stream.get("channels"),
        "sample_rate": stream.get("sample_rate"),
        "container": fmt.get("format_name"),
        "bit_rate": fmt.get("bit_rate"),
        "duration": float(fmt.get("duration") or 0.0),
        "file_size": int(fmt.get("size") or 0),
    }


def _db(value: float) -> float:
    return float(20 * np.log10(max(value, 1e-12)))


def _frames(x: np.ndarray, sr: int, win: float = 0.025, hop: float = 0.005):
    n, h = int(win * sr), int(hop * sr)
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    count = 1 + (len(x) - n) // h
    idx = np.arange(n)[None, :] + h * np.arange(count)[:, None]
    return x[idx], h


def f0_track(frames: np.ndarray, sample_rate: int, low: float = 60.0, high: float = 400.0) -> np.ndarray:
    """Per-frame F0 by normalised autocorrelation; 0.0 marks an unvoiced frame."""
    lo, hi = int(sample_rate / high), int(sample_rate / low)
    centred = frames - frames.mean(axis=1, keepdims=True)
    size = 1 << (2 * frames.shape[1] - 1).bit_length()
    spectrum = np.fft.rfft(centred, size, axis=1)
    correlation = np.fft.irfft(spectrum * np.conj(spectrum), size, axis=1)[:, : hi + 1]
    energy = correlation[:, :1]
    normalised = correlation / np.where(energy > 1e-12, energy, 1e-12)
    window = normalised[:, lo : hi + 1]
    lag = np.argmax(window, axis=1) + lo
    strength = window.max(axis=1)
    return np.where(strength > 0.35, sample_rate / np.maximum(lag, 1), 0.0)


def nuclei(frames: np.ndarray, sample_rate: int, hop: int, start: int, end: int) -> dict:
    """Syllable-nucleus profile from the 100-1200 Hz envelope.

    Used only for cross-voice consensus comparison: neural TTS lengthens the
    final syllable of an isolated word regardless of lexical stress, so absolute
    nucleus position is not a stress verdict on its own.
    """
    window = np.hanning(frames.shape[1])
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1))
    freqs = np.fft.rfftfreq(frames.shape[1], 1 / sample_rate)
    envelope = spectrum[:, (freqs >= 100) & (freqs <= 1200)].sum(axis=1)
    smoother = np.hanning(9) / np.hanning(9).sum()
    envelope = np.convolve(envelope, smoother, mode="same")
    level = 20 * np.log10(envelope / max(envelope.max(), 1e-12) + 1e-12)
    active = np.where(level > -25)[0]
    if active.size == 0:
        return {"nucleus_positions": [], "nucleus_durations": []}
    runs, current = [], [int(active[0])]
    for index in active[1:]:
        if index - current[-1] <= 2:
            current.append(int(index))
        else:
            runs.append(current)
            current = [int(index)]
    runs.append(current)
    span = max(int(active[-1]) - int(active[0]), 1)
    seconds = hop / sample_rate
    return {
        "nucleus_positions": [round(((run[0] + run[-1]) / 2 - active[0]) / span, 3) for run in runs],
        "nucleus_durations": [round((run[-1] - run[0] + 1) * seconds, 3) for run in runs],
    }


def prominence(rms_db: np.ndarray, f0: np.ndarray, start: int, end: int) -> dict:
    """Locate the nuclear accent: the frame that maximises combined F0 and loudness."""
    region_db = rms_db[start : end + 1]
    region_f0 = f0[start : end + 1]
    voiced = region_f0 > 0
    if voiced.sum() < 3 or len(region_db) < 3:
        return {"f0_peak_position": float("nan"), "prominence_position": float("nan"),
                "f0_median": 0.0, "f0_range_semitones": 0.0, "voiced_fraction": float(voiced.mean() if len(voiced) else 0)}
    positions = np.linspace(0.0, 1.0, len(region_db))
    voiced_f0 = region_f0[voiced]
    f0_z = np.zeros_like(region_f0)
    f0_z[voiced] = (voiced_f0 - voiced_f0.mean()) / max(voiced_f0.std(), 1e-6)
    db_z = (region_db - region_db.mean()) / max(region_db.std(), 1e-6)
    combined = np.where(voiced, f0_z + db_z, -9.0)
    return {
        "f0_peak_position": float(positions[voiced][int(np.argmax(voiced_f0))]),
        "prominence_position": float(positions[int(np.argmax(combined))]),
        "f0_median": float(np.median(voiced_f0)),
        "f0_range_semitones": float(12 * np.log2(max(voiced_f0.max(), 1e-6) / max(voiced_f0.min(), 1e-6))),
        "voiced_fraction": float(voiced.mean()),
    }


def measure(path: Path, sample_rate: int = 24000) -> dict:
    x = decode(path, sample_rate)
    if x.size == 0:
        return {"error": "empty decode"}
    peak = float(np.max(np.abs(x)))
    frames, hop = _frames(x, sample_rate)
    window = np.hanning(frames.shape[1])
    rms = np.sqrt(np.mean((frames * window) ** 2, axis=1)) + 1e-12
    rms_db = 20 * np.log10(rms / max(peak, 1e-12))

    # Speech region: frames within 45 dB of the loudest frame.
    active = np.where(rms_db > -45)[0]
    if active.size == 0:
        return {"error": "silent clip"}
    start, end = int(active[0]), int(active[-1])
    lead = start * hop / sample_rate
    trail = (len(rms_db) - 1 - end) * hop / sample_rate

    # Stress / prosody proxy from the 100-1000 Hz (vowel) band envelope.
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1))
    freqs = np.fft.rfftfreq(frames.shape[1], 1 / sample_rate)
    vowel = spectrum[:, (freqs >= 100) & (freqs <= 1000)].sum(axis=1)
    region = vowel[start : end + 1]
    total = float(region.sum()) + 1e-12
    positions = np.linspace(0, 1, max(len(region), 2))[: len(region)]
    energy_centroid = float((region * positions).sum() / total)
    peak_position = float(positions[int(np.argmax(region))]) if len(region) > 1 else 0.0

    power = spectrum**2
    band_total = float(power.sum()) + 1e-12
    hf = float(power[:, freqs >= 4000].sum()) / band_total
    centroid = float((power * freqs[None, :]).sum() / band_total)

    onset_n = int(0.015 * sample_rate)
    accent = prominence(rms_db, f0_track(frames, sample_rate), start, end)
    return {
        **accent,
        **nuclei(frames, sample_rate, hop, start, end),
        "duration": len(x) / sample_rate,
        "speech_duration": (end - start) * hop / sample_rate,
        "lead_silence": lead,
        "trail_silence": trail,
        "onset_rms_db": _db(float(np.sqrt(np.mean(x[:onset_n] ** 2)))) - _db(peak),
        "offset_rms_db": _db(float(np.sqrt(np.mean(x[-onset_n:] ** 2)))) - _db(peak),
        "peak_dbfs": _db(peak),
        "rms_dbfs": _db(float(np.sqrt(np.mean(x**2)))),
        "clip_fraction": float(np.mean(np.abs(x) >= 0.999)),
        "energy_centroid": energy_centroid,
        "peak_position": peak_position,
        "hf_ratio": hf,
        "spectral_centroid": centroid,
    }
