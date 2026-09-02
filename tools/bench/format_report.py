# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Source-format integrity report: what Edge actually returns, and what survives
the production FFmpeg chain into Ogg Opus."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "data" / "audio-benchmark"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_metrics  # noqa: E402


def bandwidth(path: Path, sample_rate: int = 48000, floor_db: float = -60.0) -> float:
    """Highest frequency still carrying energy above floor_db relative to the peak bin."""
    x = audio_metrics.decode(path, sample_rate)
    n = 2048
    if len(x) < n:
        return 0.0
    frames = len(x) // n
    spectrum = np.abs(np.fft.rfft(x[: frames * n].reshape(frames, n) * np.hanning(n), axis=1))
    average = spectrum.mean(axis=0)
    average_db = 20 * np.log10(average / max(average.max(), 1e-12) + 1e-12)
    freqs = np.fft.rfftfreq(n, 1 / sample_rate)
    above = np.where(average_db > floor_db)[0]
    return float(freqs[above[-1]]) if above.size else 0.0


def spectral_distance(a: Path, b: Path, sample_rate: int = 24000) -> float:
    """Speech-gated log-spectral distance (dB), cross-correlation aligned.

    Alignment matters because Opus carries an encoder pre-skip, and gating
    matters because dB ratios in near-silence dominate an ungated average.
    """
    xa = audio_metrics.decode(a, sample_rate)
    xb = audio_metrics.decode(b, sample_rate)
    if xa.size == 0 or xb.size == 0:
        return float("nan")
    search = int(0.2 * sample_rate)
    head = min(len(xa), len(xb), int(0.5 * sample_rate))
    lags = range(-search, search + 1)
    best, shift = -2.0, 0
    for lag in lags:
        if lag >= 0:
            u, v = xa[lag : lag + head], xb[:head]
        else:
            u, v = xa[:head], xb[-lag : -lag + head]
        length = min(len(u), len(v))
        if length < head // 2:
            continue
        score = float(np.dot(u[:length], v[:length]) / (np.linalg.norm(u[:length]) * np.linalg.norm(v[:length]) + 1e-12))
        if score > best:
            best, shift = score, lag
    xa = xa[shift:] if shift >= 0 else xa
    xb = xb[-shift:] if shift < 0 else xb
    n = 1024
    length = min(len(xa), len(xb)) // n
    if length == 0:
        return float("nan")
    window = np.hanning(n)
    fa = np.abs(np.fft.rfft(xa[: length * n].reshape(length, n) * window, axis=1)) + 1e-9
    fb = np.abs(np.fft.rfft(xb[: length * n].reshape(length, n) * window, axis=1)) + 1e-9
    reference = 20 * np.log10(fb)
    gate = reference > (reference.max() - 40)
    if gate.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs(20 * np.log10(fa / fb))[gate]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--reference-format", default="audio-24khz-96kbitrate-mono-mp3")
    args = parser.parse_args()

    lines = (BENCH / args.name / "index.jsonl").read_text(encoding="utf-8").splitlines()
    jobs = [json.loads(line) for line in lines if line.strip()]
    jobs = [job for job in jobs if job.get("ok")]

    by_format: dict[str, list[dict]] = defaultdict(list)
    for job in jobs:
        by_format[job["format"]].append(job)

    reference = {job["word"]: job for job in by_format.get(args.reference_format, [])}

    header = (
        f"{'source format':<34}{'n':>3}{'codec':>10}{'sr':>7}{'ch':>3}{'kB':>7}"
        f"{'src_bw':>9}{'fin_bw':>9}{'LSD_src':>9}{'LSD_fin':>9}{'fin_kB':>8}"
    )
    print(header)
    print("-" * len(header))
    for output_format, items in sorted(by_format.items()):
        probes = [audio_metrics.probe(Path(job["master"])) for job in items]
        src_bw, fin_bw, lsd_src, lsd_fin, fin_size = [], [], [], [], []
        for job in items:
            master = Path(job["master"])
            final = Path(job["final"])
            src_bw.append(bandwidth(master))
            if final.exists():
                fin_bw.append(bandwidth(final))
                fin_size.append(final.stat().st_size / 1024)
            ref = reference.get(job["word"])
            if ref and output_format != args.reference_format:
                lsd_src.append(spectral_distance(master, Path(ref["master"])))
                if final.exists() and Path(ref["final"]).exists():
                    lsd_fin.append(spectral_distance(final, Path(ref["final"])))
        mean = lambda values: statistics.mean(values) if values else float("nan")  # noqa: E731
        print(
            f"{output_format:<34}{len(items):>3}{probes[0]['codec_name'] or '-':>10}"
            f"{str(probes[0]['sample_rate']):>7}{str(probes[0]['channels']):>3}"
            f"{mean([p['file_size'] for p in probes]) / 1024:>7.1f}"
            f"{mean(src_bw):>9.0f}{mean(fin_bw):>9.0f}"
            f"{mean(lsd_src):>9.2f}{mean(lsd_fin):>9.2f}{mean(fin_size):>8.1f}"
        )
    print("\nsrc_bw/fin_bw = highest frequency above -60 dB (Hz); LSD = mean log-spectral")
    print(f"distance in dB against {args.reference_format} (lower = closer to the reference).")


if __name__ == "__main__":
    main()
