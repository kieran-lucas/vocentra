from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.ingest import db
from tools.ingest.audio_encode import encode, find_binary, verify
from tools.ingest.source_manifest import parse_a1_lines, source_key
from tools.ingest.validator import validate_batch, validate_card

ROOT = Path(__file__).resolve().parents[3]


class IngestionTests(unittest.TestCase):
    def test_authored_pilot_contains_180_valid_ordered_cards(self):
        cards = json.loads((ROOT / "tools/prompts/authored_cards.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cards), 180)
        self.assertEqual([card["sourceIndex"] for card in cards], list(range(1, 181)))
        self.assertEqual(validate_batch(cards), {})

    def test_source_identity_and_order_are_deterministic(self):
        parsed = parse_a1_lines("A1\na, an indefinite article\nabout prep., adv.\nA2\nable adj.")
        self.assertEqual([item["source_key"] for item in parsed], [source_key(1), source_key(2)])
        self.assertEqual(parsed[0]["word"], "a, an")

    def test_validator_rejects_malformed_and_duplicates(self):
        self.assertTrue(validate_card({"word": "bad"}))
        card = json.loads((ROOT / "tools/prompts/golden_cards.json").read_text(encoding="utf-8"))[1]
        failures = validate_batch([card, dict(card)])
        self.assertIn("duplicate sourceKey", failures[card["sourceKey"]])

    def test_status_keeps_failed_gap_and_idempotent_discovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.sqlite3"
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            connection.executescript((ROOT / "src-tauri/migrations/0001_initial.sql").read_text(encoding="utf-8"))
            connection.executescript((ROOT / "src-tauri/migrations/0003_ingestion_audio.sql").read_text(encoding="utf-8"))
            manifest = [
                {"source_key": source_key(index), "source_index": index, "word": f"word{index}", "part_of_speech": "n.", "cefr": "A1"}
                for index in range(1, 5)
            ]
            manifest_path = Path(temporary) / "manifest.jsonl"
            manifest_path.write_text("\n".join(json.dumps(item) for item in manifest), encoding="utf-8")
            job = db.discover(connection, manifest, manifest_path, "https://example.invalid", "test-v1")
            db.discover(connection, manifest, manifest_path, "https://example.invalid", "test-v1")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ingestion_items").fetchone()[0], 4)
            connection.execute("UPDATE ingestion_items SET status='IMPORTED' WHERE source_index IN (1,2,4)")
            connection.execute("UPDATE ingestion_items SET status='FAILED' WHERE source_index=3")
            snapshot = db.status_snapshot(connection, job)
            self.assertEqual(snapshot["last_contiguous"], 2)
            self.assertEqual(snapshot["next_pending"], 3)
            self.assertEqual(snapshot["failed"], 1)
            connection.close()

    def test_import_is_idempotent_and_preserves_membership(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.sqlite3"
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            connection.executescript((ROOT / "src-tauri/migrations/0001_initial.sql").read_text(encoding="utf-8"))
            connection.executescript((ROOT / "src-tauri/migrations/0003_ingestion_audio.sql").read_text(encoding="utf-8"))
            source = {"source_key": source_key(1), "source_index": 1, "word": "a, an", "part_of_speech": "indefinite article", "cefr": "A1"}
            manifest_path = Path(temporary) / "manifest.jsonl"
            manifest_path.write_text(json.dumps(source), encoding="utf-8")
            job = db.discover(connection, [source], manifest_path, "https://example.invalid", "import-v1")
            item = connection.execute("SELECT * FROM ingestion_items WHERE job_id=?", (job,)).fetchone()
            card = json.loads((ROOT / "tools/prompts/golden_cards.json").read_text(encoding="utf-8"))[0]
            db.import_card(connection, card, item, "audio/en-US/test.ogg", "test-voice", "abc")
            db.import_card(connection, card, item, "audio/en-US/test.ogg", "test-voice", "abc")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM vocabulary_entries WHERE source_key=?", (source_key(1),)).fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM block_entries").fetchone()[0], 1)
            connection.close()

    def test_audio_verifier_rejects_non_audio(self):
        with tempfile.NamedTemporaryFile(suffix=".ogg") as file:
            file.write(b"not ogg")
            file.flush()
            with self.assertRaises(Exception):
                verify(Path(file.name))

    def test_audio_encode_records_opus_mono_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            master = Path(temporary) / "master.wav"
            final = Path(temporary) / "final.ogg"
            subprocess.run([find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", "-c:a", "pcm_s16le", str(master)], check=True)
            encode(master, final)
            metadata = verify(final)
            self.assertEqual(metadata["streams"][0]["codec_name"], "opus")
            self.assertEqual(metadata["streams"][0]["channels"], 1)
            self.assertEqual(metadata["encoding_target_bps"], 64000)


if __name__ == "__main__":
    unittest.main()
