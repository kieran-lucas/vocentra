# /// script
# requires-python = ">=3.11"
# dependencies = ["edge-tts==7.2.7", "jsonschema>=4,<5"]
# ///
"""Import one external vocabulary JSON file into Lexium.

    uv run tools/ingest/import_external_vocabulary.py <file.json>

The file carries semantic content and a destination; everything about how the
audio is made comes from tools/ingest/audio_profile.py. The app's Import
Vocabulary JSON action runs this same module, so there is one importer and one
production audio path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ingest import audio_encode, audio_profile, audio_service, db, external_schema

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

    Deliberately not batch-scoped: re-importing the same sense under a new
    batchId must update the same card rather than create a second one.
    """
    return f"lexical:{sense_id}"


# --------------------------------------------------------------------------- destination


def resolve_destination(connection: sqlite3.Connection, destination: dict) -> tuple[str, str]:
    """Return (block_id, human path). Creates missing levels only when asked to."""
    block_id = destination.get("blockId")
    if block_id:
        row = connection.execute("SELECT id,name FROM blocks WHERE id=?", (block_id,)).fetchone()
        if not row:
            raise ImportError_(f"destination.blockId {block_id!r} does not exist")
        if connection.execute("SELECT COUNT(*) FROM blocks WHERE parent_id=?", (block_id,)).fetchone()[0]:
            raise ImportError_(f"destination.blockId {block_id!r} has child blocks; vocabulary needs a leaf block")
        return block_id, row["name"]

    path = [name.strip() for name in destination["blockPath"]]
    create = destination["createIfMissing"]
    parent: str | None = None
    for depth, name in enumerate(path):
        rows = connection.execute(
            "SELECT id FROM blocks WHERE name=? COLLATE NOCASE AND ((? IS NULL AND parent_id IS NULL) OR parent_id=?)",
            (name, parent, parent),
        ).fetchall()
        if len(rows) > 1:
            raise ImportError_(f"destination.blockPath is ambiguous: {len(rows)} blocks named {name!r} at level {depth + 1}")
        if rows:
            parent = rows[0]["id"]
            continue
        if not create:
            raise ImportError_(f"destination.blockPath level {depth + 1} ({name!r}) does not exist and createIfMissing is false")
        if parent is not None and connection.execute("SELECT COUNT(*) FROM block_entries WHERE block_id=?", (parent,)).fetchone()[0]:
            raise ImportError_(f"cannot create {name!r} under a block that already holds vocabulary")
        new_id = db.stable_id("block:" + "/".join(path[: depth + 1]).lower())
        timestamp = db.now()
        connection.execute(
            "INSERT INTO blocks(id,parent_id,name,icon_key,sort_order,created_at,updated_at) "
            "VALUES(?,?,?,?,(SELECT COALESCE(MAX(sort_order),-1)+1 FROM blocks WHERE parent_id IS ?),?,?) "
            "ON CONFLICT(id) DO NOTHING",
            (new_id, parent, name, "book-open", parent, timestamp, timestamp),
        )
        parent = new_id
    assert parent is not None
    if connection.execute("SELECT COUNT(*) FROM blocks WHERE parent_id=?", (parent,)).fetchone()[0]:
        raise ImportError_(f"destination {'/'.join(path)} has child blocks; vocabulary needs a leaf block")
    connection.commit()
    return parent, "/".join(path)


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
                 ambiguous: bool, emitter: Emitter) -> tuple[str, str, bool]:
    """Return (app relative path, sha256, regenerated)."""
    pronunciation_id = pronunciation["pronunciationId"]
    text = synthesis_text_for(form)
    existing = audio_is_current(connection, pronunciation_id, text)
    status = "needs_review" if ambiguous else "current"
    if existing:
        if existing["status"] != status:
            connection.execute("UPDATE lexical_audio_assets SET status=?,updated_at=? WHERE pronunciation_id=?",
                               (status, db.now(), pronunciation_id))
            connection.commit()
        return existing["app_path"], existing["sha256"], False

    stem = safe_stem(pronunciation_id)
    master = MASTER_ROOT / f"{stem}{audio_profile.MASTER_SUFFIX}"
    final = FINAL_ROOT / f"{stem}{audio_profile.FINAL_SUFFIX}"
    app_relative = f"{APP_AUDIO_PREFIX}/{stem}{audio_profile.FINAL_SUFFIX}"
    timestamp = db.now()
    connection.execute(
        "INSERT INTO lexical_audio_assets(pronunciation_id,entry_id,form_id,locale,synthesis_text,fingerprint,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,'stale',?,?) ON CONFLICT(pronunciation_id) DO UPDATE SET "
        "synthesis_text=excluded.synthesis_text,fingerprint=excluded.fingerprint,status='stale',updated_at=excluded.updated_at",
        (pronunciation_id, entry["entryId"], form["formId"], pronunciation["locale"], text,
         audio_profile.FINGERPRINT, timestamp, timestamp),
    )
    connection.commit()
    emitter.event("audio", entryId=entry["entryId"], pronunciationId=pronunciation_id, text=text)
    # Deliberately outside any write transaction: the network call must never
    # hold a SQLite writer open.
    master.unlink(missing_ok=True)
    metadata = audio_service.generate_production_audio(text, master, final)
    app_audio = db.default_app_data() / app_relative
    app_audio.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, app_audio)
    connection.execute(
        "UPDATE lexical_audio_assets SET master_path=?,app_path=?,sha256=?,duration_seconds=?,status=?,last_error=NULL,updated_at=? WHERE pronunciation_id=?",
        (recorded_path(master), app_relative, metadata["sha256"], metadata["durationSeconds"],
         status, db.now(), pronunciation_id),
    )
    connection.commit()
    return app_relative, metadata["sha256"], True


