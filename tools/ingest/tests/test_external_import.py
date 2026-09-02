from __future__ import annotations

import codecs
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.ingest import audio_profile, db, external_schema
from tools.ingest import import_external_vocabulary as importer

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures/external"
CANONICAL = FIXTURES / "canonical_batch.json"


def canonical() -> dict:
    return json.loads(CANONICAL.read_text(encoding="utf-8"))


def first_sense(payload: dict) -> dict:
    return payload["entries"][0]["senses"][0]


class Collector:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def event(self, stage: str, **fields) -> None:
        self.events.append({"stage": stage, **fields})

    def stages(self) -> list[str]:
        return [event["stage"] for event in self.events]


class Sandbox:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_appdata = os.environ.get("APPDATA")
        self.previous_roots = (importer.MASTER_ROOT, importer.FINAL_ROOT)
        os.environ["APPDATA"] = str(self.root / "appdata")
        importer.MASTER_ROOT = self.root / "master"
        importer.FINAL_ROOT = self.root / "final"
        self.path = self.root / "lexium.sqlite3"
        self.connection = db.connect(self.path)
        db.apply_migrations(self.connection)
        self.create_block("target-root", "Import Test")
        self.create_block("leaf-a", "V2 Leaf A", "target-root")
        self.create_block("leaf-b", "V2 Leaf B", "target-root")

    def close(self) -> None:
        self.connection.close()
        importer.MASTER_ROOT, importer.FINAL_ROOT = self.previous_roots
        if self.previous_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self.previous_appdata
        self.temporary.cleanup()

    def create_block(self, block_id: str, name: str, parent_id: str | None = None) -> None:
        timestamp = db.now()
        self.connection.execute(
            "INSERT INTO blocks(id,parent_id,name,icon_key,sort_order,created_at,updated_at) VALUES(?,?,?,?,0,?,?)",
            (block_id, parent_id, name, "book-open", timestamp, timestamp),
        )
        self.connection.commit()

    def write(self, payload: dict, name: str = "payload.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def run(self, payload: dict, target: str = "leaf-a", skip_audio: bool = True,
            name: str = "payload.json") -> tuple[dict, Collector]:
        collector = Collector()
        summary = importer.run_import(
            self.write(payload, name), target, self.connection, collector, skip_audio=skip_audio
        )
        return summary, collector

    def count(self, sql: str, *values) -> int:
        return self.connection.execute(sql, values).fetchone()[0]

    def install_current_audio(self, pronunciation_id: str, entry_id: str, form_id: str,
                              text: str, app_path: str = "audio/lex/current.ogg") -> None:
        file = db.default_app_data() / app_path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"current-audio")
        timestamp = db.now()
        self.connection.execute(
            "INSERT INTO lexical_audio_assets(pronunciation_id,entry_id,form_id,locale,synthesis_text,fingerprint,app_path,sha256,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (pronunciation_id, entry_id, form_id, "en-US", text, audio_profile.FINGERPRINT,
             app_path, "sha", "current", timestamp, timestamp),
        )
        self.connection.execute(
            "UPDATE vocabulary_entries SET audio_path=?,audio_voice=?,audio_checksum=? WHERE sense_id IN "
            "(SELECT id FROM lexical_senses WHERE pronunciation_id=?)",
            (app_path, audio_profile.VOICE, "sha", pronunciation_id),
        )
        self.connection.commit()


