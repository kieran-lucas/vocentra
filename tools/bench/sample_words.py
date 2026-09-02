# /// script
# requires-python = ">=3.11"
# ///
"""Deterministic word sampling from the Oxford manifests for the TTS benchmark."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = [
    ROOT / "data" / "source" / "oxford_a1_pilot_manifest.jsonl",
    ROOT / "data" / "source" / "oxford_5000_manifest.jsonl",
]


def headwords() -> list[str]:
    seen: dict[str, None] = {}
    for manifest in MANIFESTS:
        if not manifest.exists():
            continue
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            word = json.loads(line)["word"].strip()
            if "," in word or " " in word or not word.isalpha():
                continue  # single orthographic headwords only
            seen.setdefault(word.lower(), None)
    return sorted(seen)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--exclude", default="")
    parser.add_argument("--min-len", type=int, default=1)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    excluded = set()
    for path in filter(None, args.exclude.split(",")):
        excluded |= {w.strip().lower() for w in Path(path).read_text(encoding="utf-8").split() if w.strip()}

    pool = [w for w in headwords() if w not in excluded and len(w) >= args.min_len]
    rng = random.Random(args.seed)
    picked = rng.sample(pool, args.count)
    text = "\n".join(picked)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(f"pool={len(pool)} seed={args.seed} count={args.count}", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
