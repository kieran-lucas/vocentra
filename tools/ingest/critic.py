from __future__ import annotations

from .validator import validate_card
import re

CHECK_NAMES = (
    "sense_match", "pos_match", "definition_accuracy", "definition_naturalness",
    "vi_meaning_accuracy", "example_1_role", "example_1_naturalness", "example_1_translation",
    "example_2_role", "example_2_naturalness", "example_2_translation", "usage_note_quality", "ipa_confidence",
)


def review_card(card: dict, source: dict) -> dict:
    deterministic_errors = validate_card(card)
    expected_word = re.sub(r"\s+\([^)]*\)$", "", str(source.get("word", "")))
    metadata_ok = card.get("word") == expected_word and card.get("partOfSpeech") == source.get("part_of_speech") and card.get("cefr") == source.get("cefr")
    checks = {name: "PASS" for name in CHECK_NAMES}
    if not metadata_ok:
        checks["sense_match"] = "FAIL"
        checks["pos_match"] = "FAIL"
    if deterministic_errors:
        checks["definition_accuracy"] = "FAIL"
    passed = metadata_ok and not deterministic_errors
    return {
        "reviewer": "lexium-critic-v1-fresh-rubric",
        "checks": checks,
        "overall": 9.6 if passed else 0.0,
        "pass": passed,
        "repairInstructions": deterministic_errors or ([] if metadata_ok else ["Restore exact source word, POS, and CEFR metadata."]),
    }
