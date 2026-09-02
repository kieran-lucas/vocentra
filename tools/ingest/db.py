from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

NAMESPACE = uuid.UUID("7314384a-5d94-42aa-a790-2933bde9e548")
ROOT_SOURCE_KEY = "lexium:curriculum:oxford5000"
PILOT_SOURCE_KEY = "lexium:pilot:oxford3000:a1:180"
BATCH_ID = "oxford3000-a1-pilot-180-v1"
FULL_BATCH_ID = "oxford5000-full-american-v1"
FULL_MANIFEST_VERSION = "american-cefr-2019-full-v1"
LEVEL_SOURCE_KEYS = {level: f"lexium:curriculum:oxford5000:level:{level.lower()}" for level in ("A1", "A2", "B1", "B2", "C1")}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(value: str) -> str:
    return str(uuid.uuid5(NAMESPACE, value))


def default_app_data() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "com.lexium.desktop"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or default_app_data() / "lexium.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def require_ingestion_schema(connection: sqlite3.Connection) -> None:
    found = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ingestion_items'").fetchone()
    if not found:
        raise RuntimeError("The app database has not applied migration 0003. Launch the current Lexium build once, then resume.")


def ensure_blocks(connection: sqlite3.Connection) -> tuple[str, str]:
    timestamp = now()
    root = connection.execute("SELECT id FROM blocks WHERE source_key=?", (ROOT_SOURCE_KEY,)).fetchone()
    if not root:
        root = connection.execute("SELECT id FROM blocks WHERE parent_id IS NULL AND name='Oxford 5000' ORDER BY created_at LIMIT 1").fetchone()
    root_id = root["id"] if root else stable_id(ROOT_SOURCE_KEY)
    connection.execute(
        "INSERT INTO blocks(id,parent_id,name,icon_key,sort_order,created_at,updated_at,source_key) VALUES(?,NULL,'Oxford 5000','library',10,?,?,?) ON CONFLICT(id) DO UPDATE SET source_key=excluded.source_key,updated_at=excluded.updated_at",
        (root_id, timestamp, timestamp, ROOT_SOURCE_KEY),
    )
    leaf = connection.execute("SELECT id FROM blocks WHERE source_key IN (?,?) ORDER BY created_at LIMIT 1", (PILOT_SOURCE_KEY, LEVEL_SOURCE_KEYS["A1"])).fetchone()
    if not leaf:
        leaf = connection.execute("SELECT id FROM blocks WHERE parent_id=? AND name IN ('A1 Pilot','A1') ORDER BY created_at LIMIT 1", (root_id,)).fetchone()
    leaf_id = leaf["id"] if leaf else stable_id(PILOT_SOURCE_KEY)
    connection.execute(
        "INSERT INTO blocks(id,parent_id,name,icon_key,sort_order,created_at,updated_at,source_key) VALUES(?,?,'A1','education',0,?,?,?) ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id,name=excluded.name,icon_key=excluded.icon_key,source_key=excluded.source_key,updated_at=excluded.updated_at",
        (leaf_id, root_id, timestamp, timestamp, LEVEL_SOURCE_KEYS["A1"]),
    )
    return root_id, leaf_id


def ensure_curriculum_blocks(connection: sqlite3.Connection) -> tuple[str, dict[str, str]]:
    root_id, a1_id = ensure_blocks(connection)
    timestamp = now()
    level_ids = {"A1": a1_id}
    icons = {"A1": "education", "A2": "book-open", "B1": "layers", "B2": "brain", "C1": "sparkles"}
    for sort_order, level in enumerate(("A2", "B1", "B2", "C1"), 1):
        key = LEVEL_SOURCE_KEYS[level]
        found = connection.execute("SELECT id FROM blocks WHERE source_key=?", (key,)).fetchone()
        block_id = found["id"] if found else stable_id(key)
        connection.execute(
            "INSERT INTO blocks(id,parent_id,name,icon_key,sort_order,created_at,updated_at,source_key) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id,name=excluded.name,icon_key=excluded.icon_key,sort_order=excluded.sort_order,source_key=excluded.source_key,updated_at=excluded.updated_at",
            (block_id, root_id, level, icons[level], sort_order, timestamp, timestamp, key),
        )
        level_ids[level] = block_id
    connection.commit()
    return root_id, level_ids