class ExternalContractV2Tests(unittest.TestCase):
    def assert_valid(self, payload: dict) -> external_schema.Report:
        report = external_schema.validate_batch(payload)
        self.assertEqual(report.all_errors(), [])
        self.assertEqual(external_schema.validate_with_json_schema(payload), [])
        return report

    def assert_rejected(self, payload: dict, needle: str, batch_fatal: bool = True) -> None:
        report = external_schema.validate_batch(payload)
        external_schema.merge_json_schema(payload, report)
        problems = report.errors if batch_fatal else report.all_errors()
        self.assertTrue(any(needle.lower() in error.lower() for error in problems), problems)

    def test_active_root_is_exactly_schema_version_and_entries(self):
        payload = canonical()
        self.assertEqual(set(payload), {"schemaVersion", "entries"})
        self.assertEqual(payload["schemaVersion"], 2)
        self.assert_valid(payload)

    def test_schema_is_draft_2020_12_and_v2(self):
        schema = external_schema.load_schema()
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 2)
        self.assertEqual(set(schema["properties"]), {"schemaVersion", "entries"})
        self.assertFalse(schema["additionalProperties"])

    def test_v1_has_a_clean_deprecation_error(self):
        payload = canonical()
        payload["schemaVersion"] = 1
        payload["batchId"] = "old"
        payload["destination"] = {"blockId": None, "blockPath": ["Old"], "createIfMissing": True}
        report = external_schema.validate_batch(payload)
        external_schema.merge_json_schema(payload, report)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(len(report.all_errors()), 1)
        self.assertIn("uses import schema v1", report.errors[0])
        self.assertIn("selected leaf block", report.errors[0])

    def test_every_obsolete_or_embedded_routing_key_is_rejected(self):
        cases = {
            "batchId": "old", "destination": {}, "blockId": "x", "blockPath": ["x"],
            "createIfMissing": True, "targetBlockId": "x", "targetBlock": {},
            "deck": "x", "folder": "x",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                payload = canonical()
                if field == "targetBlockId":
                    payload["entries"][0][field] = value
                else:
                    payload[field] = value
                self.assert_rejected(payload, field)

    def test_operational_fields_remain_recursively_forbidden(self):
        for field, value in (("voice", "en-US-AriaNeural"), ("ttsProvider", "other"),
                             ("audioPath", "x"), ("audioChecksum", "x"),
                             ("ffmpegArgs", []), ("masteryScore", 10), ("dbPath", "x")):
            with self.subTest(field=field):
                payload = canonical()
                first_sense(payload)[field] = value
                self.assert_rejected(payload, "forbidden field")

    def test_locked_lexical_shapes_remain_valid(self):
        payload = canonical()
        pairs = {(entry["lemma"], sense["pos"]) for entry in payload["entries"] for sense in entry["senses"]}
        self.assertIn(("gradient descent", "noun"), pairs)
        self.assertIn(("record", "noun"), pairs)
        self.assertIn(("record", "verb"), pairs)
        self.assert_valid(payload)
        first_sense(payload)["additional"] = {"schemaVersion": 1, "items": []}
        self.assert_valid(payload)
        first_sense(payload).pop("additional")
        self.assert_valid(payload)

    def test_examples_stable_ids_null_policy_and_additional_registry(self):
        payload = canonical()
        first_sense(payload)["examples"][1]["type"] = "meaning"
        self.assert_rejected(payload, "one 'meaning' and one 'usage'", batch_fatal=False)
        payload = canonical()
        first_sense(payload)["additional"]["items"][0]["note"] = ""
        self.assert_rejected(payload, "use null", batch_fatal=False)
        payload = canonical()
        first_sense(payload)["additional"]["items"][0]["attributes"] = {"patternType": "futureSubtype"}
        report = self.assert_valid(payload)
        self.assertTrue(any("not a known Additional v1 subtype" in warning for warning in report.warnings))

    def test_validate_only_requires_no_target_and_touches_no_database(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/ingest/import_external_vocabulary.py"), str(CANONICAL), "--validate-only"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("valid", result.stdout)


class AdditiveImportV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = Sandbox()
        self.addCleanup(self.sandbox.close)

    def test_new_senses_project_one_card_each_into_selected_leaf(self):
        summary, collector = self.sandbox.run(canonical())
        self.assertEqual(summary["added"], 4)
        self.assertEqual(summary["reused"], 0)
        self.assertEqual(summary["alreadyInBlock"], 0)
        self.assertEqual(summary["failed"], [])
        self.assertEqual(summary["destination"], "Import Test / V2 Leaf A")
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM block_entries WHERE block_id='leaf-a'"), 4)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_senses"), 4)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_examples"), 8)
        self.assertIn("validated", collector.stages())
        self.assertEqual(collector.stages().count("added"), 4)

    def test_same_sense_same_target_is_already_and_never_calls_tts(self):
        self.sandbox.run(canonical())
        self.sandbox.connection.execute(
            "UPDATE block_entries SET mastery_score=7,total_reviews=5,again_count=1 WHERE block_id='leaf-a'"
        )
        self.sandbox.connection.commit()
        before = {table: self.sandbox.count(f"SELECT COUNT(*) FROM {table}") for table in
                  ("lexical_entries", "lexical_senses", "vocabulary_entries", "block_entries")}
        with mock.patch.object(importer, "ensure_audio", side_effect=AssertionError("TTS must not run")):
            summary, _ = self.sandbox.run(canonical(), skip_audio=False, name="same-block.json")
        after = {table: self.sandbox.count(f"SELECT COUNT(*) FROM {table}") for table in before}
        self.assertEqual(before, after)
        self.assertEqual(summary["alreadyInBlock"], 4)
        self.assertEqual(summary["added"], 0)
        self.assertEqual(summary["reused"], 0)
        self.assertEqual(summary["audioGenerated"], 0)
        self.assertEqual(tuple(self.sandbox.connection.execute(
            "SELECT mastery_score,total_reviews,again_count FROM block_entries WHERE block_id='leaf-a' LIMIT 1"
        ).fetchone()), (7, 5, 1))

    def test_same_sense_second_leaf_reuses_semantics_audio_and_adds_membership(self):
        self.sandbox.run(canonical())
        for entry in canonical()["entries"]:
            index = importer.entry_index(entry)
            for sense in entry["senses"]:
                form, pronunciation, _ = importer.resolve_sense_audio(entry, sense, index)
                if not self.sandbox.connection.execute(
                    "SELECT 1 FROM lexical_audio_assets WHERE pronunciation_id=?", (pronunciation["pronunciationId"],)
                ).fetchone():
                    self.sandbox.install_current_audio(
                        pronunciation["pronunciationId"], entry["entryId"], form["formId"], form["written"],
                        f"audio/lex/{pronunciation['pronunciationId']}.ogg",
                    )
        with mock.patch.object(importer.audio_service, "generate_production_audio",
                               side_effect=AssertionError("current global audio must be reused")):
            summary, _ = self.sandbox.run(canonical(), target="leaf-b", skip_audio=False, name="second-leaf.json")
        self.assertEqual(summary["reused"], 4)
        self.assertEqual(summary["added"], 0)
        self.assertEqual(summary["audioGenerated"], 0)
        self.assertEqual(summary["audioReused"], 4)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM block_entries WHERE block_id='leaf-a'"), 4)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM block_entries WHERE block_id='leaf-b'"), 4)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_senses"), 4)

    def test_standard_import_never_overwrites_existing_canonical_semantics(self):
        self.sandbox.run(canonical())
        original = self.sandbox.connection.execute(
            "SELECT definition FROM lexical_senses WHERE id='sense_responsible_adjective_01'"
        ).fetchone()[0]
        original_gloss = self.sandbox.connection.execute(
            "SELECT text FROM lexical_glosses WHERE sense_id='sense_responsible_adjective_01'"
        ).fetchone()[0]
        original_examples = [tuple(row) for row in self.sandbox.connection.execute(
            "SELECT en,note FROM lexical_examples WHERE sense_id='sense_responsible_adjective_01' ORDER BY sort_order"
        )]
        original_additional = [tuple(row) for row in self.sandbox.connection.execute(
            "SELECT text,note,attributes FROM lexical_additional_items WHERE sense_id='sense_responsible_adjective_01' ORDER BY sort_order"
        )]
        self.sandbox.connection.execute(
            "UPDATE block_entries SET mastery_score=9,total_reviews=11 WHERE block_id='leaf-a'"
        )
        self.sandbox.connection.commit()

        changed = canonical()
        sense = first_sense(changed)
        sense["definition"] = "definition B"
        sense["glosses"][0]["text"] = "gloss B"
        sense["examples"][0]["en"] = "example B"
        sense["additional"]["items"][0]["note"] = "Additional B"
        summary, _ = self.sandbox.run(changed, target="leaf-b", name="different-semantics.json")
        self.assertEqual(summary["reused"], 4)
        self.assertTrue(any("existing data is preserved" in warning for warning in summary["warnings"]))
        self.assertEqual(self.sandbox.connection.execute(
            "SELECT definition FROM lexical_senses WHERE id='sense_responsible_adjective_01'"
        ).fetchone()[0], original)
        self.assertEqual(self.sandbox.connection.execute(
            "SELECT text FROM lexical_glosses WHERE sense_id='sense_responsible_adjective_01'"
        ).fetchone()[0], original_gloss)
        self.assertEqual([tuple(row) for row in self.sandbox.connection.execute(
            "SELECT en,note FROM lexical_examples WHERE sense_id='sense_responsible_adjective_01' ORDER BY sort_order"
        )], original_examples)
        self.assertEqual([tuple(row) for row in self.sandbox.connection.execute(
            "SELECT text,note,attributes FROM lexical_additional_items WHERE sense_id='sense_responsible_adjective_01' ORDER BY sort_order"
        )], original_additional)
        self.assertEqual(tuple(self.sandbox.connection.execute(
            "SELECT mastery_score,total_reviews FROM block_entries WHERE block_id='leaf-a' LIMIT 1"
        ).fetchone()), (9, 11))

    def test_same_spelling_with_different_stable_ids_is_not_collapsed(self):
        self.sandbox.run(canonical())
        payload = {"schemaVersion": 2, "entries": [copy.deepcopy(canonical()["entries"][0])]}
        entry = payload["entries"][0]
        entry["entryId"] = "entry_responsible_other"
        entry["forms"][0]["formId"] = "form_responsible_other"
        entry["forms"][0]["pronunciations"][0]["pronunciationId"] = "pron_responsible_other"
        sense = entry["senses"][0]
        sense["senseId"] = "sense_responsible_other"
        sense["formId"] = "form_responsible_other"
        sense["pronunciationId"] = "pron_responsible_other"
        for index, example in enumerate(sense["examples"]):
            example["exampleId"] = f"ex_responsible_other_{index}"
        for index, item in enumerate(sense["additional"]["items"]):
            item["id"] = f"add_responsible_other_{index}"
        summary, _ = self.sandbox.run(payload, name="polysemy.json")
        self.assertEqual(summary["added"], 1)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_entries WHERE lemma='responsible'"), 2)
        self.assertTrue(any("stable IDs differ" in warning for warning in summary["warnings"]))

    def test_incompatible_stable_identity_is_conflict_without_tts_or_overwrite(self):
        self.sandbox.run(canonical())
        conflict = {"schemaVersion": 2, "entries": [copy.deepcopy(canonical()["entries"][0])]}
        conflict["entries"][0]["lemma"] = "irresponsible"
        with mock.patch.object(importer, "ensure_audio", side_effect=AssertionError("conflicts must not reach TTS")):
            summary, _ = self.sandbox.run(conflict, target="leaf-b", skip_audio=False, name="conflict.json")
        self.assertEqual(summary["conflicts"], 1)
        self.assertEqual(summary["added"], 0)
        self.assertEqual(summary["reused"], 0)
        self.assertIn("already exists with lemma", summary["conflictDetails"][0]["reason"])
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM block_entries WHERE block_id='leaf-b'"), 0)
        self.assertEqual(self.sandbox.connection.execute(
            "SELECT lemma FROM lexical_entries WHERE id='entry_responsible'"
        ).fetchone()[0], "responsible")

    def test_internal_import_identity_is_generated_not_read_from_json(self):
        first, _ = self.sandbox.run(canonical(), name="one.json")
        second, _ = self.sandbox.run(canonical(), name="two.json")
        self.assertNotEqual(first["importSessionId"], second["importSessionId"])
        rows = self.sandbox.connection.execute(
            "SELECT batch_id,schema_version FROM lexical_import_batches ORDER BY created_at"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["schema_version"] == 2 for row in rows))

    def test_bom_and_one_invalid_entry_partial_failure(self):
        path = self.sandbox.root / "bom.json"
        payload = canonical()
        payload["entries"][1]["senses"][0]["definition"] = ""
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")
        self.assertTrue(path.read_bytes().startswith(codecs.BOM_UTF8))
        summary = importer.run_import(path, "leaf-a", self.sandbox.connection, Collector(), skip_audio=True)
        self.assertEqual(summary["added"], 2)
        self.assertEqual(len(summary["failed"]), 1)
        self.assertEqual(summary["failed"][0]["entryId"], "entry_record")


class TrustedLeafTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = Sandbox()
        self.addCleanup(self.sandbox.close)

    def assert_target_rejected_without_work(self, target: str, needle: str) -> None:
        before = self.sandbox.count("SELECT COUNT(*) FROM lexical_entries")
        with mock.patch.object(importer, "ensure_audio", side_effect=AssertionError("invalid targets must fail before TTS")):
            with self.assertRaises(importer.ImportError_) as caught:
                self.sandbox.run(canonical(), target=target, skip_audio=False)
        self.assertIn(needle, str(caught.exception))
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_entries"), before)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_import_batches"), 0)

    def test_existing_leaf_is_accepted(self):
        summary, _ = self.sandbox.run(canonical())
        self.assertEqual(summary["blockId"], "leaf-a")

    def test_non_leaf_missing_and_deleted_targets_are_rejected(self):
        self.assert_target_rejected_without_work("target-root", "leaf block")
        self.assert_target_rejected_without_work("missing", "does not exist")
        self.sandbox.create_block("deleted", "Deleted")
        self.sandbox.connection.execute("DELETE FROM blocks WHERE id='deleted'")
        self.sandbox.connection.commit()
        self.assert_target_rejected_without_work("deleted", "does not exist")

    def test_json_cannot_create_or_select_any_block(self):
        payload = canonical()
        payload["destination"] = {"blockPath": ["Should Never Exist"], "createIfMissing": True}
        with self.assertRaises(importer.ImportError_):
            self.sandbox.run(payload)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM blocks WHERE name='Should Never Exist'"), 0)

    def test_leaf_is_rechecked_before_commit_if_it_gains_a_child_during_audio(self):
        def add_child_during_audio(*_args, **_kwargs):
            if not self.sandbox.connection.execute("SELECT 1 FROM blocks WHERE id='late-child'").fetchone():
                self.sandbox.create_block("late-child", "Late child", "leaf-a")
            return {"appPath": "audio/lex/mock.ogg", "sha256": "sha", "generated": True,
                    "status": "current", "synthesisText": "mock", "masterPath": "mock.mp3",
                    "durationSeconds": 1.0, "needsPersist": True}

        with mock.patch.object(importer, "ensure_audio", side_effect=add_child_during_audio):
            summary, _ = self.sandbox.run(canonical(), skip_audio=False)
        self.assertEqual(summary["added"], 0)
        self.assertEqual(len(summary["failed"]), 4)
        self.assertTrue(all("leaf block" in failure["reason"] for failure in summary["failed"]))
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM block_entries WHERE block_id='leaf-a'"), 0)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_entries"), 0)

    def test_target_deleted_during_audio_aborts_without_membership_or_lexical_rows(self):
        def delete_target_during_audio(*_args, **_kwargs):
            self.sandbox.connection.execute("DELETE FROM blocks WHERE id='leaf-a'")
            self.sandbox.connection.commit()
            return {"appPath": "audio/lex/mock.ogg", "sha256": "sha", "generated": True,
                    "status": "current", "synthesisText": "mock", "masterPath": "mock.mp3",
                    "durationSeconds": 1.0, "needsPersist": True}

        with mock.patch.object(importer, "ensure_audio", side_effect=delete_target_during_audio):
            summary, _ = self.sandbox.run(canonical(), skip_audio=False)
        self.assertEqual(summary["added"], 0)
        self.assertEqual(len(summary["failed"]), 4)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_entries"), 0)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM block_entries WHERE block_id='leaf-a'"), 0)


