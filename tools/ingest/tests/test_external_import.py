from __future__ import annotations

import codecs
import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.ingest import audio_profile, db, external_schema
from tools.ingest import import_external_vocabulary as importer

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures/external"
CANONICAL = FIXTURES / "canonical_batch.json"


def canonical() -> dict:
    return json.loads(CANONICAL.read_text(encoding="utf-8"))


def first_sense(batch: dict) -> dict:
    return batch["entries"][0]["senses"][0]


class Collector:
    """Emitter stand-in that keeps the JSON-lines progress events."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def event(self, stage: str, **fields) -> None:
        self.events.append({"stage": stage, **fields})

    def stages(self) -> list[str]:
        return [event["stage"] for event in self.events]


class Sandbox:
    """Temporary app-data dir, master/final roots and migrated database."""

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

    def close(self) -> None:
        self.connection.close()
        importer.MASTER_ROOT, importer.FINAL_ROOT = self.previous_roots
        if self.previous_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self.previous_appdata
        self.temporary.cleanup()

    def write(self, batch: dict, name: str = "batch.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        return path

    def run(self, batch: dict, skip_audio: bool = True, name: str = "batch.json") -> tuple[dict, Collector]:
        collector = Collector()
        summary = importer.run_import(self.write(batch, name), self.connection, collector, skip_audio=skip_audio)
        return summary, collector

    def count(self, sql: str, *values) -> int:
        return self.connection.execute(sql, values).fetchone()[0]


class ExternalContractTests(unittest.TestCase):
    """The published schema and the importer's gate agree, and neither can be
    talked into changing how audio is produced."""

    def assert_valid(self, batch: dict) -> external_schema.Report:
        report = external_schema.validate_batch(batch)
        self.assertEqual(report.all_errors(), [], "application validator rejected a valid batch")
        self.assertEqual(external_schema.validate_with_json_schema(batch), [],
                         "published JSON Schema rejected a valid batch")
        return report

    def assert_rejected(self, batch: dict, needle: str) -> None:
        """The batch or one of its entries is refused, naming the reason."""
        report = external_schema.validate_batch(batch)
        problems = report.all_errors()
        self.assertTrue(problems, f"expected a rejection mentioning {needle!r}")
        self.assertTrue(any(needle in error for error in problems),
                        f"no error mentioned {needle!r}: {problems}")

    def assert_batch_rejected(self, batch: dict, needle: str) -> None:
        """The whole file is refused, not just one entry."""
        report = external_schema.validate_batch(batch)
        self.assertFalse(report.ok, f"expected the batch to be refused over {needle!r}")
        self.assertTrue(any(needle in error for error in report.errors),
                        f"no batch-level error mentioned {needle!r}: {report.errors}")

    def test_canonical_fixture_is_valid_under_both_validators(self):
        report = self.assert_valid(canonical())
        self.assertTrue(any("not in this batch" in warning for warning in report.warnings))
        self.assertTrue(any("2 en-US pronunciations" in warning for warning in report.warnings))

    def test_generation_contract_worked_example_still_validates(self):
        """The portable LLM contract must stay importable on its own terms."""
        import re

        contract = ROOT / "tools/prompts/external_vocab_generation_v1.md"
        fence = "```" + "json"
        pattern = fence + chr(10) + "(.*?)" + chr(10) + "```"
        blocks = re.findall(pattern, contract.read_text(encoding="utf-8"), re.S)
        documents = []
        for block in blocks:
            if '"entries"' not in block or '"schemaVersion"' not in block:
                continue
            try:
                documents.append(json.loads(block))
            except json.JSONDecodeError:
                continue  # §1 illustrates the shape with /* ... */ placeholders
        self.assertTrue(documents, "the contract must contain one complete worked example")
        for document in documents:
            self.assertGreaterEqual(len(document["entries"]), 3)
            self.assert_valid(document)

    def test_generation_contract_lists_every_forbidden_field(self):
        contract = (ROOT / "tools/prompts/external_vocab_generation_v1.md").read_text(encoding="utf-8").lower()
        undocumented = sorted(field for field in external_schema.HARD_FORBIDDEN | external_schema.CONTEXT_FORBIDDEN
                              if field not in contract)
        self.assertEqual(undocumented, [], "fields the importer refuses but the contract never mentions")

    def test_schema_file_is_draft_2020_12_and_loadable(self):
        schema = external_schema.load_schema()
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], external_schema.SCHEMA_VERSION)

    def test_valid_simple_noun_verb_adjective_technical_and_multiword(self):
        batch = canonical()
        kinds = {(entry["lemma"], sense["pos"]) for entry in batch["entries"] for sense in entry["senses"]}
        self.assertIn(("responsible", "adjective"), kinds)
        self.assertIn(("record", "noun"), kinds)
        self.assertIn(("record", "verb"), kinds)
        self.assertIn(("gradient descent", "noun"), kinds)
        self.assert_valid(batch)

    def test_empty_additional_is_valid(self):
        batch = canonical()
        first_sense(batch)["additional"] = {"schemaVersion": 1, "items": []}
        self.assert_valid(batch)

    def test_absent_additional_is_valid(self):
        batch = canonical()
        first_sense(batch).pop("additional")
        self.assert_valid(batch)

    def test_unknown_future_subtype_is_preserved_with_a_warning(self):
        batch = canonical()
        first_sense(batch)["additional"]["items"][0]["attributes"] = {"patternType": "ergativeAlternation"}
        report = self.assert_valid(batch)
        self.assertTrue(any("not a known v1 subtype" in warning for warning in report.warnings))

    def test_unknown_kind_is_rejected_because_the_architecture_is_fixed(self):
        batch = canonical()
        first_sense(batch)["additional"]["items"][0]["kind"] = "etymology"
        self.assert_rejected(batch, "is not one of")

    def test_unresolved_cross_reference_warns_and_survives_import(self):
        sandbox = Sandbox()
        try:
            summary, _ = sandbox.run(canonical())
            self.assertTrue(any("unresolved" in warning for warning in summary["warnings"]))
            stored = sandbox.connection.execute(
                "SELECT target_entry_id,unresolved FROM lexical_additional_items WHERE id='add_responsible_relation_01'"
            ).fetchone()
            self.assertEqual(stored["target_entry_id"], "entry_accountable")
            self.assertEqual(stored["unresolved"], 1)
        finally:
            sandbox.close()

    def test_missing_entry_id_is_rejected(self):
        batch = canonical()
        batch["entries"][0].pop("entryId")
        self.assert_rejected(batch, "entryId is required")

    def test_duplicate_sense_id_is_rejected(self):
        batch = canonical()
        batch["entries"][1]["senses"][1]["senseId"] = batch["entries"][1]["senses"][0]["senseId"]
        self.assert_rejected(batch, "duplicate senses id")

    def test_duplicate_entry_id_is_rejected(self):
        batch = canonical()
        batch["entries"][1]["entryId"] = batch["entries"][0]["entryId"]
        self.assert_batch_rejected(batch, "duplicate entryId")

    def test_empty_string_where_null_is_required_is_rejected(self):
        batch = canonical()
        first_sense(batch)["additional"]["items"][0]["note"] = ""
        self.assert_rejected(batch, "use null when there is no value")

    def test_item_with_only_a_cross_reference_is_valid(self):
        """A wordFormation item can carry its whole meaning in the target."""
        batch = canonical()
        first_sense(batch)["additional"]["items"].append({
            "id": "add_responsible_wordformation_01", "kind": "wordFormation", "salience": 2,
            "text": None, "note": None,
            "target": {"entryId": "entry_responsibility", "senseId": None},
            "attributes": {"relationType": "derivation", "targetPos": "noun"},
        })
        self.assert_valid(batch)

    def test_item_with_no_text_note_or_target_is_rejected(self):
        batch = canonical()
        item = first_sense(batch)["additional"]["items"][0]
        item["text"], item["note"], item["target"] = None, None, None
        self.assert_rejected(batch, "at least one of text, note or target")

    def test_examples_must_be_one_meaning_and_one_usage(self):
        batch = canonical()
        first_sense(batch)["examples"][1]["type"] = "meaning"
        self.assert_rejected(batch, "one 'meaning' and one 'usage'")

    def test_forbidden_tts_voice_field_is_rejected(self):
        for placement in ("root", "entry", "sense"):
            batch = canonical()
            if placement == "root":
                batch["voice"] = "en-US-AriaNeural"
            elif placement == "entry":
                batch["entries"][0]["ttsVoice"] = "en-US-AriaNeural"
            else:
                first_sense(batch)["audioPath"] = "audio/lex/evil.ogg"
            with self.subTest(placement=placement):
                self.assert_batch_rejected(batch, "forbidden field")

    def test_forbidden_source_format_and_ffmpeg_fields_are_rejected(self):
        for field, value in (("sourceFormat", "riff-48khz-16bit-mono-pcm"),
                             ("ffmpegArgs", ["-af", "volume=100"]),
                             ("audioChecksum", "deadbeef"),
                             ("mastery", 9)):
            batch = canonical()
            batch[field] = value
            with self.subTest(field=field):
                self.assert_batch_rejected(batch, "forbidden field")

    def test_pronunciations_are_semantic_and_never_treated_as_infrastructure(self):
        self.assert_valid(canonical())
        report = external_schema.validate_batch(canonical())
        self.assertFalse(any("pronunciations" in error for error in report.all_errors()))

    def test_grammatical_voice_inside_attributes_is_allowed(self):
        batch = canonical()
        first_sense(batch)["additional"]["items"][0]["attributes"] = {"patternType": "valency", "voice": "passive"}
        self.assert_valid(batch)

    def test_invalid_destination_is_rejected(self):
        for mutate, needle in (
            (lambda d: d.pop("blockPath"), "blockPath"),
            (lambda d: d.update(blockPath=[]), "blockPath"),
            (lambda d: d.update(createIfMissing="yes"), "createIfMissing"),
            (lambda d: d.update(extra=1), "unknown field"),
        ):
            batch = canonical()
            mutate(batch["destination"])
            with self.subTest(needle=needle):
                self.assert_batch_rejected(batch, needle)


class ExternalImportTests(unittest.TestCase):
    """End-to-end behaviour against a temporary database and app-data directory."""

    def setUp(self):
        self.sandbox = Sandbox()
        self.addCleanup(self.sandbox.close)

    def target_block(self) -> str:
        return self.sandbox.connection.execute(
            "SELECT id FROM blocks WHERE name='Vocabulary' AND parent_id IS NOT NULL").fetchone()["id"]

    def test_a_file_saved_with_a_byte_order_mark_still_imports(self):
        """Notepad and PowerShell write a BOM; an LLM-authored file often has one."""
        path = self.sandbox.root / "bom.json"
        path.write_text(json.dumps(canonical(), ensure_ascii=False), encoding="utf-8-sig")
        self.assertTrue(path.read_bytes().startswith(codecs.BOM_UTF8))
        summary = importer.run_import(path, self.sandbox.connection, Collector(), skip_audio=True)
        self.assertEqual(summary["imported"], 3)
        self.assertEqual(summary["failed"], [])

    def test_a_malformed_file_is_reported_not_raised_as_a_traceback(self):
        path = self.sandbox.root / "broken.json"
        path.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(importer.ImportError_) as caught:
            importer.run_import(path, self.sandbox.connection, Collector(), skip_audio=True)
        self.assertIn("is not valid UTF-8 JSON", str(caught.exception))
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_entries"), 0)

    def test_import_into_a_new_block_creates_the_hierarchy_once_and_produces_cards(self):
        summary, collector = self.sandbox.run(canonical())
        self.assertEqual(summary["failed"], [])
        self.assertEqual(summary["imported"], 3)
        self.assertEqual(summary["destination"], "Import Test/Vocabulary")
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM blocks WHERE name='Import Test'"), 1)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM blocks WHERE name='Vocabulary'"), 1)
        block = self.target_block()
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM block_entries WHERE block_id=?", block), 4)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_senses"), 4)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_examples"), 8)
        self.assertIn("validated", collector.stages())
        self.assertIn("summary", collector.stages())

        card = self.sandbox.connection.execute(
            "SELECT * FROM vocabulary_entries WHERE sense_id='sense_responsible_adjective_01'").fetchone()
        self.assertEqual(card["word"], "responsible")
        self.assertEqual(card["part_of_speech"], "adjective")
        self.assertEqual(card["ipa"], "/rɪˈspɑːnsəbəl/")
        self.assertEqual(card["vi_meaning"], "chịu trách nhiệm; có trách nhiệm")
        self.assertTrue(card["example_meaning_en"] and card["example_meaning_vi"])
        self.assertTrue(card["example_usage_en"] and card["example_usage_vi"])
        self.assertEqual(json.loads(card["accepted_answers"]), ["responsible"])
        additional = json.loads(card["extra_metadata"])
        self.assertEqual(additional["schemaVersion"], 1)
        self.assertEqual([item["kind"] for item in additional["items"]], ["pattern", "collocation", "relation"])

    def test_heteronyms_become_distinct_cards_with_distinct_audio_identity(self):
        self.sandbox.run(canonical())
        rows = self.sandbox.connection.execute(
            "SELECT part_of_speech,ipa,sense_id FROM vocabulary_entries WHERE word='record' ORDER BY part_of_speech").fetchall()
        self.assertEqual([row["part_of_speech"] for row in rows], ["noun", "verb"])
        self.assertNotEqual(rows[0]["ipa"], rows[1]["ipa"])
        senses = self.sandbox.connection.execute(
            "SELECT pronunciation_id FROM lexical_senses WHERE entry_id='entry_record' ORDER BY sort_order").fetchall()
        self.assertNotEqual(senses[0]["pronunciation_id"], senses[1]["pronunciation_id"])

    def test_destination_rules(self):
        batch = canonical()
        batch["destination"]["createIfMissing"] = False
        with self.assertRaises(importer.ImportError_) as caught:
            self.sandbox.run(batch)
        self.assertIn("createIfMissing is false", str(caught.exception))

        self.sandbox.run(canonical())
        by_id = canonical()
        by_id["destination"] = {"blockId": self.target_block(), "blockPath": ["ignored"], "createIfMissing": False}
        summary, _ = self.sandbox.run(by_id, name="by_id.json")
        self.assertEqual(summary["blockId"], self.target_block())

        missing = canonical()
        missing["destination"] = {"blockId": "not-a-block", "blockPath": ["x"], "createIfMissing": True}
        with self.assertRaises(importer.ImportError_) as caught:
            self.sandbox.run(missing, name="missing.json")
        self.assertIn("does not exist", str(caught.exception))

    def test_ambiguous_block_path_fails_rather_than_guessing(self):
        timestamp = db.now()
        for index in range(2):
            self.sandbox.connection.execute(
                "INSERT INTO blocks(id,parent_id,name,icon_key,sort_order,created_at,updated_at) VALUES(?,NULL,'Import Test','book-open',?,?,?)",
                (f"dup-{index}", index, timestamp, timestamp))
        self.sandbox.connection.commit()
        with self.assertRaises(importer.ImportError_) as caught:
            self.sandbox.run(canonical())
        self.assertIn("ambiguous", str(caught.exception))

    def test_reimport_is_idempotent_and_preserves_mastery(self):
        self.sandbox.run(canonical())
        block = self.target_block()
        self.sandbox.connection.execute(
            "UPDATE block_entries SET mastery_score=7,total_reviews=5,again_count=1 WHERE block_id=?", (block,))
        self.sandbox.connection.commit()
        before = {table: self.sandbox.count(f"SELECT COUNT(*) FROM {table}") for table in
                  ("blocks", "block_entries", "vocabulary_entries", "lexical_entries", "lexical_senses",
                   "lexical_examples", "lexical_example_translations", "lexical_additional_items")}

        summary, _ = self.sandbox.run(canonical())
        after = {table: self.sandbox.count(f"SELECT COUNT(*) FROM {table}") for table in before}
        self.assertEqual(before, after)
        self.assertEqual(summary["imported"], 0)
        self.assertEqual(summary["alreadyCurrent"], 3)
        mastery = self.sandbox.connection.execute(
            "SELECT mastery_score,total_reviews,again_count FROM block_entries WHERE block_id=? LIMIT 1", (block,)).fetchone()
        self.assertEqual(tuple(mastery), (7, 5, 1))

    def test_semantic_update_rewrites_content_without_touching_learner_state(self):
        self.sandbox.run(canonical())
        block = self.target_block()
        self.sandbox.connection.execute("UPDATE block_entries SET mastery_score=4 WHERE block_id=?", (block,))
        self.sandbox.connection.commit()

        updated = canonical()
        first_sense(updated)["definition"] = "having a duty to take care of someone or something"
        first_sense(updated)["additional"]["items"][0]["note"] = "Very common with 'for'."
        summary, _ = self.sandbox.run(updated, name="updated.json")
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["failed"], [])
        card = self.sandbox.connection.execute(
            "SELECT en_definition,extra_metadata FROM vocabulary_entries WHERE sense_id='sense_responsible_adjective_01'").fetchone()
        self.assertEqual(card["en_definition"], "having a duty to take care of someone or something")
        self.assertEqual(json.loads(card["extra_metadata"])["items"][0]["note"], "Very common with 'for'.")
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_additional_items WHERE sense_id='sense_responsible_adjective_01'"), 3)
        self.assertEqual(self.sandbox.count("SELECT mastery_score FROM block_entries WHERE block_id=? LIMIT 1", block), 4)

    def test_block_membership_is_additive_and_never_removes_an_older_block(self):
        self.sandbox.run(canonical())
        card = self.sandbox.connection.execute(
            "SELECT id FROM vocabulary_entries WHERE sense_id='sense_responsible_adjective_01'").fetchone()["id"]
        timestamp = db.now()
        self.sandbox.connection.execute(
            "INSERT INTO blocks(id,parent_id,name,icon_key,sort_order,created_at,updated_at) VALUES('other',NULL,'Other','book-open',9,?,?)",
            (timestamp, timestamp))
        self.sandbox.connection.execute(
            "INSERT INTO block_entries(id,block_id,entry_id,mastery_score,created_at,updated_at) VALUES('m2','other',?,3,?,?)",
            (card, timestamp, timestamp))
        self.sandbox.connection.commit()
        self.sandbox.run(canonical())
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM block_entries WHERE entry_id=?", card), 2)
        self.assertEqual(self.sandbox.count("SELECT mastery_score FROM block_entries WHERE id='m2'"), 3)

    def test_identity_conflicts_fail_the_entry_and_leave_the_rest_importable(self):
        self.sandbox.run(canonical())
        clashing = canonical()
        clashing["entries"] = [copy.deepcopy(clashing["entries"][0])]
        clashing["entries"][0]["lemma"] = "irresponsible"
        clashing["batchId"] = "fixture_conflict_v1"
        summary, _ = self.sandbox.run(clashing, name="conflict.json")
        self.assertEqual(len(summary["failed"]), 1)
        self.assertIn("already exists with lemma", summary["failed"][0]["reason"])
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM vocabulary_entries WHERE sense_id IS NOT NULL"), 4)

    def test_one_invalid_entry_fails_alone_and_the_rest_import(self):
        """A content error in one entry must not cost the user the other entries."""
        batch = canonical()
        batch["entries"][1]["senses"][0]["definition"] = ""  # only entry 2 is unusable
        report = external_schema.validate_batch(batch)
        self.assertEqual(report.errors, [], "an entry-level content error is not batch-fatal")
        self.assertIn(1, report.entry_errors)

        summary, collector = self.sandbox.run(batch, name="one_bad.json")
        self.assertEqual(summary["imported"], 2)
        self.assertEqual([failure["entryId"] for failure in summary["failed"]], ["entry_record"])
        self.assertIn("definition", summary["failed"][0]["reason"])
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_entries"), 2)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM vocabulary_entries WHERE sense_id IS NOT NULL"), 2)
        self.assertIn("failed", collector.stages())

        fixed = canonical()
        summary, _ = self.sandbox.run(fixed, name="fixed.json")
        self.assertEqual(summary["failed"], [])
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM vocabulary_entries WHERE sense_id IS NOT NULL"), 4)

    def test_failed_entry_is_recorded_and_resumes_on_the_next_run(self):
        batch = canonical()
        batch["entries"] = [copy.deepcopy(batch["entries"][0])]
        self.sandbox.connection.execute(
            "INSERT INTO lexical_entries(id,lemma,created_at,updated_at) VALUES('entry_responsible','different',?,?)",
            (db.now(), db.now()))
        self.sandbox.connection.commit()
        summary, _ = self.sandbox.run(batch)
        self.assertEqual(len(summary["failed"]), 1)
        item = self.sandbox.connection.execute(
            "SELECT status,attempt_count,last_error FROM lexical_import_items WHERE entry_id='entry_responsible'").fetchone()
        self.assertEqual(item["status"], "FAILED")
        self.assertEqual(item["attempt_count"], 1)
        self.assertIn("lemma", item["last_error"])

        self.sandbox.connection.execute("UPDATE lexical_entries SET lemma='responsible' WHERE id='entry_responsible'")
        self.sandbox.connection.commit()
        summary, _ = self.sandbox.run(batch)
        self.assertEqual(summary["failed"], [])
        self.assertEqual(self.sandbox.connection.execute(
            "SELECT status FROM lexical_import_items WHERE entry_id='entry_responsible'").fetchone()["status"], "IMPORTED")

    def test_progress_events_are_machine_readable(self):
        _, collector = self.sandbox.run(canonical())
        validated = next(event for event in collector.events if event["stage"] == "validated")
        self.assertEqual(validated["total"], 3)
        self.assertEqual(validated["batchId"], "fixture_canonical_v1")
        imported = [event for event in collector.events if event["stage"] == "imported"]
        self.assertEqual([event["current"] for event in imported], [1, 2, 3])
        summary = next(event for event in collector.events if event["stage"] == "summary")
        for key in ("requested", "imported", "updated", "alreadyCurrent", "audioGenerated", "audioReused", "failed"):
            self.assertIn(key, summary)

    def test_forbidden_voice_is_rejected_before_any_database_or_network_work(self):
        batch = canonical()
        batch["voice"] = "en-US-AriaNeural"
        with self.assertRaises(importer.ImportError_) as caught:
            self.sandbox.run(batch, skip_audio=False)
        self.assertIn("forbidden field", str(caught.exception))
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_entries"), 0)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM lexical_audio_assets"), 0)
        self.assertEqual(self.sandbox.count("SELECT COUNT(*) FROM blocks WHERE name='Import Test'"), 0)


class ProductionAudioProfileTests(unittest.TestCase):
    """One source of truth, and the importer cannot be steered away from it."""

    def test_profile_reports_the_benchmarked_configuration(self):
        described = audio_profile.describe()
        self.assertEqual(described["voice"], "en-US-JennyNeural")
        self.assertEqual(described["sourceFormat"], "audio-24khz-48kbitrate-mono-mp3")
        self.assertEqual(described["finalCodec"], "opus")
        self.assertEqual(described["finalContainer"], "ogg")
        self.assertEqual(described["finalTargetBps"], 64000)
        self.assertEqual(described["finalChannels"], 1)

    def test_fingerprint_is_deterministic_and_covers_voice_format_and_encoder(self):
        self.assertEqual(audio_profile.fingerprint(), audio_profile.FINGERPRINT)
        for token in ("edge-readaloud", "en-US-JennyNeural", "audio-24khz-48kbitrate-mono-mp3",
                      "rate=-5%", "opus-64k-mono-vbr", "encoder-profile="):
            self.assertIn(token, audio_profile.FINGERPRINT)

    def test_changing_the_ffmpeg_chain_changes_the_fingerprint(self):
        from tools.ingest import audio_encode

        original = audio_encode.FILTER_CHAIN
        try:
            audio_encode.FILTER_CHAIN = original + ",volume=2"
            self.assertNotEqual(audio_profile.fingerprint(), audio_profile.FINGERPRINT)
        finally:
            audio_encode.FILTER_CHAIN = original
        self.assertEqual(audio_profile.fingerprint(), audio_profile.FINGERPRINT)

    def test_stale_fingerprint_invalidates_stored_audio(self):
        sandbox = Sandbox()
        try:
            sandbox.run(canonical())
            sandbox.connection.execute(
                "INSERT INTO lexical_audio_assets(pronunciation_id,entry_id,form_id,locale,synthesis_text,fingerprint,app_path,sha256,status,created_at,updated_at) "
                "VALUES('pron_responsible_en_us_01','entry_responsible','form_responsible_01','en-US','responsible','old-profile','audio/lex/x.ogg','abc','current',?,?) "
                "ON CONFLICT(pronunciation_id) DO UPDATE SET fingerprint='old-profile'",
                (db.now(), db.now()))
            sandbox.connection.commit()
            self.assertIsNone(importer.audio_is_current(sandbox.connection, "pron_responsible_en_us_01", "responsible"))
        finally:
            sandbox.close()

    def test_synthesis_text_comes_from_the_lexical_form_only(self):
        self.assertEqual(importer.synthesis_text_for({"written": "gradient descent"}), "gradient descent")
        self.assertEqual(importer.synthesis_text_for({"written": "a, an"}), "a. an")

    def test_identifiers_cannot_escape_the_audio_directory(self):
        for hostile in ("../../etc/passwd", "a/b", "a\\b", "a b"):
            with self.subTest(hostile=hostile):
                with self.assertRaises(importer.ImportError_):
                    importer.safe_stem(hostile)
        self.assertEqual(importer.safe_stem("external:batch:entry"), "external_batch_entry")


class LiveSpeechTests(unittest.TestCase):
    """Network-gated proof that a real import produces real Jenny audio."""

    def test_valid_import_synthesises_with_the_locked_voice_and_source_format(self):
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            self.skipTest("edge-tts is not installed")
        sandbox = Sandbox()
        try:
            batch = canonical()
            batch["entries"] = [copy.deepcopy(batch["entries"][0])]
            try:
                summary, _ = sandbox.run(batch, skip_audio=False)
            except Exception as error:  # noqa: BLE001 - offline runs must not fail the suite
                self.skipTest(f"Microsoft Edge speech is unreachable: {error}")
            self.assertEqual(summary["failed"], [])
            self.assertEqual(summary["audioGenerated"], 1)

            asset = sandbox.connection.execute(
                "SELECT * FROM lexical_audio_assets WHERE pronunciation_id='pron_responsible_en_us_01'").fetchone()
            self.assertEqual(asset["fingerprint"], audio_profile.FINGERPRINT)
            self.assertEqual(asset["status"], "current")
            self.assertGreater(asset["duration_seconds"], 0.2)

            master = next((sandbox.root / "master").glob("*.mp3"))
            probe = __import__("subprocess").run(
                [__import__("tools.ingest.audio_encode", fromlist=["find_binary"]).find_binary("ffprobe"),
                 "-v", "error", "-show_entries", "stream=codec_name,sample_rate,channels",
                 "-show_entries", "format=bit_rate", "-of", "default=nw=1", str(master)],
                check=True, capture_output=True, text=True).stdout
            self.assertIn("codec_name=mp3", probe)
            self.assertIn("sample_rate=24000", probe)
            self.assertIn("channels=1", probe)
            self.assertIn("bit_rate=48000", probe)

            card = sandbox.connection.execute(
                "SELECT audio_voice,audio_path FROM vocabulary_entries WHERE sense_id='sense_responsible_adjective_01'").fetchone()
            self.assertEqual(card["audio_voice"], "en-US-JennyNeural")
            self.assertTrue(card["audio_path"].startswith("audio/lex/"))
            self.assertTrue((db.default_app_data() / card["audio_path"]).exists())

            summary, _ = sandbox.run(batch, skip_audio=False, name="again.json")
            self.assertEqual(summary["audioGenerated"], 0)
            self.assertEqual(summary["audioReused"], 1)
        finally:
            sandbox.close()


if __name__ == "__main__":
    unittest.main()
