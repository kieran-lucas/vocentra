"""Validation for the external vocabulary import contract.

tools/schemas/external_vocabulary_import.v2.schema.json is the published
contract. This module is the importer's gate: it repeats the structure with
precise, item-addressed messages, adds the checks JSON Schema cannot express
(identity, ownership, cross-references, subtype registries) and refuses any
attempt to steer the audio pipeline from the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sys

# PyInstaller unpacks bundled data under sys._MEIPASS; a checkout resolves from
# the repository root. Both must find the published contract.
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
SCHEMA_PATH = ROOT / "tools/schemas/external_vocabulary_import.v2.schema.json"
SCHEMA_VERSION = 2
ADDITIONAL_SCHEMA_VERSION = 1

# Infrastructure names the file may never carry, at any depth. The external file
# is semantic content; voice, codec and paths belong to tools/ingest/audio_profile.py.
HARD_FORBIDDEN = {
    "ttsvoice", "ttsprovider", "tts", "sourceformat", "audioformat", "audiocodec",
    "audiopath", "audiohash", "audiochecksum", "audiopipelineversion", "ffmpegargs",
    "masterpath", "appaudiopath", "audio", "audiovoice", "bitrate", "codec",
    "mastery", "masteryscore", "reviewhistory", "schedulerstate", "dbpath",
}
# Ambiguous outside infrastructure context: "voice" is also a grammatical term, so
# it is only forbidden as a key outside an Additional `attributes` object.
CONTEXT_FORBIDDEN = {"voice", "provider", "rate", "format"}
ROUTING_FORBIDDEN = {
    "batchid", "destination", "blockid", "blockpath", "createifmissing",
    "targetblockid", "targetblock", "deck", "folder",
}

KINDS = ("pattern", "collocation", "usage", "relation", "wordFormation", "expression")
POS_HINT = ("noun", "verb", "adjective", "adverb", "preposition", "conjunction",
            "pronoun", "determiner", "interjection", "phrase", "idiom")

# Known subtypes validate strongly; unknown but well-formed subtypes are kept and
# reported, because the taxonomy is meant to grow without a schema migration.
REGISTRIES: dict[str, dict[str, tuple[str, ...]]] = {
    "pattern": {"patternType": ("complementation", "valency", "preposition", "transitivity",
                                "reflexive", "reciprocal", "construction", "other")},
    "collocation": {"relation": ("verb+noun", "adjective+noun", "adverb+adjective", "noun+noun",
                                 "verb+adverb", "preposition+noun", "other")},
    "usage": {"usageType": ("countability", "transitivity", "register", "region", "dialect",
                            "style", "domain", "medium", "dated", "rare", "offensive",
                            "technical", "learnerError", "selectional", "pragmatics",
                            "politeness", "frequency", "other")},
    "relation": {"relationType": ("synonym", "near_synonym", "antonym", "contrast", "confusable",
                                  "false_friend", "broader", "narrower", "related", "other")},
    "wordFormation": {"relationType": ("derivation", "compounding", "conversion", "clipping",
                                       "blending", "other")},
    "expression": {"expressionType": ("phrasalVerb", "idiom", "collocationalPhrase",
                                      "fixedExpression", "other")},
}


class Report:
    """Batch-fatal problems, per-entry problems, and warnings.

    `errors` stops the whole file: a broken lexical envelope,
    an identity clash between entries, or any attempt to steer the audio
    pipeline. `entry_errors` stops only that entry, so one bad word does not
    cost the user the other forty-nine.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.entry_errors: dict[int, list[str]] = {}
        self.warnings: list[str] = []
        self._entry: int | None = None

    def error(self, where: str, message: str) -> None:
        line = f"{where}: {message}"
        if self._entry is None:
            self.errors.append(line)
        else:
            self.entry_errors.setdefault(self._entry, []).append(line)

    def all_errors(self) -> list[str]:
        return self.errors + [line for lines in self.entry_errors.values() for line in lines]

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")

    @property
    def ok(self) -> bool:
        """True when the file can be imported at all, bad entries aside."""
        return not self.errors


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def scan_forbidden(node: Any, where: str, report: Report, in_attributes: bool = False) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = key.lower()
            if lowered in ROUTING_FORBIDDEN:
                report.error(
                    f"{where}.{key}",
                    "forbidden routing field: a V2 file contains lexical content only; "
                    "the selected leaf block supplies the destination",
                )
            elif lowered in HARD_FORBIDDEN or (lowered in CONTEXT_FORBIDDEN and not in_attributes):
                report.error(
                    f"{where}.{key}",
                    "forbidden field: the import file may not set the TTS voice, source format, "
                    "codec, audio path or learner state; Lexium owns those",
                )
            scan_forbidden(value, f"{where}.{key}", report, in_attributes or key == "attributes")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            scan_forbidden(value, f"{where}[{index}]", report, in_attributes)