# --------------------------------------------------------------------------- persistence


def conflict_check(connection: sqlite3.Connection, entry: dict) -> list[str]:
    """Refuse identity collisions rather than silently repairing them."""
    problems = []
    row = connection.execute("SELECT lemma FROM lexical_entries WHERE id=?", (entry["entryId"],)).fetchone()
    if row and row["lemma"].casefold() != entry["lemma"].casefold():
        problems.append(f"entryId {entry['entryId']!r} already exists with lemma {row['lemma']!r}, not {entry['lemma']!r}")
    for form in entry["forms"]:
        owner = connection.execute("SELECT entry_id FROM lexical_forms WHERE id=?", (form["formId"],)).fetchone()
        if owner and owner["entry_id"] != entry["entryId"]:
            problems.append(f"formId {form['formId']!r} already belongs to entry {owner['entry_id']!r}")
        for pronunciation in form["pronunciations"]:
            held = connection.execute("SELECT form_id FROM lexical_pronunciations WHERE id=?", (pronunciation["pronunciationId"],)).fetchone()
            if held and held["form_id"] != form["formId"]:
                problems.append(f"pronunciationId {pronunciation['pronunciationId']!r} already belongs to form {held['form_id']!r}")
    for sense in entry["senses"]:
        held = connection.execute("SELECT entry_id FROM lexical_senses WHERE id=?", (sense["senseId"],)).fetchone()
        if held and held["entry_id"] != entry["entryId"]:
            problems.append(f"senseId {sense['senseId']!r} already belongs to entry {held['entry_id']!r}")
    duplicate = connection.execute(
        "SELECT id FROM lexical_entries WHERE lemma=? COLLATE NOCASE AND id<>?", (entry["lemma"], entry["entryId"])
    ).fetchone()
    if duplicate:
        problems.append(f"lemma {entry['lemma']!r} is already stored under a different entryId ({duplicate['id']!r}); "
                        "merge them or reuse that entryId")
    return problems


def persist_shell(connection: sqlite3.Connection, entry: dict) -> None:
    """Write the entry, its forms and its pronunciations.

    Runs before synthesis so an audio asset always has a pronunciation row to
    point at. An entry that later fails leaves only this shell behind: no senses
    means no cards, so nothing incomplete reaches the study screen.
    """
    timestamp = db.now()
    with connection:
        connection.execute(
            "INSERT INTO lexical_entries(id,lemma,entry_type,created_at,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET lemma=excluded.lemma,entry_type=excluded.entry_type,updated_at=excluded.updated_at",
            (entry["entryId"], entry["lemma"], entry.get("entryType"), timestamp, timestamp),
        )
        for order, form in enumerate(entry["forms"]):
            connection.execute(
                "INSERT INTO lexical_forms(id,entry_id,written,morphology,sort_order) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET entry_id=excluded.entry_id,written=excluded.written,morphology=excluded.morphology,sort_order=excluded.sort_order",
                (form["formId"], entry["entryId"], form["written"],
                 json.dumps(form.get("morphology") or {}, ensure_ascii=False), order),
            )
            for position, pronunciation in enumerate(form["pronunciations"]):
                connection.execute(
                    "INSERT INTO lexical_pronunciations(id,form_id,locale,ipa,sort_order) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET form_id=excluded.form_id,locale=excluded.locale,ipa=excluded.ipa,sort_order=excluded.sort_order",
                    (pronunciation["pronunciationId"], form["formId"], pronunciation["locale"], pronunciation["ipa"], position),
                )


