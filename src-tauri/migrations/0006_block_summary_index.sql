-- Cover library counts and mastery totals without fetching each membership row.
-- The leading column also serves existing block membership lookups.
CREATE INDEX idx_block_entries_summary ON block_entries(block_id, mastery_score);
DROP INDEX idx_block_entries_block;
