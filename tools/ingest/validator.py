from __future__ import annotations

import re
import unicodedata

REQUIRED_PATHS = (
    "sourceKey", "sourceIndex", "word", "ipa", "partOfSpeech", "cefr", "viMeaning",
    "enDefinition", "exampleMeaning.en", "exampleMeaning.vi", "exampleUsage.en", "exampleUsage.vi",
)
PLACEHOLDERS = re.compile(r"\b(todo|tbd|placeholder|lorem ipsum|as an ai)\b", re.I)


def get_path(card: dict, path: str):
    value = card
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def validate_card(card: dict) -> list[str]:
    errors: list[str] = []
    for path in REQUIRED_PATHS:
        value = get_path(card, path)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"{path} is required")
    ipa = str(card.get("ipa", ""))
    if ipa and (not ipa.startswith("/") or not ipa.endswith("/") or len(ipa) < 3):
        errors.append("ipa must use /.../ notation")
    target_forms = [str(answer).casefold() for answer in card.get("acceptedAnswers", []) if isinstance(answer, str)]
    if not target_forms:
        target_forms = [str(card.get("word", "")).casefold()]
    examples = [get_path(card, "exampleMeaning.en"), get_path(card, "exampleUsage.en")]
    if all(isinstance(example, str) and not any(form in example.casefold() for form in target_forms) for example in examples):
        errors.append("target word is absent from both English examples")
    if examples[0] and examples[0] == examples[1]:
        errors.append("meaning and usage examples must differ")
    for english, vietnamese in ((get_path(card, "exampleMeaning.en"), get_path(card, "exampleMeaning.vi")), (get_path(card, "exampleUsage.en"), get_path(card, "exampleUsage.vi"))):
        if english and vietnamese and unicodedata.normalize("NFKC", english).casefold() == unicodedata.normalize("NFKC", vietnamese).casefold():
            errors.append("English example equals its Vietnamese translation")
    accepted = card.get("acceptedAnswers", [])
    if not isinstance(accepted, list) or not accepted or any(not isinstance(answer, str) or not answer.strip() for answer in accepted):
        errors.append("acceptedAnswers must be a nonempty string array")
    for path in REQUIRED_PATHS:
        value = get_path(card, path)
        if isinstance(value, str):
            if "```" in value or PLACEHOLDERS.search(value):
                errors.append(f"{path} contains commentary or placeholder text")
            if len(value) > (500 if "example" in path else 300):
                errors.append(f"{path} is excessively long")
    return sorted(set(errors))


def validate_batch(cards: list[dict]) -> dict[str, list[str]]:
    failures: dict[str, list[str]] = {}
    source_keys: set[str] = set()
    source_indices: set[int] = set()
    fingerprints: set[tuple[str, str]] = set()
    for card in cards:
        errors = validate_card(card)
        key = str(card.get("sourceKey", "<missing>"))
        index = card.get("sourceIndex")
        fingerprint = (str(card.get("word", "")).casefold(), str(card.get("partOfSpeech", "")).casefold())
        if key in source_keys:
            errors.append("duplicate sourceKey")
        if isinstance(index, int) and index in source_indices:
            errors.append("duplicate sourceIndex")
        if fingerprint in fingerprints:
            errors.append("duplicate word/POS card")
        source_keys.add(key)
        if isinstance(index, int):
            source_indices.add(index)
        fingerprints.add(fingerprint)
        if errors:
            failures[key] = sorted(set(errors))
    return failures
