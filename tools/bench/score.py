# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Aggregate benchmark metrics into per-configuration summary tables."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "data" / "audio-benchmark"

# Words ASR cannot disambiguate out of context; judged acoustically instead.
ASR_EXEMPT = {"a", "an", "i", "at", "be", "to", "an"}

def longest_nucleus(record: dict) -> float | None:
    durations = record.get("nucleus_durations") or []
    positions = record.get("nucleus_positions") or []
    if len(durations) != len(positions) or not durations:
        return None
    return positions[max(range(len(durations)), key=durations.__getitem__)]


def consensus_outliers(records: list[dict], tolerance: float = 0.25) -> dict[str, list[str]]:
    """Flag per-word prosodic outliers relative to the other configurations.

    Isolated-word TTS lengthens the final syllable regardless of lexical stress,
    so absolute nucleus position means little. Disagreement with the majority on
    the same word does mean something and is worth inspecting.
    """
    by_word: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_word[record["word"]].append(record)
    flags: dict[str, list[str]] = defaultdict(list)
    for word, items in by_word.items():
        values = {id(r): longest_nucleus(r) for r in items}
        present = [v for v in values.values() if v is not None]
        if len(present) < 3:
            continue
        median = statistics.median(present)
        counts = [len(r.get("nucleus_durations") or []) for r in items]
        modal = statistics.mode(counts)
        for record in items:
            key = f"{record['voice']} | {record['format']}"
            value = values[id(record)]
            if value is not None and abs(value - median) > tolerance:
                flags[key].append(f"{word}:pos{value:.2f}(median{median:.2f})")
            count = len(record.get("nucleus_durations") or [])
            if abs(count - modal) >= 2:
                flags[key].append(f"{word}:nuclei{count}(modal{modal})")
    return flags


def load(name: str) -> list[dict]:
    path = BENCH / name / "metrics.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def group_key(record: dict, by: str) -> str:
    if by == "voice":
        return record["voice"]
    if by == "format":
        return record["format"]
    return f"{record['voice']} | {record['format']}"


