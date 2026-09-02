# /// script
# requires-python = ">=3.11"
# dependencies = ["edge-tts==7.2.7", "jsonschema>=4,<5"]
# ///
"""Import one external vocabulary JSON file into Lexium.

    uv run tools/ingest/import_external_vocabulary.py <file.json> --target-block-id <ID>

The file carries semantic content only. The selected leaf block arrives as a
trusted command argument; everything about routing, audio and learner state is
owned by Vocentra. The app's Import vocabulary action runs this same module, so
there is one importer and one production audio path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ingest import audio_profile, audio_service, db, external_schema

MASTER_ROOT = ROOT / "data/audio-master/lex"
FINAL_ROOT = ROOT / "data/audio-final/lex"
APP_AUDIO_PREFIX = "audio/lex"


def configure_storage(app_data: Path) -> None:
    """Point the intermediate master and final stores at a writable location.

    A checkout keeps them in the repository beside the pilot masters. An
    installed app has no writable repository, so they live under app data.
    """
    global MASTER_ROOT, FINAL_ROOT
    if getattr(sys, "frozen", False):
        MASTER_ROOT = Path(app_data) / "audio-master/lex"
        FINAL_ROOT = Path(app_data) / "audio-final/lex"


class ImportError_(RuntimeError):
    """A failure that stops the whole batch before anything is written."""


class Emitter:
    """Progress as JSON lines for the app, or plain text for a terminal."""

    def __init__(self, as_json: bool) -> None:
        self.as_json = as_json

    def event(self, stage: str, **fields) -> None:
        if self.as_json:
            print(json.dumps({"stage": stage, **fields}, ensure_ascii=False), flush=True)
        elif stage not in ("progress", "summary"):  # main() prints a readable summary
            detail = " ".join(f"{key}={value}" for key, value in fields.items() if key != "total")
            print(f"[{stage}] {detail}", flush=True)


def safe_stem(identifier: str) -> str:
    """Path-safe file stem for an identifier that may contain ':' (illegal on Windows)."""
    if not all(character.isalnum() or character in "._:-" for character in identifier):
        raise ImportError_(f"Unsafe identifier for a file name: {identifier!r}")
    return identifier.replace(":", "_")


def recorded_path(path: Path) -> str:
    """Repo-relative when the file sits inside the checkout, absolute otherwise."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def source_key_for(sense_id: str) -> str:
    """Batch-independent identity for the projected card row.

    Deliberately not import-session- or block-scoped: the same stable sense ID
    always resolves to the same global card projection.
    """
    return f"lexical:{sense_id}"


# --------------------------------------------------------------------------- trusted target


def validate_target_leaf(connection: sqlite3.Connection, target_block_id: str) -> tuple[str, str]:
    """Return the trusted target and its display path without mutating anything."""
    if not isinstance(target_block_id, str) or not target_block_id.strip():
        raise ImportError_("--target-block-id is required for an actual import")
    row = connection.execute("SELECT id,parent_id,name FROM blocks WHERE id=?", (target_block_id,)).fetchone()
    if not row:
        raise ImportError_(f"target block {target_block_id!r} does not exist or is unavailable")
    if connection.execute("SELECT 1 FROM blocks WHERE parent_id=? LIMIT 1", (target_block_id,)).fetchone():
        raise ImportError_("Vocabulary can only be imported into a leaf block")

    names = [row["name"]]
    parent_id = row["parent_id"]
    seen = {row["id"]}
    while parent_id is not None:
        parent = connection.execute("SELECT id,parent_id,name FROM blocks WHERE id=?", (parent_id,)).fetchone()
        if not parent or parent["id"] in seen:
            raise ImportError_(f"target block {target_block_id!r} has an invalid parent hierarchy")
        seen.add(parent["id"])
        names.append(parent["name"])
        parent_id = parent["parent_id"]
    return row["id"], " / ".join(reversed(names))


# --------------------------------------------------------------------------- lexical shaping


def entry_index(entry: dict) -> dict:
    """Flatten one entry into the lookups the importer needs."""
    forms = {form["formId"]: form for form in entry["forms"]}
    pronunciations = {}
    owner = {}
    for form in entry["forms"]:
        for pronunciation in form["pronunciations"]:
            pronunciations[pronunciation["pronunciationId"]] = pronunciation
            owner[pronunciation["pronunciationId"]] = form
    return {"forms": forms, "pronunciations": pronunciations, "owner": owner}