def persist_senses(connection: sqlite3.Connection, entry: dict, block_id: str, audio: dict, unresolved: dict) -> dict:
    """Write the senses and their projected cards in one short transaction."""
    timestamp = db.now()
    index = entry_index(entry)
    counts = {"senses": 0}
    with connection:
        for order, sense in enumerate(entry["senses"]):
            form, pronunciation, _ = resolve_sense_audio(entry, sense, index)
            connection.execute(
                "INSERT INTO lexical_senses(id,entry_id,pronunciation_id,pos,definition,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET entry_id=excluded.entry_id,pronunciation_id=excluded.pronunciation_id,pos=excluded.pos,"
                "definition=excluded.definition,sort_order=excluded.sort_order,updated_at=excluded.updated_at",
                (sense["senseId"], entry["entryId"], pronunciation["pronunciationId"], sense["pos"],
                 sense["definition"], order, timestamp, timestamp),
            )
            # Child rows carry no learner state, so replacing them is the simplest
            # deterministic merge. block_entries and mastery are never touched.
            connection.execute("DELETE FROM lexical_glosses WHERE sense_id=?", (sense["senseId"],))
            for position, gloss in enumerate(sense["glosses"]):
                connection.execute(
                    "INSERT INTO lexical_glosses(id,sense_id,locale,text,sort_order) VALUES(?,?,?,?,?)",
                    (db.stable_id(f"gloss:{sense['senseId']}:{gloss['locale']}:{position}"),
                     sense["senseId"], gloss["locale"], gloss["text"], position),
                )
            connection.execute("DELETE FROM lexical_examples WHERE sense_id=?", (sense["senseId"],))
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
            connection.execute("DELETE FROM lexical_additional_items WHERE sense_id=?", (sense["senseId"],))
            for position, item in enumerate((sense.get("additional") or {}).get("items", [])):
                target = item.get("target") or {}
                connection.execute(
                    "INSERT INTO lexical_additional_items(id,sense_id,kind,salience,text,note,target_entry_id,target_sense_id,attributes,unresolved,sort_order) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (item["id"], sense["senseId"], item["kind"], item["salience"], item.get("text"), item.get("note"),
                     target.get("entryId"), target.get("senseId"), json.dumps(item.get("attributes") or {}, ensure_ascii=False),
                     1 if item["id"] in unresolved else 0, position),
                )

            meaning, usage = example_of(sense, "meaning"), example_of(sense, "usage")
            app_path, checksum = audio[pronunciation["pronunciationId"]]
            accepted = [form["written"]] + ([entry["lemma"]] if entry["lemma"] != form["written"] else [])
            card_id = db.stable_id(f"lexsense:{sense['senseId']}")
            existing = connection.execute("SELECT id FROM vocabulary_entries WHERE sense_id=? OR source_key=?",
                                          (sense["senseId"], source_key_for(sense["senseId"]))).fetchone()
            card_id = existing["id"] if existing else card_id
            connection.execute(
                """INSERT INTO vocabulary_entries(id,word,ipa,part_of_speech,vi_meaning,en_definition,example_meaning_en,example_meaning_vi,
                   example_usage_en,example_usage_vi,collocations,usage_note,register,word_family,synonyms,antonyms,accepted_answers,extra_metadata,
                   created_at,updated_at,source_key,source_name,audio_path,audio_voice,audio_checksum,sense_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,'[]',?,NULL,'[]','[]','[]',?,?,?,?,?,'external',?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET word=excluded.word,ipa=excluded.ipa,part_of_speech=excluded.part_of_speech,
                   vi_meaning=excluded.vi_meaning,en_definition=excluded.en_definition,example_meaning_en=excluded.example_meaning_en,
                   example_meaning_vi=excluded.example_meaning_vi,example_usage_en=excluded.example_usage_en,
                   example_usage_vi=excluded.example_usage_vi,usage_note=excluded.usage_note,accepted_answers=excluded.accepted_answers,
                   extra_metadata=excluded.extra_metadata,audio_path=excluded.audio_path,audio_voice=excluded.audio_voice,
                   audio_checksum=excluded.audio_checksum,sense_id=excluded.sense_id,updated_at=excluded.updated_at""",
                (card_id, form["written"], pronunciation["ipa"], sense["pos"], gloss_for(sense), sense["definition"],
                 meaning["en"], translation_of(meaning), usage["en"], translation_of(usage),
                 usage.get("note"), json.dumps(accepted, ensure_ascii=False),
                 additional_payload(sense, unresolved), timestamp, timestamp, source_key_for(sense["senseId"]),
                 app_path, audio_profile.VOICE, checksum, sense["senseId"]),
            )
            connection.execute(
                "INSERT INTO block_entries(id,block_id,entry_id,created_at,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(block_id,entry_id) DO NOTHING",
                (db.stable_id(f"membership:{block_id}:{card_id}"), block_id, card_id, timestamp, timestamp),
            )
            counts["senses"] += 1
    return counts


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