def _text(value: Any, where: str, field: str, report: Report, required: bool = True) -> None:
    """Enforce the null/empty policy: a present optional scalar is a value or null, never ''."""
    if value is None:
        if required:
            report.error(where, f"{field} is required")
        return
    if not isinstance(value, str):
        report.error(where, f"{field} must be a string")
    elif not value.strip():
        report.error(where, f"{field} must not be empty or blank; use null when there is no value")


def _id(value: Any, where: str, field: str, report: Report) -> str | None:
    if not isinstance(value, str) or not value.strip():
        report.error(where, f"{field} is required and must be a non-empty string")
        return None
    # Identifiers become file names and directory-free path segments, so the
    # character set is restricted here rather than sanitised later.
    if not all(character.isalnum() or character in "._:-" for character in value):
        report.error(where, f"{field} may only contain letters, digits and . _ : -")
        return None
    return value


def _locale(value: Any, where: str, report: Report) -> None:
    if not isinstance(value, str) or not value:
        report.error(where, "locale is required")
        return
    parts = value.split("-")
    if not (1 <= len(parts) <= 2 and parts[0].isalpha() and len(parts[0]) == 2):
        report.error(where, f"locale {value!r} is not a BCP-47 language or language-region tag")


def validate_additional(additional: Any, where: str, report: Report) -> list[dict]:
    if additional is None:
        return []
    if not isinstance(additional, dict):
        report.error(where, "additional must be an object")
        return []
    if additional.get("schemaVersion") != ADDITIONAL_SCHEMA_VERSION:
        report.error(where, f"additional.schemaVersion must be {ADDITIONAL_SCHEMA_VERSION}")
    items = additional.get("items")
    if not isinstance(items, list):
        report.error(where, "additional.items must be an array (use [] when there is nothing to add)")
        return []
    for index, item in enumerate(items):
        spot = f"{where}.items[{index}]"
        if not isinstance(item, dict):
            report.error(spot, "must be an object")
            continue
        missing = [field for field in ("id", "kind", "salience", "text", "note", "target", "attributes")
                   if field not in item]
        if missing:
            report.error(spot, f"missing required field(s): {', '.join(missing)}")
            continue
        _id(item["id"], spot, "id", report)
        kind = item["kind"]
        if kind not in KINDS:
            report.error(spot, f"kind {kind!r} is not one of {', '.join(KINDS)}")
        if item["salience"] not in (1, 2, 3):
            report.error(spot, "salience must be 1 (essential), 2 (useful) or 3 (optional)")
        _text(item["text"], spot, "text", report, required=False)
        _text(item["note"], spot, "note", report, required=False)
        target = item["target"]
        if item["text"] is None and item["note"] is None and target is None:
            # A wordFormation or relation item can carry its whole meaning in the
            # cross-reference, so a target counts as content.
            report.error(spot, "an item needs at least one of text, note or target")
        if target is not None:
            if not isinstance(target, dict) or set(target) - {"entryId", "senseId"}:
                report.error(spot, "target must be null or an object with entryId and senseId")
            else:
                for field in ("entryId", "senseId"):
                    value = target.get(field)
                    if value is not None and (not isinstance(value, str) or not value.strip()):
                        report.error(spot, f"target.{field} must be a non-empty string or null")
                if target.get("entryId") is None and target.get("senseId") is None:
                    report.error(spot, "target must be null rather than an object with only nulls")
        attributes = item["attributes"]
        if not isinstance(attributes, dict):
            report.error(spot, "attributes must be an object")
            continue
        for field, known in REGISTRIES.get(kind, {}).items():
            value = attributes.get(field)
            if value is None:
                report.warn(spot, f"{kind} item has no {field}; it will be stored without a subtype")
            elif value not in known:
                report.warn(spot, f"{field}={value!r} is not a known Additional v1 subtype; preserved as an additive value")
    return [item for item in items if isinstance(item, dict)]