def resolve_sense_audio(entry: dict, sense: dict, index: dict) -> tuple[dict, dict, bool]:
    """Pick (form, pronunciation, ambiguous) for a sense.

    Defaults to the entry's first form and its first en-US pronunciation, which
    is what the production voice speaks. Ambiguity is reported, never guessed
    away: two en-US pronunciations on one written form mean Edge cannot be told
    which reading to produce.
    """
    if sense.get("pronunciationId"):
        pronunciation = index["pronunciations"][sense["pronunciationId"]]
        form = index["owner"][sense["pronunciationId"]]
    else:
        form = index["forms"][sense["formId"]] if sense.get("formId") else entry["forms"][0]
        candidates = [p for p in form["pronunciations"] if p["locale"] == "en-US"] or form["pronunciations"]
        pronunciation = candidates[0]
    # Naming a pronunciationId fixes which IPA the card shows, but Edge is given
    # text, not phonemes: it cannot be told which reading of one spelling to
    # produce. So the flag depends on the form, not on the sense.
    same_locale = [p for p in form["pronunciations"] if p["locale"] == pronunciation["locale"]]
    return form, pronunciation, len(same_locale) > 1


def synthesis_text_for(form: dict) -> str:
    """Canonical spoken text, derived from lexical data and normalised as production does."""
    return form["written"].replace(",", ".").strip()


def gloss_for(sense: dict, locale: str = "vi") -> str:
    for gloss in sense["glosses"]:
        if gloss["locale"] == locale or gloss["locale"].startswith(locale + "-"):
            return gloss["text"]
    return sense["glosses"][0]["text"]


def example_of(sense: dict, kind: str) -> dict:
    return next(example for example in sense["examples"] if example["type"] == kind)


def translation_of(example: dict, locale: str = "vi") -> str:
    for translation in example["translations"]:
        if translation["locale"] == locale or translation["locale"].startswith(locale + "-"):
            return translation["text"]
    return example["translations"][0]["text"]


def additional_payload(sense: dict, unresolved: set[str]) -> str:
    additional = sense.get("additional") or {"schemaVersion": 1, "items": []}
    items = []
    for item in additional.get("items", []):
        copied = dict(item)
        copied["unresolved"] = item["id"] in unresolved
        items.append(copied)
    return json.dumps({"schemaVersion": additional.get("schemaVersion", 1), "items": items}, ensure_ascii=False)


# --------------------------------------------------------------------------- audio


def audio_is_current(connection: sqlite3.Connection, pronunciation_id: str, text: str) -> sqlite3.Row | None:
    row = connection.execute("SELECT * FROM lexical_audio_assets WHERE pronunciation_id=?", (pronunciation_id,)).fetchone()
    if not row or row["status"] not in ("current", "needs_review"):
        return None
    if row["fingerprint"] != audio_profile.FINGERPRINT or row["synthesis_text"] != text:
        return None
    if not row["app_path"] or not (db.default_app_data() / row["app_path"]).exists():
        return None
    return row


def ensure_audio(connection: sqlite3.Connection, entry: dict, form: dict, pronunciation: dict,
                 ambiguous: bool, emitter: Emitter) -> dict:
    """Prepare a current audio asset without opening or mutating a DB transaction."""
    pronunciation_id = pronunciation["pronunciationId"]
    text = synthesis_text_for(form)
    existing = audio_is_current(connection, pronunciation_id, text)
    status = "needs_review" if ambiguous else "current"
    if existing:
        return {
            "appPath": existing["app_path"], "sha256": existing["sha256"], "generated": False,
            "status": status, "synthesisText": text, "masterPath": existing["master_path"],
            "durationSeconds": existing["duration_seconds"], "needsPersist": existing["status"] != status,
        }

    stem = safe_stem(pronunciation_id)
    master = MASTER_ROOT / f"{stem}{audio_profile.MASTER_SUFFIX}"
    final = FINAL_ROOT / f"{stem}{audio_profile.FINAL_SUFFIX}"
    app_relative = f"{APP_AUDIO_PREFIX}/{stem}{audio_profile.FINAL_SUFFIX}"
    emitter.event("audio", entryId=entry["entryId"], pronunciationId=pronunciation_id, text=text)
    # Deliberately outside any write transaction: the network call must never
    # hold a SQLite writer open.
    master.unlink(missing_ok=True)
    metadata = audio_service.generate_production_audio(text, master, final)
    app_audio = db.default_app_data() / app_relative
    app_audio.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, app_audio)
    return {
        "appPath": app_relative, "sha256": metadata["sha256"], "generated": True,
        "status": status, "synthesisText": text, "masterPath": recorded_path(master),
        "durationSeconds": metadata["durationSeconds"], "needsPersist": True,
    }