def run_import(path: Path, connection: sqlite3.Connection, emitter: Emitter, skip_audio: bool = False) -> dict:
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

    block_id, block_path = resolve_destination(connection, payload["destination"])
    entries = payload["entries"]
    total = len(entries)
    emitter.event("validated", current=0, total=total, batchId=payload["batchId"],
                  destination=block_path, blockId=block_id, warnings=len(report.warnings))

    timestamp = db.now()
    connection.execute(
        "INSERT INTO lexical_import_batches(batch_id,schema_version,source_sha256,destination_block_id,destination_path,entry_count,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,'RUNNING',?,?) ON CONFLICT(batch_id) DO UPDATE SET source_sha256=excluded.source_sha256,"
        "destination_block_id=excluded.destination_block_id,destination_path=excluded.destination_path,"
        "entry_count=excluded.entry_count,status='RUNNING',updated_at=excluded.updated_at",
        (payload["batchId"], payload["schemaVersion"], source_sha, block_id, block_path, total, timestamp, timestamp),
    )
    connection.commit()

    unresolved = unresolved_targets(connection, payload)
    for item_id, missing in unresolved.items():
        report.warn(item_id, f"cross-reference is unresolved ({missing}); kept and resolvable on a later import")

    summary = {
        "batchId": payload["batchId"], "destination": block_path, "blockId": block_id,
        "requested": total, "validated": total, "imported": 0, "updated": 0, "alreadyCurrent": 0,
        "audioGenerated": 0, "audioReused": 0, "needsPronunciationReview": [],
        "warnings": report.warnings, "failed": [],
    }

    for position, entry in enumerate(entries, start=1):
        invalid = report.entry_errors.get(position - 1)
        if invalid:
            # One unusable entry costs only itself; §46.
            summary["validated"] -= 1
            summary["failed"].append({"entryId": entry.get("entryId"), "lemma": entry.get("lemma"),
                                      "reason": "; ".join(invalid)})
            emitter.event("failed", entryId=entry.get("entryId"), current=position, total=total, reason=invalid[0])
            continue
        source_key = f"external:{payload['batchId']}:{entry['entryId']}"
        payload_sha = hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        previous = connection.execute("SELECT * FROM lexical_import_items WHERE source_key=?", (source_key,)).fetchone()
        stored = connection.execute("SELECT id FROM lexical_entries WHERE id=?", (entry["entryId"],)).fetchone()
        connection.execute(
            "INSERT INTO lexical_import_items(source_key,batch_id,entry_id,entry_index,status,stage,attempt_count,payload_sha256,created_at,updated_at) "
            "VALUES(?,?,?,?,'DISCOVERED','discovery',0,?,?,?) ON CONFLICT(source_key) DO UPDATE SET "
            "batch_id=excluded.batch_id,entry_index=excluded.entry_index,payload_sha256=excluded.payload_sha256,updated_at=excluded.updated_at",
            (source_key, payload["batchId"], entry["entryId"], position, payload_sha, db.now(), db.now()),
        )
        connection.commit()
        try:
            problems = conflict_check(connection, entry)
            if problems:
                raise ImportError_("; ".join(problems))
            connection.execute("UPDATE lexical_import_items SET status='VALIDATED',stage='validation',updated_at=? WHERE source_key=?",
                               (db.now(), source_key))
            connection.commit()

            persist_shell(connection, entry)
            index = entry_index(entry)
            audio: dict[str, tuple[str, str]] = {}
            for sense in entry["senses"]:
                form, pronunciation, ambiguous = resolve_sense_audio(entry, sense, index)
                if ambiguous:
                    summary["needsPronunciationReview"].append(
                        f"{entry['lemma']} / {sense['senseId']}: the written form has several {pronunciation['locale']} "
                        "pronunciations, and the speech service is given text rather than phonemes, so the generated "
                        "clip may read the other sense. Audio is stored as needs_review."
                    )
                if pronunciation["pronunciationId"] in audio:
                    continue
                if skip_audio:
                    audio[pronunciation["pronunciationId"]] = (None, None)
                    continue
                app_path, checksum, generated = ensure_audio(connection, entry, form, pronunciation, ambiguous, emitter)
                audio[pronunciation["pronunciationId"]] = (app_path, checksum)
                summary["audioGenerated" if generated else "audioReused"] += 1
            connection.execute("UPDATE lexical_import_items SET status='ENCODED',stage='encode',updated_at=? WHERE source_key=?",
                               (db.now(), source_key))
            connection.commit()

            counts = persist_senses(connection, entry, block_id, audio, unresolved)
            connection.execute("UPDATE lexical_import_items SET status='IMPORTED',stage='import',last_error=NULL,updated_at=? WHERE source_key=?",
                               (db.now(), source_key))
            connection.commit()
            if previous is not None and previous["status"] == "IMPORTED" and previous["payload_sha256"] == payload_sha:
                summary["alreadyCurrent"] += 1
            elif stored:
                summary["updated"] += 1
            else:
                summary["imported"] += 1
            emitter.event("imported", entryId=entry["entryId"], current=position, total=total, senses=counts["senses"])
        except Exception as error:  # noqa: BLE001 - one bad entry must not lose the rest
            message = f"{type(error).__name__}: {error}"
            connection.execute(
                "UPDATE lexical_import_items SET status='FAILED',last_error=?,attempt_count=attempt_count+1,updated_at=? WHERE source_key=?",
                (message, db.now(), source_key))
            connection.commit()
            summary["failed"].append({"entryId": entry["entryId"], "lemma": entry.get("lemma"), "reason": message})
            emitter.event("failed", entryId=entry["entryId"], current=position, total=total, reason=message)

    connection.execute("UPDATE lexical_import_batches SET status=?,updated_at=? WHERE batch_id=?",
                       ("COMPLETED" if not summary["failed"] else "PARTIAL", db.now(), payload["batchId"]))
    connection.commit()
    emitter.event("summary", **summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one external vocabulary JSON file")
    parser.add_argument("file", type=Path)
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

    audio_encode.find_binary("ffmpeg")
    connection = db.connect(args.db)
    try:
        db.require_ingestion_schema(connection)
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lexical_entries'").fetchone():
            raise ImportError_("The app database has not applied migration 0005. Launch the current Lexium build once, then retry.")
        summary = run_import(args.file, connection, emitter, skip_audio=args.skip_audio)
    except ImportError_ as error:
        emitter.event("error", message=str(error))
        if not args.progress_json:
            print(f"IMPORT FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()

    if not args.progress_json:
        print(f"\nBatch {summary['batchId']} -> {summary['destination']}")
        for label in ("requested", "imported", "updated", "alreadyCurrent", "audioGenerated", "audioReused"):
            print(f"  {label}: {summary[label]}")
        for warning in summary["warnings"]:
            print(f"  warn  {warning}")
        for note in summary["needsPronunciationReview"]:
            print(f"  REVIEW {note}")
        for failure in summary["failed"]:
            print(f"  FAILED {failure['entryId']}: {failure['reason']}")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
