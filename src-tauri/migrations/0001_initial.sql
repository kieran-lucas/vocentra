PRAGMA foreign_keys = ON;

CREATE TABLE blocks (
  id TEXT PRIMARY KEY NOT NULL,
  parent_id TEXT REFERENCES blocks(id) ON DELETE CASCADE,
  name TEXT NOT NULL CHECK(length(trim(name)) > 0),
  icon_key TEXT NOT NULL DEFAULT 'book-open',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_blocks_parent_sort ON blocks(parent_id, sort_order, name);

CREATE TABLE vocabulary_entries (
  id TEXT PRIMARY KEY NOT NULL,
  word TEXT NOT NULL,
  ipa TEXT NOT NULL,
  part_of_speech TEXT NOT NULL,
  vi_meaning TEXT NOT NULL,
  en_definition TEXT NOT NULL,
  example_meaning_en TEXT NOT NULL,
  example_meaning_vi TEXT NOT NULL,
  example_usage_en TEXT NOT NULL,
  example_usage_vi TEXT NOT NULL,
  collocations TEXT NOT NULL DEFAULT '[]',
  usage_note TEXT,
  register TEXT,
  word_family TEXT NOT NULL DEFAULT '[]',
  synonyms TEXT NOT NULL DEFAULT '[]',
  antonyms TEXT NOT NULL DEFAULT '[]',
  accepted_answers TEXT NOT NULL DEFAULT '[]',
  extra_metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_vocab_word ON vocabulary_entries(word COLLATE NOCASE);

CREATE TABLE block_entries (
  id TEXT PRIMARY KEY NOT NULL,
  block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
  entry_id TEXT NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
  mastery_score INTEGER NOT NULL DEFAULT 0,
  last_rating TEXT,
  total_reviews INTEGER NOT NULL DEFAULT 0,
  again_count INTEGER NOT NULL DEFAULT 0,
  hard_count INTEGER NOT NULL DEFAULT 0,
  good_count INTEGER NOT NULL DEFAULT 0,
  easy_count INTEGER NOT NULL DEFAULT 0,
  typing_correct_count INTEGER NOT NULL DEFAULT 0,
  typing_error_count INTEGER NOT NULL DEFAULT 0,
  last_reviewed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(block_id, entry_id)
);
CREATE INDEX idx_block_entries_block ON block_entries(block_id);

CREATE TABLE study_turns (
  id TEXT PRIMARY KEY NOT NULL,
  block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  target_unique_count INTEGER NOT NULL,
  total_shown INTEGER NOT NULL DEFAULT 0,
  completed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE study_events (
  id TEXT PRIMARY KEY NOT NULL,
  turn_id TEXT NOT NULL REFERENCES study_turns(id) ON DELETE CASCADE,
  block_entry_id TEXT NOT NULL REFERENCES block_entries(id) ON DELETE CASCADE,
  sequence_index INTEGER NOT NULL,
  rating TEXT NOT NULL,
  mastery_before INTEGER NOT NULL,
  mastery_after INTEGER NOT NULL,
  typing_correct_count INTEGER NOT NULL DEFAULT 0,
  typing_error_count INTEGER NOT NULL DEFAULT 0,
  shown_at TEXT NOT NULL,
  rated_at TEXT NOT NULL
);
CREATE INDEX idx_study_events_turn ON study_events(turn_id, sequence_index);