# --------------------------------------------------------------------------- persistence


def identity_conflicts(connection: sqlite3.Connection, entry: dict) -> list[str]:
    """Refuse incompatible stable-ID ownership; semantic differences are preserved, not merged."""
    problems = []
    row = connection.execute("SELECT lemma FROM lexical_entries WHERE id=?", (entry["entryId"],)).fetchone()
    if row and row["lemma"].casefold() != entry["lemma"].casefold():
        problems.append(f"entryId {entry['entryId']!r} already exists with lemma {row['lemma']!r}, not {entry['lemma']!r}")
    for form in entry["forms"]:
        owner = connection.execute("SELECT entry_id,written FROM lexical_forms WHERE id=?", (form["formId"],)).fetchone()
        if owner and owner["entry_id"] != entry["entryId"]:
            problems.append(f"formId {form['formId']!r} already belongs to entry {owner['entry_id']!r}")
        elif owner and owner["written"].casefold() != form["written"].casefold():
            problems.append(f"formId {form['formId']!r} already identifies written form {owner['written']!r}, not {form['written']!r}")
        for pronunciation in form["pronunciations"]:
            held = connection.execute("SELECT form_id,locale,ipa FROM lexical_pronunciations WHERE id=?", (pronunciation["pronunciationId"],)).fetchone()
            if held and held["form_id"] != form["formId"]:
                problems.append(f"pronunciationId {pronunciation['pronunciationId']!r} already belongs to form {held['form_id']!r}")
            elif held and (held["locale"] != pronunciation["locale"] or held["ipa"] != pronunciation["ipa"]):
                problems.append(
                    f"pronunciationId {pronunciation['pronunciationId']!r} already identifies "
                    f"{held['locale']} {held['ipa']!r}, not {pronunciation['locale']} {pronunciation['ipa']!r}"
                )
    for sense in entry["senses"]:
        held = connection.execute("SELECT entry_id FROM lexical_senses WHERE id=?", (sense["senseId"],)).fetchone()
        if held and held["entry_id"] != entry["entryId"]:
            problems.append(f"senseId {sense['senseId']!r} already belongs to entry {held['entry_id']!r}")
        for example in sense["examples"]:
            owner = connection.execute("SELECT sense_id FROM lexical_examples WHERE id=?", (example["exampleId"],)).fetchone()
            if owner and owner["sense_id"] != sense["senseId"]:
                problems.append(f"exampleId {example['exampleId']!r} already belongs to sense {owner['sense_id']!r}")
        for item in (sense.get("additional") or {}).get("items", []):
            owner = connection.execute("SELECT sense_id FROM lexical_additional_items WHERE id=?", (item["id"],)).fetchone()
            if owner and owner["sense_id"] != sense["senseId"]:
                problems.append(f"Additional id {item['id']!r} already belongs to sense {owner['sense_id']!r}")
    return problems


