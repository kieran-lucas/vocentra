from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SOURCE_NAME = "oxford3000"
SOURCE_LEVEL = "A1"
SOURCE_VERSION = "american-cefr-2019-pilot-v1"
SOURCE_URL = "https://www.oxfordlearnersdictionaries.com/external/pdf/wordlists/oxford-3000-5000/American_Oxford_3000_by_CEFR_level.pdf"
ENTRY_START = re.compile(
    r"\s(?=(?:indefinite article|adj\.|adv\.|conj\.|det\.|exclam\.|modal v\.|n\.|number|prep\.|pron\.|v\.|auxiliary v\.))"
)


def source_key(index: int) -> str:
    return f"{SOURCE_NAME}:{SOURCE_LEVEL.lower()}:{index:06d}"


def normalize_headword(value: str) -> str:
    value = re.sub(r"(?<=[A-Za-z])\d+$", "", value.strip())
    return value.replace("\u2019", "'")


def parse_a1_lines(text: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    in_a1 = False
    for raw_line in text.splitlines():
        line = raw_line.strip().replace("\ufffd", "")
        if line == "A1":
            in_a1 = True
            continue
        if in_a1 and line == "A2":
            break
        if not in_a1 or not line or line.startswith(("Oxford University Press", "The Oxford", "(American English)")):
            continue
        match = ENTRY_START.search(line)
        if not match:
            continue
        word = normalize_headword(line[: match.start()])
        part_of_speech = line[match.start() :].strip()
        if not word or not part_of_speech:
            continue
        index = len(items) + 1
        items.append(
            {
                "source_key": source_key(index),
                "source_index": index,
                "word": word,
                "part_of_speech": part_of_speech,
                "cefr": SOURCE_LEVEL,
                "source_name": SOURCE_NAME,
                "source_version": SOURCE_VERSION,
            }
        )
    return items


def extract_manifest(pdf_path: Path, limit: int = 180) -> list[dict[str, object]]:
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
    items = parse_a1_lines(text)
    if len(items) < limit:
        raise ValueError(f"Oxford source yielded only {len(items)} A1 entries")
    return items[:limit]


def write_manifest(items: list[dict[str, object]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in items)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def read_manifest(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    entries = extract_manifest(root / "data/source/American_Oxford_3000_by_CEFR_level.pdf")
    checksum = write_manifest(entries, root / "data/source/oxford_a1_pilot_manifest.jsonl")
    print(f"Wrote {len(entries)} entries; SHA-256 {checksum}")
