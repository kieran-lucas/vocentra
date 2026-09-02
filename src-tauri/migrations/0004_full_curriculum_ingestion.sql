ALTER TABLE ingestion_items ADD COLUMN target_block_id TEXT REFERENCES blocks(id);
ALTER TABLE ingestion_items ADD COLUMN source_name TEXT;

UPDATE ingestion_items
SET target_block_id = (
  SELECT target_block_id FROM ingestion_jobs WHERE ingestion_jobs.id = ingestion_items.job_id
)
WHERE target_block_id IS NULL;

UPDATE ingestion_items SET source_name = 'oxford3000' WHERE source_name IS NULL;

CREATE INDEX idx_ingestion_items_target_block ON ingestion_items(target_block_id, source_index);
