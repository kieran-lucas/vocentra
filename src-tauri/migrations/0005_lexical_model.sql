-- Canonical lexical model: LexicalEntry -> Forms -> Pronunciations, and
-- LexicalEntry -> Senses -> Glosses / Examples / Additional.
-- vocabulary_entries stays as the card-engine read model; one sense projects to
-- one card row, so heteronyms become distinct cards and mastery is untouched.

CREATE TABLE lexical_entries (
  id TEXT PRIMARY KEY NOT NULL,
  lemma TEXT NOT NULL CHECK(length(trim(lemma)) > 0),
  entry_type TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_lexical_entries_lemma ON lexical_entries(lemma COLLATE NOCASE);

CREATE TABLE lexical_forms (
  id TEXT PRIMARY KEY NOT NULL,
  entry_id TEXT NOT NULL REFERENCES lexical_entries(id) ON DELETE CASCADE,
  written TEXT NOT NULL CHECK(length(trim(written)) > 0),
  morphology TEXT NOT NULL DEFAULT '{}',
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_lexical_forms_entry ON lexical_forms(entry_id, sort_order);

CREATE TABLE lexical_pronunciations (
  id TEXT PRIMARY KEY NOT NULL,
  form_id TEXT NOT NULL REFERENCES lexical_forms(id) ON DELETE CASCADE,
  locale TEXT NOT NULL,
  ipa TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_lexical_pronunciations_form ON lexical_pronunciations(form_id, locale, sort_order);

CREATE TABLE lexical_senses (
  id TEXT PRIMARY KEY NOT NULL,
  entry_id TEXT NOT NULL REFERENCES lexical_entries(id) ON DELETE CASCADE,
  pronunciation_id TEXT REFERENCES lexical_pronunciations(id) ON DELETE SET NULL,
  pos TEXT NOT NULL,
  definition TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_lexical_senses_entry ON lexical_senses(entry_id, sort_order);

CREATE TABLE lexical_glosses (
  id TEXT PRIMARY KEY NOT NULL,
  sense_id TEXT NOT NULL REFERENCES lexical_senses(id) ON DELETE CASCADE,
  locale TEXT NOT NULL,
  text TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE(sense_id, locale, sort_order)
);

CREATE TABLE lexical_examples (
  id TEXT PRIMARY KEY NOT NULL,
  sense_id TEXT NOT NULL REFERENCES lexical_senses(id) ON DELETE CASCADE,
  example_type TEXT NOT NULL CHECK(example_type IN ('meaning','usage')),
  en TEXT NOT NULL,
  note TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_lexical_examples_sense ON lexical_examples(sense_id, sort_order);

CREATE TABLE lexical_example_translations (
  id TEXT PRIMARY KEY NOT NULL,
  example_id TEXT NOT NULL REFERENCES lexical_examples(id) ON DELETE CASCADE,
  locale TEXT NOT NULL,
  text TEXT NOT NULL,
  UNIQUE(example_id, locale)
);

CREATE TABLE lexical_additional_items (
  id TEXT PRIMARY KEY NOT NULL,
  sense_id TEXT NOT NULL REFERENCES lexical_senses(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  salience INTEGER NOT NULL CHECK(salience BETWEEN 1 AND 3),
  text TEXT,
  note TEXT,
  target_entry_id TEXT,
  target_sense_id TEXT,
  attributes TEXT NOT NULL DEFAULT '{}',
  unresolved INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_lexical_additional_sense ON lexical_additional_items(sense_id, sort_order);
CREATE INDEX idx_lexical_additional_target ON lexical_additional_items(target_entry_id) WHERE target_entry_id IS NOT NULL;

-- Audio identity is (entry, form, pronunciation, locale), never the spelling, so
-- two pronunciations of one written form never share a clip.
CREATE TABLE lexical_audio_assets (
  pronunciation_id TEXT PRIMARY KEY NOT NULL REFERENCES lexical_pronunciations(id) ON DELETE CASCADE,
  entry_id TEXT NOT NULL,
  form_id TEXT NOT NULL,
  locale TEXT NOT NULL,
  synthesis_text TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  master_path TEXT,
  app_path TEXT,
  sha256 TEXT,
  duration_seconds REAL,
  status TEXT NOT NULL CHECK(status IN ('current','needs_review','stale','failed')),
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_lexical_audio_status ON lexical_audio_assets(status, fingerprint);

CREATE TABLE lexical_import_batches (
  batch_id TEXT PRIMARY KEY NOT NULL,
  schema_version INTEGER NOT NULL,
  source_sha256 TEXT NOT NULL,
  destination_block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
  destination_path TEXT NOT NULL,
  entry_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE lexical_import_items (
  source_key TEXT PRIMARY KEY NOT NULL,
  batch_id TEXT NOT NULL REFERENCES lexical_import_batches(batch_id) ON DELETE CASCADE,
  entry_id TEXT NOT NULL,
  entry_index INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('DISCOVERED','VALIDATED','AUDIO_REQUESTED','AUDIO_DONE','ENCODED','IMPORTED','FAILED')),
  stage TEXT NOT NULL DEFAULT 'discovery',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  payload_sha256 TEXT NOT NULL,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_lexical_import_items_batch ON lexical_import_items(batch_id, status, entry_index);

-- Back-link from the projected card row to the sense that owns it.
ALTER TABLE vocabulary_entries ADD COLUMN sense_id TEXT REFERENCES lexical_senses(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX idx_vocabulary_sense ON vocabulary_entries(sense_id) WHERE sense_id IS NOT NULL;