def summarise(records: list[dict], by: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[group_key(record, by)].append(record)
    outliers = consensus_outliers(records)
    combo_to_group = {f"{r['voice']} | {r['format']}": group_key(r, by) for r in records}
    grouped_flags: dict[str, list[str]] = defaultdict(list)
    for combo, values in outliers.items():
        grouped_flags[combo_to_group[combo]].extend(values)
    rows = []
    for key, items in groups.items():
        scored = [r for r in items if r["word"].lower() not in ASR_EXEMPT and "asr_match" in r]
        misses = [r for r in scored if not r["asr_match"]]
        stress_flags = sorted(grouped_flags.get(key, []))
        rate = [r["speech_duration"] / max(len(r["word"]), 1) for r in items if "speech_duration" in r]
        logprobs = [r["asr_logprob"] for r in scored if r.get("asr_logprob", -9.0) > -8.0]
        no_speech = [r for r in items if r.get("asr_text", "x") == ""]
        errors = [r for r in items if "error" in r]
        rows.append({
            "key": key,
            "n": len(items),
            "asr_n": len(scored),
            "asr_miss": len(misses),
            "asr_miss_words": sorted({f"{r['word']}->{r.get('asr_text','')}" for r in misses}),
            "logprob": statistics.mean(logprobs) if logprobs else 0.0,
            "logprob_min": min(logprobs, default=0.0),
            "no_speech": len(no_speech),
            "errors": len(errors),
            "stress_flags": stress_flags,
            "sec_per_char": statistics.mean(rate) if rate else 0.0,
            "rate_cv": (statistics.pstdev(rate) / statistics.mean(rate)) if len(rate) > 1 else 0.0,
            "onset_db": max((r["onset_rms_db"] for r in items if "onset_rms_db" in r), default=-99),
            "offset_db": max((r["offset_rms_db"] for r in items if "offset_rms_db" in r), default=-99),
            "lead_ms": statistics.mean(r["lead_silence"] for r in items if "lead_silence" in r) * 1000,
            "trail_ms": statistics.mean(r["trail_silence"] for r in items if "trail_silence" in r) * 1000,
            "hf_ratio": statistics.mean(r["hf_ratio"] for r in items if "hf_ratio" in r),
            "centroid": statistics.mean(r["spectral_centroid"] for r in items if "spectral_centroid" in r),
            "clip_frac": max((r["clip_fraction"] for r in items if "clip_fraction" in r), default=0.0),
            "dur": statistics.mean(r["duration"] for r in items if "duration" in r),
            "f0_range": statistics.mean(
                r["f0_range_semitones"] for r in items if r.get("f0_range_semitones", 0) > 0
            ) if any(r.get("f0_range_semitones", 0) > 0 for r in items) else 0.0,
            "quiet": sum(1 for r in items if r.get("peak_dbfs", 0) < -30),
        })
    rows.sort(key=lambda row: (row["errors"] + row["no_speech"], row["asr_miss"], len(row["stress_flags"]), -row["logprob"]))
    return rows


def repeatability(records: list[dict], by: str) -> dict[str, dict]:
    pairs: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        pairs[group_key(record, by)][record["word"]].append(record)
    out = {}
    for key, words in pairs.items():
        deltas, text_mismatch, flagged = [], 0, []
        for word, takes in words.items():
            if len(takes) < 2:
                continue
            durations = [t["speech_duration"] for t in takes]
            spread = (max(durations) - min(durations)) / max(statistics.mean(durations), 1e-6)
            deltas.append(spread)
            texts = {t.get("asr_text", "").strip().lower().rstrip(".") for t in takes}
            positions = [t.get("peak_position", 0.0) for t in takes]
            if len(texts) > 1:
                text_mismatch += 1
                flagged.append(f"{word}:text{sorted(texts)}")
            if max(positions) - min(positions) > 0.25:
                flagged.append(f"{word}:stress{[round(p,2) for p in positions]}")
            if spread > 0.10:
                flagged.append(f"{word}:dur{spread:.0%}")
        out[key] = {
            "mean_dur_spread": statistics.mean(deltas) if deltas else 0.0,
            "max_dur_spread": max(deltas) if deltas else 0.0,
            "text_mismatch": text_mismatch,
            "flags": flagged,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--by", default="voice", choices=["voice", "format", "combo"])
    parser.add_argument("--repeat", action="store_true")
    args = parser.parse_args()
    records = load(args.name)
    rows = summarise(records, args.by)
    header = (f"{'configuration':<46}{'n':>4}{'bad':>5}{'miss':>6}{'stress':>7}{'logP':>8}{'minP':>7}"
              f"{'s/char':>8}{'cv':>7}{'trail':>7}{'hf':>7}{'cent':>7}{'f0rng':>7}")
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['key']:<46}{row['n']:>4}{row['errors'] + row['no_speech'] + row['quiet']:>5}"
            f"{row['asr_miss']:>6}{len(row['stress_flags']):>7}"
            f"{row['logprob']:>8.3f}{row['logprob_min']:>7.2f}{row['sec_per_char']:>8.4f}"
            f"{row['rate_cv']:>7.3f}{row['trail_ms']:>7.0f}"
            f"{row['hf_ratio']:>7.4f}{row['centroid']:>7.0f}{row['f0_range']:>7.1f}"
        )
    print()
    for row in rows:
        if row["asr_miss_words"] or row["stress_flags"]:
            print(f"{row['key']}:")
            if row["asr_miss_words"]:
                print(f"    asr: {row['asr_miss_words']}")
            if row["stress_flags"]:
                print(f"    stress: {row['stress_flags']}")
    if args.repeat:
        print("\nrepeatability")
        for key, value in sorted(repeatability(records, args.by).items(), key=lambda kv: kv[1]["mean_dur_spread"]):
            print(f"{key:<46} mean_spread={value['mean_dur_spread']:.3f} max={value['max_dur_spread']:.3f} "
                  f"text_mismatch={value['text_mismatch']} flags={value['flags']}")


if __name__ == "__main__":
    main()