def build_import_plan(connection: sqlite3.Connection, payload: dict, target_block_id: str) -> tuple[list[dict], list[str]]:
    """Classify every projected sense before audio or lexical writes."""
    plan: list[dict] = []
    warnings: list[str] = []
    for entry in payload["entries"]:
        duplicate = connection.execute(
            "SELECT id FROM lexical_entries WHERE lemma=? COLLATE NOCASE AND id<>? LIMIT 1",
            (entry["lemma"], entry["entryId"]),
        ).fetchone()
        if duplicate:
            warnings.append(
                f"{entry['entryId']}: possible duplicate spelling {entry['lemma']!r} is already stored as "
                f"{duplicate['id']!r}; stable IDs differ, so senses remain separate"
            )
        conflicts = identity_conflicts(connection, entry)
        index = entry_index(entry)
        for sense in entry["senses"]:
            form, pronunciation, ambiguous = resolve_sense_audio(entry, sense, index)
            item = {
                "entry": entry, "sense": sense, "form": form, "pronunciation": pronunciation,
                "ambiguous": ambiguous, "cardId": None, "kind": "NEW", "reason": None,
            }
            if conflicts:
                item["kind"] = "CONFLICT"
                item["reason"] = "; ".join(conflicts)
                plan.append(item)
                continue

            stored_sense = connection.execute(
                "SELECT entry_id,pos,definition FROM lexical_senses WHERE id=?", (sense["senseId"],)
            ).fetchone()
            if stored_sense:
                card = connection.execute(
                    "SELECT id FROM vocabulary_entries WHERE sense_id=? OR source_key=?",
                    (sense["senseId"], source_key_for(sense["senseId"])),
                ).fetchone()
                if not card:
                    item["kind"] = "CONFLICT"
                    item["reason"] = f"senseId {sense['senseId']!r} exists without its canonical study-card projection"
                else:
                    item["cardId"] = card["id"]
                    membership = connection.execute(
                        "SELECT 1 FROM block_entries WHERE block_id=? AND entry_id=?",
                        (target_block_id, card["id"]),
                    ).fetchone()
                    item["kind"] = "ALREADY_IN_TARGET" if membership else "REUSE_GLOBAL"
                    if stored_sense["pos"] != sense["pos"] or stored_sense["definition"] != sense["definition"]:
                        warnings.append(
                            f"{sense['senseId']}: incoming content differs from existing canonical data; "
                            "existing data is preserved"
                        )
            else:
                card_id = db.stable_id(f"lexsense:{sense['senseId']}")
                collision = connection.execute(
                    "SELECT id,sense_id FROM vocabulary_entries WHERE id=? OR source_key=?",
                    (card_id, source_key_for(sense["senseId"])),
                ).fetchone()
                if collision:
                    item["kind"] = "CONFLICT"
                    item["reason"] = (
                        f"senseId {sense['senseId']!r} collides with study card {collision['id']!r} "
                        f"owned by sense {collision['sense_id']!r}"
                    )
                else:
                    item["cardId"] = card_id
            plan.append(item)
    return plan, warnings


def persist_shell(connection: sqlite3.Connection, entry: dict) -> None:
    """Insert missing shell rows inside the caller's short write transaction."""
    timestamp = db.now()
    connection.execute(
        "INSERT INTO lexical_entries(id,lemma,entry_type,created_at,updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(id) DO NOTHING",
        (entry["entryId"], entry["lemma"], entry.get("entryType"), timestamp, timestamp),
    )
    for order, form in enumerate(entry["forms"]):
        connection.execute(
            "INSERT INTO lexical_forms(id,entry_id,written,morphology,sort_order) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO NOTHING",
            (form["formId"], entry["entryId"], form["written"],
             json.dumps(form.get("morphology") or {}, ensure_ascii=False), order),
        )
        for position, pronunciation in enumerate(form["pronunciations"]):
            connection.execute(
                "INSERT INTO lexical_pronunciations(id,form_id,locale,ipa,sort_order) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO NOTHING",
                (pronunciation["pronunciationId"], form["formId"], pronunciation["locale"], pronunciation["ipa"], position),
            )


def persist_audio_asset(connection: sqlite3.Connection, item: dict, audio: dict | None) -> None:
    if not audio or not audio["needsPersist"]:
        return
    entry, form, pronunciation = item["entry"], item["form"], item["pronunciation"]
    timestamp = db.now()
    connection.execute(
        "INSERT INTO lexical_audio_assets(pronunciation_id,entry_id,form_id,locale,synthesis_text,fingerprint,master_path,app_path,sha256,duration_seconds,status,last_error,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,?,?) ON CONFLICT(pronunciation_id) DO UPDATE SET "
        "synthesis_text=excluded.synthesis_text,fingerprint=excluded.fingerprint,master_path=excluded.master_path,"
        "app_path=excluded.app_path,sha256=excluded.sha256,duration_seconds=excluded.duration_seconds,"
        "status=excluded.status,last_error=NULL,updated_at=excluded.updated_at",
        (pronunciation["pronunciationId"], entry["entryId"], form["formId"], pronunciation["locale"],
         audio["synthesisText"], audio_profile.FINGERPRINT, audio["masterPath"], audio["appPath"],
         audio["sha256"], audio["durationSeconds"], audio["status"], timestamp, timestamp),
    )
    connection.execute(
        "UPDATE vocabulary_entries SET audio_path=?,audio_voice=?,audio_checksum=?,updated_at=? WHERE sense_id=?",
        (audio["appPath"], audio_profile.VOICE, audio["sha256"], timestamp, item["sense"]["senseId"]),
    )