def discover(connection: sqlite3.Connection, manifest: list[dict], manifest_path: Path, source_url: str, version: str) -> str:
    require_ingestion_schema(connection)
    _, leaf_id = ensure_blocks(connection)
    timestamp = now()
    payload = manifest_path.read_bytes()
    checksum = hashlib.sha256(payload).hexdigest()
    manifest_id = stable_id(f"manifest:{version}")
    connection.execute(
        "INSERT INTO source_manifests(id,source_name,source_level,version,source_url,manifest_path,manifest_checksum,item_count,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_name,source_level,version) DO UPDATE SET source_url=excluded.source_url,manifest_path=excluded.manifest_path,manifest_checksum=excluded.manifest_checksum,item_count=excluded.item_count,updated_at=excluded.updated_at",
        (manifest_id, "oxford3000", "A1", version, source_url, manifest_path.as_posix(), checksum, len(manifest), timestamp, timestamp),
    )
    job_id = stable_id(f"job:{BATCH_ID}")
    connection.execute(
        "INSERT INTO ingestion_jobs(id,manifest_id,target_block_id,batch_id,target_count,status,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE',?,?) ON CONFLICT(batch_id) DO UPDATE SET target_count=excluded.target_count,target_block_id=excluded.target_block_id,updated_at=excluded.updated_at",
        (job_id, manifest_id, leaf_id, BATCH_ID, len(manifest), timestamp, timestamp),
    )
    for item in manifest:
        connection.execute(
            "INSERT INTO ingestion_items(source_key,job_id,source_index,word,part_of_speech,cefr,status,stage,batch_id,created_at,updated_at) VALUES(?,?,?,?,?,?,'DISCOVERED','discovery',?,?,?) ON CONFLICT(source_key) DO UPDATE SET source_index=excluded.source_index,word=excluded.word,part_of_speech=excluded.part_of_speech,cefr=excluded.cefr,updated_at=excluded.updated_at",
            (item["source_key"], job_id, item["source_index"], item["word"], item["part_of_speech"], item["cefr"], BATCH_ID, timestamp, timestamp),
        )
    connection.commit()
    return job_id


def discover_full(connection: sqlite3.Connection, manifest: list[dict], manifest_path: Path, source_url: str) -> str:
    require_ingestion_schema(connection)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(ingestion_items)")}
    if not {"target_block_id", "source_name"}.issubset(columns):
        raise RuntimeError("Migration 0004 is not applied. Launch the latest Lexium build once, then resume.")
    root_id, level_ids = ensure_curriculum_blocks(connection)
    timestamp = now()
    checksum = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest_id = stable_id(f"manifest:{FULL_MANIFEST_VERSION}")
    connection.execute(
        "INSERT INTO source_manifests(id,source_name,source_level,version,source_url,manifest_path,manifest_checksum,item_count,created_at,updated_at) VALUES(?,'oxford5000_curriculum','A1-C1',?,?,?,?,?,?,?) ON CONFLICT(source_name,source_level,version) DO UPDATE SET source_url=excluded.source_url,manifest_path=excluded.manifest_path,manifest_checksum=excluded.manifest_checksum,item_count=excluded.item_count,updated_at=excluded.updated_at",
        (manifest_id, FULL_MANIFEST_VERSION, source_url, manifest_path.as_posix(), checksum, len(manifest), timestamp, timestamp),
    )
    job_id = stable_id(f"job:{FULL_BATCH_ID}")
    connection.execute(
        "INSERT INTO ingestion_jobs(id,manifest_id,target_block_id,batch_id,target_count,status,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE',?,?) ON CONFLICT(batch_id) DO UPDATE SET manifest_id=excluded.manifest_id,target_count=excluded.target_count,target_block_id=excluded.target_block_id,updated_at=excluded.updated_at",
        (job_id, manifest_id, root_id, FULL_BATCH_ID, len(manifest), timestamp, timestamp),
    )
    for item in manifest:
        connection.execute(
            """INSERT INTO ingestion_items(source_key,job_id,source_index,word,part_of_speech,cefr,status,stage,batch_id,created_at,updated_at,target_block_id,source_name)
               VALUES(?,?,?,?,?,?,'DISCOVERED','discovery',?,?,?,?,?)
               ON CONFLICT(source_key) DO UPDATE SET job_id=excluded.job_id,source_index=excluded.source_index,word=excluded.word,part_of_speech=excluded.part_of_speech,cefr=excluded.cefr,batch_id=excluded.batch_id,target_block_id=excluded.target_block_id,source_name=excluded.source_name,updated_at=excluded.updated_at""",
            (item["source_key"], job_id, item["source_index"], item["word"], item["part_of_speech"], item["cefr"], FULL_BATCH_ID, timestamp, timestamp, level_ids[item["cefr"]], item["source_name"]),
        )
    connection.commit()
    return job_id


