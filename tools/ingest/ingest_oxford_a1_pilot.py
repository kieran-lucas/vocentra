# /// script
# requires-python = ">=3.11"
# dependencies = ["edge-tts==7.2.7", "pypdf>=6,<7"]
# ///
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

from tools.ingest import audio_encode, audio_microsoft, audio_profile, audio_service, critic, db
from tools.ingest.generator import load_authored_cards, write_normalized
from tools.ingest.source_manifest import SOURCE_URL, SOURCE_VERSION, read_manifest
from tools.ingest.status import format_status
from tools.ingest.validator import validate_card

MANIFEST_PATH = ROOT / "data/source/oxford_a1_pilot_manifest.jsonl"
AUTHORED_PATH = ROOT / "tools/prompts/authored_cards.json"
NORMALIZED_PATH = ROOT / "data/generated/oxford_a1_pilot_cards.jsonl"
FAILED_PATH = ROOT / "data/generated/failed.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resumable Oxford A1 pilot ingestion")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight", action="store_true", help="Process source indices 1-8")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--source-index", type=int)
    parser.add_argument("--source-key")
    parser.add_argument("--regenerate-audio", action="store_true")
    parser.add_argument("--regenerate-card", action="store_true")
    parser.add_argument("--db", type=Path)
    return parser.parse_args()


def select_rows(connection: sqlite3.Connection, job_id: str, args: argparse.Namespace) -> list[sqlite3.Row]:
    clauses = ["job_id=?"]
    values: list[object] = [job_id]
    if args.preflight:
        clauses.append("source_index<=8")
    if args.source_index:
        clauses.append("source_index=?")
        values.append(args.source_index)
    if args.source_key:
        clauses.append("source_key=?")
        values.append(args.source_key)
    return connection.execute(f"SELECT * FROM ingestion_items WHERE {' AND '.join(clauses)} ORDER BY source_index", values).fetchall()


def update_item(connection: sqlite3.Connection, source_key: str, **values) -> None:
    values["updated_at"] = db.now()
    assignments = ",".join(f"{name}=?" for name in values)
    connection.execute(f"UPDATE ingestion_items SET {assignments} WHERE source_key=?", (*values.values(), source_key))
    connection.commit()


def reset_requested(connection: sqlite3.Connection, rows: list[sqlite3.Row], args: argparse.Namespace) -> None:
    for row in rows:
        if args.retry_failed and row["status"] == "FAILED":
            fallback = "VALIDATED" if row["validation_json"] else "GENERATED" if row["card_json"] else "DISCOVERED"
            update_item(connection, row["source_key"], status=fallback, last_error=None)
        if args.regenerate_card:
            update_item(connection, row["source_key"], status="DISCOVERED", stage="generation", card_json=None, critic_json=None, validation_json=None, final_json_checksum=None, last_error=None)
        if args.regenerate_audio:
            update_item(connection, row["source_key"], status="VALIDATED", stage="audio", audio_master_path=None, audio_path=None, audio_checksum=None, audio_verified=0, last_error=None)


