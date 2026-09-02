ALTER TABLE blocks ADD COLUMN source_key TEXT;
CREATE UNIQUE INDEX idx_blocks_source_key ON blocks(source_key) WHERE source_key IS NOT NULL;

ALTER TABLE vocabulary_entries ADD COLUMN source_key TEXT;
ALTER TABLE vocabulary_entries ADD COLUMN source_name TEXT;
ALTER TABLE vocabulary_entries ADD COLUMN source_level TEXT;
ALTER TABLE vocabulary_entries ADD COLUMN source_index INTEGER;
ALTER TABLE vocabulary_entries ADD COLUMN cefr TEXT;
ALTER TABLE vocabulary_entries ADD COLUMN audio_path TEXT;
ALTER TABLE vocabulary_entries ADD COLUMN audio_voice TEXT;
ALTER TABLE vocabulary_entries ADD COLUMN audio_checksum TEXT;
CREATE UNIQUE INDEX idx_vocabulary_source_key ON vocabulary_entries(source_key) WHERE source_key IS NOT NULL;
CREATE INDEX idx_vocabulary_source_position ON vocabulary_entries(source_name, source_level, source_index);

CREATE TABLE source_manifests (
  id TEXT PRIMARY KEY NOT NULL,
  source_name TEXT NOT NULL,
  source_level TEXT NOT NULL,
  version TEXT NOT NULL,
  source_url TEXT NOT NULL,
  manifest_path TEXT NOT NULL,
  manifest_checksum TEXT NOT NULL,
  item_count INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(source_name, source_level, version)
);

CREATE TABLE ingestion_jobs (
  id TEXT PRIMARY KEY NOT NULL,
  manifest_id TEXT NOT NULL REFERENCES source_manifests(id),
  target_block_id TEXT NOT NULL REFERENCES blocks(id),
  batch_id TEXT NOT NULL UNIQUE,
  target_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE ingestion_items (
  source_key TEXT PRIMARY KEY NOT NULL,
  job_id TEXT NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
  source_index INTEGER NOT NULL,
  word TEXT NOT NULL,
  part_of_speech TEXT NOT NULL,
  cefr TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('DISCOVERED','GENERATED','REVIEWED','REPAIR_NEEDED','VALIDATED','AUDIO_REQUESTED','AUDIO_DONE','ENCODED','IMPORTED','FAILED')),
  stage TEXT NOT NULL DEFAULT 'discovery',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  batch_id TEXT NOT NULL,
  generator_model TEXT,
  critic_model TEXT,
  generator_version TEXT,
  critic_version TEXT,
  card_json TEXT,
  critic_json TEXT,
  validation_json TEXT,
  audio_voice TEXT,
  audio_master_path TEXT,
  audio_path TEXT,
  audio_checksum TEXT,
  audio_verified INTEGER NOT NULL DEFAULT 0,
  final_json_checksum TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(job_id, source_index)
);
CREATE INDEX idx_ingestion_items_job_status ON ingestion_items(job_id, status, source_index);

CREATE TABLE ingestion_failures (
  id TEXT PRIMARY KEY NOT NULL,
  source_key TEXT NOT NULL REFERENCES ingestion_items(source_key) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  error_code TEXT NOT NULL,
  error_message TEXT NOT NULL,
  attempts INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_ingestion_failures_source ON ingestion_failures(source_key, created_at);
