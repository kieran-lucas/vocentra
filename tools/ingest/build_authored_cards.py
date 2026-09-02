# /// script
# requires-python = ">=3.11"
# dependencies = ["eng-to-ipa==0.0.2"]
# ///
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import eng_to_ipa

from tools.ingest.generator import write_normalized
from tools.ingest.source_manifest import read_manifest
from tools.ingest.validator import validate_batch

IPA_OVERRIDES = {
    "address": "/ˈædres/", "adult": "/əˈdʌlt/", "advice": "/ədˈvaɪs/", "aunt": "/ænt/",
    "April": "/ˈeɪprəl/", "August": "/ˈɔɡəst/", "CD": "/ˌsiː ˈdiː/", "cannot": "/ˈkænɑt/",
    "capital": "/ˈkæpɪtəl/", "center": "/ˈsentər/", "clothes": "/kloʊðz/", "could": "/kʊd/",
    "born": "/bɔrn/", "bye": "/baɪ/", "cafe": "/kæˈfeɪ/", "career": "/kəˈrɪr/",
    "color": "/ˈkʌlər/", "conversation": "/ˌkɑnvərˈseɪʃən/", "country": "/ˈkʌntri/",
    "and": "/ænd/", "any": "/ˈeni/", "anyone": "/ˈeniˌwʌn/", "anything": "/ˈeniˌθɪŋ/",
    "around": "/əˈraʊnd/", "arrive": "/əˈraɪv/", "as": "/æz/", "banana": "/bəˈnænə/",
    "baseball": "/ˈbeɪsˌbɔl/", "basketball": "/ˈbæskɪtˌbɔl/", "because": "/bɪˈkɔz/",
    "before": "/bɪˈfɔr/", "but": "/bʌt/", "can": "/kæn/", "chair": "/tʃer/",
    "chart": "/tʃɑrt/", "city": "/ˈsɪti/", "coffee": "/ˈkɔfi/", "common": "/ˈkɑmən/",
    "compare": "/kəmˈper/", "computer": "/kəmˈpjutər/", "concert": "/ˈkɑnsərt/",
    "correct": "/kəˈrekt/", "course": "/kɔrs/", "culture": "/ˈkʌltʃər/",
}


def display_word(source_word: str) -> str:
    return re.sub(r"\s+\([^)]*\)$", "", source_word)


def ipa_for(word: str) -> str:
    if word in IPA_OVERRIDES:
        return IPA_OVERRIDES[word]
    converted = eng_to_ipa.convert(word)
    if "*" in converted:
        raise ValueError(f"No IPA found for {word}: {converted}")
    converted = converted.split(",")[0].strip()
    return f"/{converted}/"


def main() -> None:
    manifest = read_manifest(ROOT / "data/source/oxford_a1_pilot_manifest.jsonl")
    golden = json.loads((ROOT / "tools/prompts/golden_cards.json").read_text(encoding="utf-8"))
    cards = {card["sourceIndex"]: card for card in golden}
    with (ROOT / "data/source/oxford_a1_card_content.tsv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            index = int(row["index"])
            if index in cards:
                continue
            source = manifest[index - 1]
            word = display_word(str(source["word"]))
            cards[index] = {
                "sourceKey": source["source_key"], "sourceIndex": index, "word": word,
                "ipa": ipa_for(word), "partOfSpeech": source["part_of_speech"], "cefr": "A1",
                "viMeaning": row["vi_meaning"], "enDefinition": row["en_definition"],
                "exampleMeaning": {"en": row["example_meaning_en"], "vi": row["example_meaning_vi"]},
                "exampleUsage": {"en": row["example_usage_en"], "vi": row["example_usage_vi"], "note": row["usage_note"]},
                "acceptedAnswers": [word], "extras": {},
            }
    ordered = [cards[index] for index in range(1, 181) if index in cards]
    missing = sorted(set(range(1, 181)) - set(cards))
    failures = validate_batch(ordered)
    if missing or failures:
        raise SystemExit(f"Missing={missing}; validation_failures={json.dumps(failures, ensure_ascii=False, indent=2)}")
    destination = ROOT / "tools/prompts/authored_cards.json"
    destination.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    write_normalized(ordered, ROOT / "data/generated/oxford_a1_pilot_cards.jsonl")
    print(f"Built {len(ordered)} authored cards at {destination}")


if __name__ == "__main__":
    main()