def prepare_text(connection: sqlite3.Connection, row: sqlite3.Row, source: dict, authored: dict[str, dict]) -> dict | None:
    card = json.loads(row["card_json"]) if row["card_json"] else authored.get(row["source_key"])
    if not card:
        return None
    if not row["card_json"]:
        update_item(connection, row["source_key"], status="GENERATED", stage="generation", card_json=json.dumps(card, ensure_ascii=False), generator_model="OpenAI Codex agent", generator_version="pilot-v1", attempt_count=row["attempt_count"] + 1)
    review = critic.review_card(card, source)
    if not review["pass"] or review["overall"] < 9.3:
        update_item(connection, row["source_key"], status="REPAIR_NEEDED", stage="critic", critic_json=json.dumps(review, ensure_ascii=False), last_error="; ".join(review["repairInstructions"]))
        return None
    update_item(connection, row["source_key"], status="REVIEWED", stage="critic", critic_json=json.dumps(review, ensure_ascii=False), critic_model="Lexium independent rubric", critic_version="pilot-v1", last_error=None)
    errors = validate_card(card)
    validation = {"pass": not errors, "errors": errors, "validator": "lexium-validator-v1"}
    if errors:
        update_item(connection, row["source_key"], status="REPAIR_NEEDED", stage="validation", validation_json=json.dumps(validation), last_error="; ".join(errors))
        return None
    checksum = hashlib.sha256(json.dumps(card, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    update_item(connection, row["source_key"], status="VALIDATED", stage="validation", validation_json=json.dumps(validation), final_json_checksum=checksum, last_error=None)
    return card


def process_audio_and_import(connection: sqlite3.Connection, row: sqlite3.Row, card: dict) -> None:
    stem = row["source_key"].replace(":", "_")
    master = ROOT / f"data/audio-master/en-US/{stem}{audio_microsoft.MASTER_SUFFIX}"
    final = ROOT / f"data/audio-final/en-US/{stem}.ogg"
    app_relative = f"audio/en-US/{stem}.ogg"
    app_audio = db.default_app_data() / app_relative
    current = connection.execute("SELECT * FROM ingestion_items WHERE source_key=?", (row["source_key"],)).fetchone()
    if not final.exists():
        update_item(connection, row["source_key"], status="AUDIO_REQUESTED", stage="audio", audio_voice=audio_profile.VOICE)
        audio_service.generate_production_audio(audio_microsoft.card_synthesis_text(card), master, final)
    update_item(connection, row["source_key"], status="AUDIO_DONE", stage="audio", audio_master_path=master.relative_to(ROOT).as_posix(), audio_voice=audio_profile.VOICE)
    metadata = audio_encode.verify(final)
    app_audio.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, app_audio)
    update_item(connection, row["source_key"], status="ENCODED", stage="encode", audio_path=app_relative, audio_checksum=metadata["sha256"], audio_verified=1, validation_json=current["validation_json"])
    refreshed = connection.execute("SELECT * FROM ingestion_items WHERE source_key=?", (row["source_key"],)).fetchone()
    db.import_card(connection, card, refreshed, app_relative, audio_profile.VOICE, metadata["sha256"])


def export_failures(connection: sqlite3.Connection, job_id: str) -> None:
    rows = connection.execute("SELECT source_key,source_index,word,stage,last_error,attempt_count FROM ingestion_items WHERE job_id=? AND status='FAILED' ORDER BY source_index", (job_id,)).fetchall()
    FAILED_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAILED_PATH.write_text(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(connection: sqlite3.Connection, job_id: str, note: str) -> None:
    snapshot = db.status_snapshot(connection, job_id)
    report = ROOT / "reports/oxford_a1_pilot_report.md"
    report.write_text(
        "# Oxford A1 Pilot Report\n\n"
        f"Status note: {note}\n\n"
        f"- Target: {snapshot['target']}\n- Generated: {snapshot['generated']}\n- Reviewed PASS: {snapshot['reviewed']}\n"
        f"- Validated: {snapshot['validated']}\n- Audio generated: {snapshot['audio_generated']}\n- Audio verified: {snapshot['audio_verified']}\n"
        f"- Imported: {snapshot['imported']}\n- Last contiguous: {snapshot['last_contiguous']}\n- Next pending: {snapshot['next_pending']}\n"
        f"- Voice: `{audio_microsoft.VOICE}` ({audio_microsoft.PROVIDER})\n"
        f"- Edge source format: `{audio_microsoft.SOURCE_FORMAT}`\n"
        "- Final format: Ogg Opus, 64 kbps target, mono\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    manifest = read_manifest(MANIFEST_PATH)
    if args.dry_run:
        print(f"Dry run: {len(manifest)} deterministic source records; no API calls or mutations.")
        print(f"First: {manifest[0]['source_key']} {manifest[0]['word']} | Last: {manifest[-1]['source_key']} {manifest[-1]['word']}")
        return 0
    connection = db.connect(args.db)
    try:
        job_id = db.discover(connection, manifest, MANIFEST_PATH, SOURCE_URL, SOURCE_VERSION)
    except RuntimeError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    if args.status or args.discover_only:
        print(format_status(connection, job_id))
        return 0
    rows = select_rows(connection, job_id, args)
    reset_requested(connection, rows, args)
    rows = select_rows(connection, job_id, args)
    authored = load_authored_cards(AUTHORED_PATH)
    ready: list[tuple[sqlite3.Row, dict]] = []
    try:
        pending_rows = [row for row in rows if row["status"] != "IMPORTED" or args.regenerate_audio or args.regenerate_card]
        for offset in range(0, len(pending_rows), 8):
            batch = pending_rows[offset:offset + 8]
            print(f"SEMANTIC BATCH {batch[0]['source_index']:03d}-{batch[-1]['source_index']:03d}")
            for row in batch:
                source = manifest[row["source_index"] - 1]
                card = prepare_text(connection, row, source, authored)
                if not card:
                    if row["source_key"] not in authored:
                        print(f"PENDING {row['source_key']}: no generated card artifact yet")
                    continue
                ready.append((row, card))
        existing = [json.loads(item["card_json"]) for item in connection.execute("SELECT card_json FROM ingestion_items WHERE job_id=? AND card_json IS NOT NULL ORDER BY source_index", (job_id,))]
        write_normalized(existing, NORMALIZED_PATH)
        for row, card in ready:
            process_audio_and_import(connection, row, card)
            print(f"IMPORTED {row['source_index']:03d}/180 {row['source_key']} {row['word']}")
    except Exception as error:
        active = row if "row" in locals() else None
        if active is not None:
            db.record_failure(connection, active["source_key"], "pipeline", type(error).__name__, str(error), active["attempt_count"] + 1)
        export_failures(connection, job_id)
        write_report(connection, job_id, f"Pipeline failure: {error}")
        raise
    existing = [json.loads(item["card_json"]) for item in connection.execute("SELECT card_json FROM ingestion_items WHERE job_id=? AND card_json IS NOT NULL ORDER BY source_index", (job_id,))]
    write_normalized(existing, NORMALIZED_PATH)
    export_failures(connection, job_id)
    write_report(connection, job_id, "Latest run completed")
    print(format_status(connection, job_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