class ProductionLockAndSourceWiringTests(unittest.TestCase):
    def test_audio_profile_and_fingerprint_are_unchanged(self):
        described = audio_profile.describe()
        self.assertEqual(described["voice"], "en-US-JennyNeural")
        self.assertEqual(described["sourceFormat"], "audio-24khz-48kbitrate-mono-mp3")
        self.assertEqual(described["finalCodec"], "opus")
        self.assertEqual(described["finalContainer"], "ogg")
        self.assertEqual(described["finalTargetBps"], 64000)
        self.assertEqual(described["finalChannels"], 1)
        for token in ("en-US-JennyNeural", "audio-24khz-48kbitrate-mono-mp3", "opus-64k-mono-vbr"):
            self.assertIn(token, audio_profile.FINGERPRINT)

    def test_stale_fingerprint_still_invalidates_reused_audio(self):
        sandbox = Sandbox()
        try:
            sandbox.run(canonical())
            sandbox.install_current_audio(
                "pron_responsible_en_us_01", "entry_responsible", "form_responsible_01",
                "responsible", "audio/lex/stale-check.ogg",
            )
            sandbox.connection.execute(
                "UPDATE lexical_audio_assets SET fingerprint='old-profile' WHERE pronunciation_id='pron_responsible_en_us_01'"
            )
            sandbox.connection.commit()
            self.assertIsNone(importer.audio_is_current(
                sandbox.connection, "pron_responsible_en_us_01", "responsible"
            ))
        finally:
            sandbox.close()

    def test_frontend_exposes_only_leaf_option_and_passes_selected_id(self):
        app = (ROOT / "src/App.svelte").read_text(encoding="utf-8")
        tile = (ROOT / "src/lib/components/blocks/BlockTile.svelte").read_text(encoding="utf-8")
        api = (ROOT / "src/lib/api/external-import.ts").read_text(encoding="utf-8")
        manager = (ROOT / "src/lib/components/manage/VocabularyManager.svelte").read_text(encoding="utf-8")
        self.assertNotIn("Import JSON", app)
        self.assertNotIn("Import JSON", manager)
        self.assertIn("block.childCount===0", tile)
        self.assertIn("Import vocabulary", tile)
        self.assertIn("targetBlockId", api)
        self.assertIn("targetBlockId={importTarget.block.id}", app)

    def test_sidecar_build_uses_v2_schema_in_hash_bundle_and_smoke(self):
        build = (ROOT / "tools/build_importer_sidecar.ps1").read_text(encoding="utf-8")
        self.assertIn("external_vocabulary_import.v2.schema.json", build)
        self.assertIn("@($sources.FullName) + @($schema", build)
        self.assertIn("--validate-only", build)


if __name__ == "__main__":
    unittest.main()