def validate_entry(entry: Any, where: str, report: Report) -> dict:
    """Validate one entry and return the identifiers it declares."""
    declared: dict[str, list[str]] = {"forms": [], "pronunciations": [], "senses": [],
                                      "examples": [], "additional": []}
    if not isinstance(entry, dict):
        report.error(where, "entry must be an object")
        return declared
    entry_id = _id(entry.get("entryId"), where, "entryId", report)
    _text(entry.get("lemma"), where, "lemma", report)
    entry_type = entry.get("entryType")
    if entry_type is not None and entry_type not in ("word", "phrase", "idiom", "abbreviation"):
        report.error(where, f"entryType {entry_type!r} is not recognised")

    forms = entry.get("forms")
    if not isinstance(forms, list) or not forms:
        report.error(where, "forms must be a non-empty array")
        forms = []
    for index, form in enumerate(forms):
        spot = f"{where}.forms[{index}]"
        if not isinstance(form, dict):
            report.error(spot, "form must be an object")
            continue
        form_id = _id(form.get("formId"), spot, "formId", report)
        if form_id:
            declared["forms"].append(form_id)
        _text(form.get("written"), spot, "written", report)
        pronunciations = form.get("pronunciations")
        if not isinstance(pronunciations, list) or not pronunciations:
            report.error(spot, "pronunciations must be a non-empty array")
            continue
        seen_locales: dict[str, int] = {}
        for position, pronunciation in enumerate(pronunciations):
            place = f"{spot}.pronunciations[{position}]"
            if not isinstance(pronunciation, dict):
                report.error(place, "pronunciation must be an object")
                continue
            pronunciation_id = _id(pronunciation.get("pronunciationId"), place, "pronunciationId", report)
            if pronunciation_id:
                declared["pronunciations"].append(pronunciation_id)
            _locale(pronunciation.get("locale"), place, report)
            _text(pronunciation.get("ipa"), place, "ipa", report)
            locale = pronunciation.get("locale")
            if isinstance(locale, str):
                seen_locales[locale] = seen_locales.get(locale, 0) + 1
        for locale, count in seen_locales.items():
            if count > 1:
                report.warn(spot, f"{count} {locale} pronunciations on one form; senses must name the one they mean")

    senses = entry.get("senses")
    if not isinstance(senses, list) or not senses:
        report.error(where, "senses must be a non-empty array")
        senses = []
    for index, sense in enumerate(senses):
        spot = f"{where}.senses[{index}]"
        if not isinstance(sense, dict):
            report.error(spot, "sense must be an object")
            continue
        sense_id = _id(sense.get("senseId"), spot, "senseId", report)
        if sense_id:
            declared["senses"].append(sense_id)
        _text(sense.get("pos"), spot, "pos", report)
        pos = sense.get("pos")
        if isinstance(pos, str) and pos.strip() and pos.split()[0].lower() not in POS_HINT:
            report.warn(spot, f"pos {pos!r} is unusual; check it is a part of speech and not a sense label")
        _text(sense.get("definition"), spot, "definition", report)
        for field, pool in (("formId", set(declared["forms"])), ("pronunciationId", set(declared["pronunciations"]))):
            value = sense.get(field)
            if value is not None and value not in pool:
                report.error(spot, f"{field} {value!r} is not declared by this entry")

        glosses = sense.get("glosses")
        if not isinstance(glosses, list) or not glosses:
            report.error(spot, "glosses must be a non-empty array of {locale, text}")
        else:
            locales = []
            for position, gloss in enumerate(glosses):
                place = f"{spot}.glosses[{position}]"
                if not isinstance(gloss, dict):
                    report.error(place, "gloss must be an object")
                    continue
                _locale(gloss.get("locale"), place, report)
                _text(gloss.get("text"), place, "text", report)
                locales.append(gloss.get("locale"))
            if "vi" not in locales:
                report.warn(spot, "no Vietnamese gloss; the card back will show no Vietnamese meaning")

        examples = sense.get("examples")
        if not isinstance(examples, list) or len(examples) != 2:
            report.error(spot, "examples must contain exactly two entries: one 'meaning' and one 'usage'")
            examples = examples if isinstance(examples, list) else []
        types = []
        for position, example in enumerate(examples):
            place = f"{spot}.examples[{position}]"
            if not isinstance(example, dict):
                report.error(place, "example must be an object")
                continue
            example_id = _id(example.get("exampleId"), place, "exampleId", report)
            if example_id:
                declared["examples"].append(example_id)
            if example.get("type") not in ("meaning", "usage"):
                report.error(place, "type must be 'meaning' or 'usage'")
            types.append(example.get("type"))
            _text(example.get("en"), place, "en", report)
            _text(example.get("note"), place, "note", report, required=False)
            translations = example.get("translations")
            if not isinstance(translations, list) or not translations:
                report.error(place, "translations must be a non-empty array of {locale, text}")
                continue
            seen = set()
            for offset, translation in enumerate(translations):
                corner = f"{place}.translations[{offset}]"
                if not isinstance(translation, dict):
                    report.error(corner, "translation must be an object")
                    continue
                _locale(translation.get("locale"), corner, report)
                _text(translation.get("text"), corner, "text", report)
                locale = translation.get("locale")
                if locale in seen:
                    report.error(corner, f"duplicate translation locale {locale!r}")
                seen.add(locale)
        if len(examples) == 2 and sorted(filter(None, types)) != ["meaning", "usage"]:
            report.error(spot, "the two examples must be one 'meaning' and one 'usage'")

        for item in validate_additional(sense.get("additional"), f"{spot}.additional", report):
            if isinstance(item.get("id"), str):
                declared["additional"].append(item["id"])
    for bucket, values in declared.items():
        repeated = sorted({value for value in values if values.count(value) > 1})
        if repeated:
            report.error(where, f"duplicate {bucket} id(s) inside this entry: {', '.join(repeated)}")
    return declared