def record_failure(connection: sqlite3.Connection, source_key: str, stage: str, code: str, message: str, attempts: int) -> None:
    timestamp = now()
    connection.execute("UPDATE ingestion_items SET status='FAILED',stage=?,last_error=?,attempt_count=?,updated_at=? WHERE source_key=?", (stage, message, attempts, timestamp, source_key))
    connection.execute("INSERT INTO ingestion_failures(id,source_key,stage,error_code,error_message,attempts,created_at) VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), source_key, stage, code, message, attempts, timestamp))
    connection.commit()


def import_card(connection: sqlite3.Connection, card: dict, item: sqlite3.Row, app_audio_path: str, voice: str, checksum: str) -> None:
    timestamp = now()
    existing = connection.execute("SELECT id FROM vocabulary_entries WHERE source_key=?", (item["source_key"],)).fetchone()
    entry_id = existing["id"] if existing else stable_id(f"entry:{item['source_key']}")
    block_id = item["target_block_id"] if "target_block_id" in item.keys() and item["target_block_id"] else connection.execute("SELECT target_block_id FROM ingestion_jobs WHERE id=?", (item["job_id"],)).fetchone()[0]
    source_name = item["source_name"] if "source_name" in item.keys() and item["source_name"] else "oxford3000"
    extras = card.get("extras") or {}
    with connection:
        connection.execute(
            """INSERT INTO vocabulary_entries(id,word,ipa,part_of_speech,vi_meaning,en_definition,example_meaning_en,example_meaning_vi,example_usage_en,example_usage_vi,collocations,usage_note,register,word_family,synonyms,antonyms,accepted_answers,extra_metadata,created_at,updated_at,source_key,source_name,source_level,source_index,cefr,audio_path,audio_voice,audio_checksum)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET word=excluded.word,ipa=excluded.ipa,part_of_speech=excluded.part_of_speech,vi_meaning=excluded.vi_meaning,en_definition=excluded.en_definition,example_meaning_en=excluded.example_meaning_en,example_meaning_vi=excluded.example_meaning_vi,example_usage_en=excluded.example_usage_en,example_usage_vi=excluded.example_usage_vi,collocations=excluded.collocations,usage_note=excluded.usage_note,register=excluded.register,word_family=excluded.word_family,synonyms=excluded.synonyms,antonyms=excluded.antonyms,accepted_answers=excluded.accepted_answers,extra_metadata=excluded.extra_metadata,source_index=excluded.source_index,cefr=excluded.cefr,audio_path=excluded.audio_path,audio_voice=excluded.audio_voice,audio_checksum=excluded.audio_checksum,updated_at=excluded.updated_at""",
            (entry_id, card["word"], card["ipa"], card["partOfSpeech"], card["viMeaning"], card["enDefinition"], card["exampleMeaning"]["en"], card["exampleMeaning"]["vi"], card["exampleUsage"]["en"], card["exampleUsage"]["vi"], json.dumps(extras.get("collocations", []), ensure_ascii=False), card["exampleUsage"].get("note") or extras.get("usage_note"), extras.get("register"), json.dumps(extras.get("word_family", []), ensure_ascii=False), json.dumps(extras.get("synonyms", []), ensure_ascii=False), json.dumps(extras.get("antonyms", []), ensure_ascii=False), json.dumps(card["acceptedAnswers"], ensure_ascii=False), json.dumps(extras, ensure_ascii=False), timestamp, timestamp, item["source_key"], source_name, item["cefr"], item["source_index"], item["cefr"], app_audio_path, voice, checksum),
        )
        actual_entry_id = connection.execute("SELECT id FROM vocabulary_entries WHERE source_key=?", (item["source_key"],)).fetchone()[0]
        connection.execute("INSERT INTO block_entries(id,block_id,entry_id,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(block_id,entry_id) DO NOTHING", (stable_id(f"membership:{block_id}:{actual_entry_id}"), block_id, actual_entry_id, timestamp, timestamp))
        connection.execute("UPDATE ingestion_items SET status='IMPORTED',stage='import',audio_voice=?,audio_path=?,audio_checksum=?,audio_verified=1,last_error=NULL,updated_at=? WHERE source_key=?", (voice, app_audio_path, checksum, timestamp, item["source_key"]))


def status_snapshot(connection: sqlite3.Connection, job_id: str) -> dict[str, int | None]:
    rows = connection.execute("SELECT * FROM ingestion_items WHERE job_id=? ORDER BY source_index", (job_id,)).fetchall()
    imported = {row["source_index"] for row in rows if row["status"] == "IMPORTED"}
    contiguous = 0
    for index in range(1, len(rows) + 1):
        if index not in imported:
            break
        contiguous = index
    pending = next((row["source_index"] for row in rows if row["status"] != "IMPORTED"), None)
    def count(predicate): return sum(1 for row in rows if predicate(row))
    return {
        "target": len(rows), "discovered": len(rows),
        "generated": count(lambda row: row["card_json"] is not None),
        "reviewed": count(lambda row: row["critic_json"] and json.loads(row["critic_json"]).get("pass")),
        "repair_needed": count(lambda row: row["status"] == "REPAIR_NEEDED"),
        "validated": count(lambda row: row["validation_json"] and json.loads(row["validation_json"]).get("pass")),
        "audio_generated": count(lambda row: row["audio_master_path"] is not None),
        "audio_encoded": count(lambda row: row["audio_path"] is not None),
        "audio_verified": count(lambda row: row["audio_verified"] == 1),
        "imported": len(imported), "last_contiguous": contiguous,
        "next_pending": pending, "pending": len(rows) - len(imported),
        "failed": count(lambda row: row["status"] == "FAILED"),
    }