def _assert_target_leaf_in_transaction(connection: sqlite3.Connection, block_id: str) -> None:
    """Race-safe target check. Caller has acquired SQLite's writer lock."""
    validate_target_leaf(connection, block_id)


def persist_new_sense(connection: sqlite3.Connection, item: dict, block_id: str,
                      audio: dict | None, unresolved: dict) -> None:
    """Insert one genuinely new canonical sense, projection and membership."""
    entry, sense = item["entry"], item["sense"]
    form, pronunciation = item["form"], item["pronunciation"]
    timestamp = db.now()
    connection.execute("BEGIN IMMEDIATE")
    try:
        _assert_target_leaf_in_transaction(connection, block_id)
        problems = identity_conflicts(connection, entry)
        if problems:
            raise ImportError_("; ".join(problems))
        if connection.execute("SELECT 1 FROM lexical_senses WHERE id=?", (sense["senseId"],)).fetchone():
            raise ImportError_(f"senseId {sense['senseId']!r} appeared while importing; retry to reuse it safely")
        persist_shell(connection, entry)
        persist_audio_asset(connection, item, audio)
        connection.execute(
            "INSERT INTO lexical_senses(id,entry_id,pronunciation_id,pos,definition,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (sense["senseId"], entry["entryId"], pronunciation["pronunciationId"], sense["pos"],
             sense["definition"], entry["senses"].index(sense), timestamp, timestamp),
        )
        for position, gloss in enumerate(sense["glosses"]):
            connection.execute(
                "INSERT INTO lexical_glosses(id,sense_id,locale,text,sort_order) VALUES(?,?,?,?,?)",
                (db.stable_id(f"gloss:{sense['senseId']}:{gloss['locale']}:{position}"),
                 sense["senseId"], gloss["locale"], gloss["text"], position),
            )
        for position, example in enumerate(sense["examples"]):
            connection.execute(
                "INSERT INTO lexical_examples(id,sense_id,example_type,en,note,sort_order) VALUES(?,?,?,?,?,?)",
                (example["exampleId"], sense["senseId"], example["type"], example["en"], example.get("note"), position),
            )
            for translation in example["translations"]:
                connection.execute(
                    "INSERT INTO lexical_example_translations(id,example_id,locale,text) VALUES(?,?,?,?)",
                    (db.stable_id(f"tr:{example['exampleId']}:{translation['locale']}"),
                     example["exampleId"], translation["locale"], translation["text"]),
                )
        for position, additional in enumerate((sense.get("additional") or {}).get("items", [])):
            target = additional.get("target") or {}
            connection.execute(
                "INSERT INTO lexical_additional_items(id,sense_id,kind,salience,text,note,target_entry_id,target_sense_id,attributes,unresolved,sort_order) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (additional["id"], sense["senseId"], additional["kind"], additional["salience"],
                 additional.get("text"), additional.get("note"), target.get("entryId"), target.get("senseId"),
                 json.dumps(additional.get("attributes") or {}, ensure_ascii=False),
                 1 if additional["id"] in unresolved else 0, position),
            )
        meaning, usage = example_of(sense, "meaning"), example_of(sense, "usage")
        accepted = [form["written"]] + ([entry["lemma"]] if entry["lemma"] != form["written"] else [])
        card_id = item["cardId"]
        connection.execute(
            """INSERT INTO vocabulary_entries(id,word,ipa,part_of_speech,vi_meaning,en_definition,example_meaning_en,example_meaning_vi,
               example_usage_en,example_usage_vi,collocations,usage_note,register,word_family,synonyms,antonyms,accepted_answers,extra_metadata,
               created_at,updated_at,source_key,source_name,audio_path,audio_voice,audio_checksum,sense_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,'[]',?,NULL,'[]','[]','[]',?,?,?,?,?,'external',?,?,?,?)""",
            (card_id, form["written"], pronunciation["ipa"], sense["pos"], gloss_for(sense), sense["definition"],
             meaning["en"], translation_of(meaning), usage["en"], translation_of(usage), usage.get("note"),
             json.dumps(accepted, ensure_ascii=False), additional_payload(sense, unresolved), timestamp, timestamp,
             source_key_for(sense["senseId"]), audio["appPath"] if audio else None,
             audio_profile.VOICE, audio["sha256"] if audio else None, sense["senseId"]),
        )
        connection.execute(
            "INSERT INTO block_entries(id,block_id,entry_id,created_at,updated_at) VALUES(?,?,?,?,?)",
            (db.stable_id(f"membership:{block_id}:{card_id}"), block_id, card_id, timestamp, timestamp),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def add_membership(connection: sqlite3.Connection, block_id: str, item: dict, audio: dict | None) -> None:
    """Add one membership without touching canonical semantics or prior memberships."""
    timestamp = db.now()
    connection.execute("BEGIN IMMEDIATE")
    try:
        _assert_target_leaf_in_transaction(connection, block_id)
        if not connection.execute("SELECT 1 FROM vocabulary_entries WHERE id=?", (item["cardId"],)).fetchone():
            raise ImportError_(f"canonical card for sense {item['sense']['senseId']!r} is unavailable")
        persist_audio_asset(connection, item, audio)
        connection.execute(
            "INSERT INTO block_entries(id,block_id,entry_id,created_at,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(block_id,entry_id) DO NOTHING",
            (db.stable_id(f"membership:{block_id}:{item['cardId']}"), block_id, item["cardId"], timestamp, timestamp),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


# --------------------------------------------------------------------------- driver


def unresolved_targets(connection: sqlite3.Connection, payload: dict) -> dict:
    """Additional item ids whose cross-reference target is not yet importable."""
    batch_entries = {entry["entryId"] for entry in payload["entries"]}
    batch_senses = {sense["senseId"] for entry in payload["entries"] for sense in entry["senses"]}
    unresolved = {}
    for entry in payload["entries"]:
        for sense in entry["senses"]:
            for item in (sense.get("additional") or {}).get("items", []):
                target = item.get("target") or {}
                missing = []
                if target.get("entryId") and target["entryId"] not in batch_entries:
                    if not connection.execute("SELECT 1 FROM lexical_entries WHERE id=?", (target["entryId"],)).fetchone():
                        missing.append(f"entryId {target['entryId']}")
                if target.get("senseId") and target["senseId"] not in batch_senses:
                    if not connection.execute("SELECT 1 FROM lexical_senses WHERE id=?", (target["senseId"],)).fetchone():
                        missing.append(f"senseId {target['senseId']}")
                if missing:
                    unresolved[item["id"]] = ", ".join(missing)
    return unresolved


def run_import(path: Path, target_block_id: str, connection: sqlite3.Connection,
               emitter: Emitter, skip_audio: bool = False) -> dict:
    raw = path.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImportError_(f"{path.name} is not valid UTF-8 JSON: {error}") from error

    report = external_schema.validate_batch(payload)
    external_schema.merge_json_schema(payload, report)
    if not report.ok:
        emitter.event("rejected", errors=report.errors[:50], errorCount=len(report.errors))
        raise ImportError_("the batch was rejected before any change was made:\n  - " + "\n  - ".join(report.errors[:50]))

    block_id, block_path = validate_target_leaf(connection, target_block_id)
    entries = payload["entries"]
    total = sum(len(entry.get("senses") or []) for entry in entries if isinstance(entry, dict))
    valid_entries = [entry for index, entry in enumerate(entries) if index not in report.entry_errors]
    plan, plan_warnings = build_import_plan(connection, {"entries": valid_entries}, block_id)
    report.warnings.extend(plan_warnings)
    emitter.event("validated", current=0, total=total,
                  destination=block_path, blockId=block_id, warnings=len(report.warnings))

    import_session_id = str(uuid.uuid4())
    timestamp = db.now()
    connection.execute(
        "INSERT INTO lexical_import_batches(batch_id,schema_version,source_sha256,destination_block_id,destination_path,entry_count,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,'RUNNING',?,?)",
        (import_session_id, payload["schemaVersion"], source_sha, block_id, block_path, len(entries), timestamp, timestamp),
    )
    connection.commit()

    unresolved = unresolved_targets(connection, {"entries": valid_entries})
    for item_id, missing in unresolved.items():
        report.warn(item_id, f"cross-reference is unresolved ({missing}); kept and resolvable on a later import")

    summary = {
        "importSessionId": import_session_id, "destination": block_path, "blockId": block_id,
        "requested": total, "validated": len(plan), "added": 0, "reused": 0,
        "alreadyInBlock": 0, "conflicts": 0,
        "audioGenerated": 0, "audioReused": 0, "needsPronunciationReview": [],
        "warnings": report.warnings, "conflictDetails": [], "failed": [],
    }

    for index, invalid in sorted(report.entry_errors.items()):
        entry = entries[index] if index < len(entries) and isinstance(entries[index], dict) else {}
        summary["failed"].append({"entryId": entry.get("entryId"), "lemma": entry.get("lemma"),
                                  "reason": "; ".join(invalid)})
        emitter.event("failed", entryId=entry.get("entryId"), current=index + 1,
                      total=total, reason=invalid[0])

    prepared_audio: dict[str, dict | None | Exception] = {}
    for item in plan:
        if item["kind"] not in ("NEW", "REUSE_GLOBAL"):
            continue
        pronunciation = item["pronunciation"]
        pronunciation_id = pronunciation["pronunciationId"]
        if pronunciation_id in prepared_audio:
            continue
        if item["ambiguous"]:
            summary["needsPronunciationReview"].append(
                f"{item['entry']['lemma']} / {item['sense']['senseId']}: the written form has several "
                f"{pronunciation['locale']} pronunciations; generated speech may use the other reading."
            )
        if skip_audio:
            prepared_audio[pronunciation_id] = None
            continue
        try:
            prepared = ensure_audio(
                connection, item["entry"], item["form"], pronunciation, item["ambiguous"], emitter
            )
            prepared_audio[pronunciation_id] = prepared
            summary["audioGenerated" if prepared["generated"] else "audioReused"] += 1
        except Exception as error:  # noqa: BLE001 - only dependent cards fail
            prepared_audio[pronunciation_id] = error

    entry_results: dict[str, list[str]] = {}
    for position, item in enumerate(plan, start=1):
        entry, sense, kind = item["entry"], item["sense"], item["kind"]
        entry_results.setdefault(entry["entryId"], []).append(kind)
        if kind == "CONFLICT":
            summary["conflicts"] += 1
            detail = {"entryId": entry["entryId"], "senseId": sense["senseId"], "reason": item["reason"]}
            summary["conflictDetails"].append(detail)
            emitter.event("conflict", current=position, total=len(plan), **detail)
            continue
        if kind == "ALREADY_IN_TARGET":
            summary["alreadyInBlock"] += 1
            emitter.event("already", entryId=entry["entryId"], senseId=sense["senseId"],
                          current=position, total=len(plan))
            continue

        audio = prepared_audio[item["pronunciation"]["pronunciationId"]]
        if isinstance(audio, Exception):
            message = f"{type(audio).__name__}: {audio}"
            summary["failed"].append({"entryId": entry["entryId"], "senseId": sense["senseId"],
                                      "lemma": entry.get("lemma"), "reason": message})
            emitter.event("failed", entryId=entry["entryId"], senseId=sense["senseId"],
                          current=position, total=len(plan), reason=message)
            entry_results[entry["entryId"]][-1] = "FAILED"
            continue
        try:
            if kind == "NEW":
                persist_new_sense(connection, item, block_id, audio, unresolved)
                summary["added"] += 1
                emitter.event("added", entryId=entry["entryId"], senseId=sense["senseId"],
                              current=position, total=len(plan))
            else:
                add_membership(connection, block_id, item, audio)
                summary["reused"] += 1
                emitter.event("reused", entryId=entry["entryId"], senseId=sense["senseId"],
                              current=position, total=len(plan))
        except Exception as error:  # noqa: BLE001 - preserve independent successful cards
            message = f"{type(error).__name__}: {error}"
            summary["failed"].append({"entryId": entry["entryId"], "senseId": sense["senseId"],
                                      "lemma": entry.get("lemma"), "reason": message})
            emitter.event("failed", entryId=entry["entryId"], senseId=sense["senseId"],
                          current=position, total=len(plan), reason=message)
            entry_results[entry["entryId"]][-1] = "FAILED"

    audit_available = bool(connection.execute(
        "SELECT 1 FROM lexical_import_batches WHERE batch_id=?", (import_session_id,)
    ).fetchone())
    for position, entry in enumerate(entries, start=1):
        if not audit_available:
            break
        if not isinstance(entry, dict) or not isinstance(entry.get("entryId"), str):
            continue
        results = entry_results.get(entry["entryId"], ["FAILED"])
        failed = all(result in ("CONFLICT", "FAILED") for result in results)
        message = next((detail["reason"] for detail in summary["conflictDetails"]
                        if detail["entryId"] == entry["entryId"]), None)
        source_key = f"external:{import_session_id}:{entry['entryId']}"
        payload_sha = hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        connection.execute(
            "INSERT INTO lexical_import_items(source_key,batch_id,entry_id,entry_index,status,stage,attempt_count,payload_sha256,last_error,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (source_key, import_session_id, entry["entryId"], position, "FAILED" if failed else "IMPORTED",
             "conflict" if failed else "import", 1 if failed else 0, payload_sha, message, db.now(), db.now()),
        )

    status = "PARTIAL" if summary["failed"] or summary["conflicts"] else "COMPLETED"
    if audit_available:
        connection.execute("UPDATE lexical_import_batches SET status=?,updated_at=? WHERE batch_id=?",
                           (status, db.now(), import_session_id))
    connection.commit()
    emitter.event("summary", **summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one external vocabulary JSON file")
    parser.add_argument("file", type=Path)
    parser.add_argument("--target-block-id", help="Existing leaf block selected by the app (required for import)")
    parser.add_argument("--db", type=Path, help="Target SQLite file (defaults to the app database)")
    parser.add_argument("--app-data", type=Path, help="App-data directory that owns audio/ (defaults to %APPDATA%/com.lexium.desktop)")
    parser.add_argument("--progress-json", action="store_true", help="Emit JSON-lines progress on stdout")
    parser.add_argument("--validate-only", action="store_true", help="Validate and report without writing or synthesising")
    parser.add_argument("--skip-audio", action="store_true", help="Import semantics without contacting the speech service")
    args = parser.parse_args()
    emitter = Emitter(args.progress_json)
    if args.app_data:
        db.set_app_data(args.app_data)
    configure_storage(args.app_data or db.default_app_data())

    if not args.file.exists():
        emitter.event("rejected", errors=[f"{args.file} does not exist"], errorCount=1)
        return 2
    if args.validate_only:
        try:
            payload = json.loads(args.file.read_bytes().decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            message = f"{args.file.name} is not valid UTF-8 JSON: {error}"
            emitter.event("rejected", errors=[message], errorCount=1)
            if not args.progress_json:
                print(f"  ERROR {message}")
            return 1
        report = external_schema.validate_batch(payload)
        external_schema.merge_json_schema(payload, report)
        problems = report.all_errors()
        emitter.event("validated" if not problems else "rejected", errors=problems, warnings=report.warnings,
                      errorCount=len(problems))
        if not args.progress_json:
            for line in problems:
                print(f"  ERROR {line}")
            for line in report.warnings:
                print(f"  warn  {line}")
            print("valid" if not problems else f"{len(problems)} error(s)")
        return 0 if not problems else 1

    if not args.target_block_id:
        message = "--target-block-id is required for an actual import"
        emitter.event("error", message=message)
        if not args.progress_json:
            print(f"IMPORT FAILED: {message}", file=sys.stderr)
        return 2
    connection = db.connect(args.db)
    try:
        db.require_ingestion_schema(connection)
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lexical_entries'").fetchone():
            raise ImportError_("The app database has not applied migration 0005. Launch the current Lexium build once, then retry.")
        summary = run_import(args.file, args.target_block_id, connection, emitter, skip_audio=args.skip_audio)
    except ImportError_ as error:
        emitter.event("error", message=str(error))
        if not args.progress_json:
            print(f"IMPORT FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()

    if not args.progress_json:
        print(f"\nImport {summary['importSessionId']} -> {summary['destination']}")
        for label in ("requested", "added", "reused", "alreadyInBlock", "conflicts", "audioGenerated", "audioReused"):
            print(f"  {label}: {summary[label]}")
        for warning in summary["warnings"]:
            print(f"  warn  {warning}")
        for note in summary["needsPronunciationReview"]:
            print(f"  REVIEW {note}")
        for failure in summary["failed"]:
            print(f"  FAILED {failure['entryId']}: {failure['reason']}")
    return 1 if summary["failed"] or summary["conflicts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
