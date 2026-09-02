# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=6,<7"]
# ///
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
BASE_PDF = ROOT / "data/source/American_Oxford_3000_by_CEFR_level.pdf"
EXTENSION_PDF = ROOT / "data/source/American_Oxford_5000_by_CEFR_level.pdf"
OUTPUT = ROOT / "data/source/oxford_5000_manifest.jsonl"
LEVELS = {"A1", "A2", "B1", "B2", "C1"}
POS_START = re.compile(
    r"\s(?=(?:indefinite article|adj\.|adv\.|conj\.|det\.|exclam\.|modal v\.|n\.|number|prep\.|pron\.|v\.|auxiliary v\.))"
)
TRAILING_LEVEL = re.compile(r"\s+(A1|A2|B1|B2|C1)$")


def normalize_headword(value: str) -> str:
    value = re.sub(r"(?<=[A-Za-z])\d+$", "", value.strip())
    return value.replace("\u2019", "'")


def parse_pdf(pdf_path: Path, source_name: str, allowed_levels: set[str]) -> list[dict]:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    current_level: str | None = None
    records: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().replace("\ufffd", "")
        if line in LEVELS:
            current_level = line
            continue
        if not line or current_level not in allowed_levels:
            continue
        if "Oxford University Press" in line or "The Oxford" in line or "American English" in line:
            continue
        line = TRAILING_LEVEL.sub("", line)
        match = POS_START.search(line)
        if not match:
            continue
        word = normalize_headword(line[: match.start()])
        part_of_speech = line[match.start() :].strip()
        if not word or not part_of_speech:
            continue
        records.append({
            "word": word,
            "part_of_speech": part_of_speech,
            "cefr": current_level,
            "source_name": source_name,
        })
    return records


def source_key(record: dict, source_index: int) -> str:
    prefix = "oxford3000" if record["source_name"] == "oxford3000" else "oxford5000"
    return f"{prefix}:{record['cefr'].lower()}:{source_index:06d}"


def main() -> None:
    base = parse_pdf(BASE_PDF, "oxford3000", {"A1", "A2", "B1", "B2"})
    extension = parse_pdf(EXTENSION_PDF, "oxford5000_extension", {"B2", "C1"})
    if len(base) != 3305 or len(extension) != 2012:
        raise SystemExit(f"Unexpected official counts: Oxford 3000={len(base)}, extension={len(extension)}")
    records = base + extension
    for source_index, record in enumerate(records, 1):
        record["source_index"] = source_index
        record["source_key"] = source_key(record, source_index)
        record["source_version"] = "american-cefr-2019-full-v1"
    existing = [json.loads(line) for line in (ROOT / "data/source/oxford_a1_pilot_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for previous, current in zip(existing, records):
        for field in ("source_key", "source_index", "word", "part_of_speech", "cefr"):
            if previous[field] != current[field]:
                raise SystemExit(f"Pilot identity changed at #{previous['source_index']} field {field}: {previous[field]!r} != {current[field]!r}")
    payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    OUTPUT.write_text(payload, encoding="utf-8")
    checksum = hashlib.sha256(payload.encode()).hexdigest()
    print(f"Wrote {len(records)} records to {OUTPUT}")
    print(f"Levels: {dict(sorted(Counter(record['cefr'] for record in records).items()))}")
    print(f"Sources: {dict(Counter(record['source_name'] for record in records))}")
    print(f"SHA-256: {checksum}")


if __name__ == "__main__":
    main()