def validate_batch(payload: Any) -> Report:
    report = Report()
    if not isinstance(payload, dict):
        report.error("$", "the file must contain a JSON object")
        return report
    if payload.get("schemaVersion") == 1:
        report.error(
            "$.schemaVersion",
            "This vocabulary file uses import schema v1. Vocentra now uses schema v2, "
            "where the selected leaf block determines the destination. Generate a v2 "
            "vocabulary JSON file and try again.",
        )
        return report
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        report.error("$.schemaVersion", f"must be {SCHEMA_VERSION}")
    scan_forbidden(payload, "$", report)
    unknown = set(payload) - {"schemaVersion", "entries"}
    if unknown:
        report.error("$", f"unknown root field(s): {', '.join(sorted(unknown))}")

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        report.error("$.entries", "entries must be a non-empty array")
        return report

    seen: dict[str, set[str]] = {"entryId": set(), "forms": set(), "pronunciations": set(),
                                 "senses": set(), "examples": set(), "additional": set()}
    for index, entry in enumerate(entries):
        where = f"$.entries[{index}]"
        entry_id = entry.get("entryId") if isinstance(entry, dict) else None
        if isinstance(entry_id, str):
            if entry_id in seen["entryId"]:
                report.error(where, f"duplicate entryId {entry_id!r} in this batch")
            seen["entryId"].add(entry_id)
        report._entry = index
        declared = validate_entry(entry, where, report)
        report._entry = None
        for bucket in ("forms", "pronunciations", "senses", "examples", "additional"):
            clash = set(declared[bucket]) & seen[bucket]
            if clash:
                report.error(where, f"duplicate {bucket} id(s) in this batch: {', '.join(sorted(clash))}")
            seen[bucket] |= set(declared[bucket])

    # Cross-references resolve inside the batch when they can; anything else is
    # kept and reported so a later import can complete the link (see §27).
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        for sense_index, sense in enumerate(entry.get("senses") or []):
            if not isinstance(sense, dict):
                continue
            additional = sense.get("additional") or {}
            for item_index, item in enumerate(additional.get("items") or []):
                if not isinstance(item, dict) or not isinstance(item.get("target"), dict):
                    continue
                spot = f"$.entries[{index}].senses[{sense_index}].additional.items[{item_index}]"
                target = item["target"]
                if target.get("entryId") and target["entryId"] not in seen["entryId"]:
                    report.warn(spot, f"target entryId {target['entryId']!r} is not in this batch; "
                                      "the reference is kept and resolves when that entry is imported")
                if target.get("senseId") and target["senseId"] not in seen["senses"]:
                    report.warn(spot, f"target senseId {target['senseId']!r} is not in this batch; "
                                      "the reference is kept and resolves when that sense is imported")
    if report.ok:
        report.warnings.sort()
    return report


def validate_with_json_schema(payload: Any) -> list[str]:
    """Structural check against the published schema. Empty list when unavailable."""
    try:
        import jsonschema
    except ImportError:
        return []
    validator = jsonschema.Draft202012Validator(load_schema())
    return [f"{_pointer(error.absolute_path)}: {error.message}"
            for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))]


def _pointer(path) -> str:
    return "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in path)


def merge_json_schema(payload: Any, report: Report) -> None:
    """Fold published-schema failures into the report, keeping entry isolation.

    A structural failure inside one entry fails that entry; anything else fails
    the file.
    """
    # V1 gets one purpose-built migration message instead of a cascade of V2
    # additional-property/const errors that obscures the required user action.
    if isinstance(payload, dict) and payload.get("schemaVersion") == 1:
        return
    try:
        import jsonschema
    except ImportError:
        return
    validator = jsonschema.Draft202012Validator(load_schema())
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        path = list(error.absolute_path)
        line = f"{_pointer(path)}: {error.message}"
        if len(path) >= 2 and path[0] == "entries" and isinstance(path[1], int):
            report.entry_errors.setdefault(path[1], []).append(line)
        else:
            report.errors.append(line)
