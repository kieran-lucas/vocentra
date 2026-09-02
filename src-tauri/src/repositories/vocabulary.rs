use crate::{
    error::AppResult,
    models::{ManagedEntry, StudyItem, VocabularyEntry},
};
use sqlx::SqlitePool;

pub async fn list(pool: &SqlitePool, block_id: &str, search: &str) -> AppResult<Vec<ManagedEntry>> {
    let q = format!("%{}%", search.trim());
    Ok(sqlx::query_as::<_,ManagedEntry>(r#"SELECT v.id,v.word,v.ipa,v.part_of_speech,v.vi_meaning,v.en_definition,v.example_meaning_en,v.example_meaning_vi,v.example_usage_en,v.example_usage_vi,v.collocations,v.usage_note,v.register,v.word_family,v.synonyms,v.antonyms,v.accepted_answers,v.extra_metadata,v.source_key,v.source_name,v.source_level,v.source_index,v.cefr,v.audio_path,v.audio_voice,v.audio_checksum,be.id block_entry_id,be.mastery_score,be.total_reviews FROM block_entries be JOIN vocabulary_entries v ON v.id=be.entry_id WHERE be.block_id=? AND v.word LIKE ? ORDER BY v.word COLLATE NOCASE LIMIT 1000"#).bind(block_id).bind(q).fetch_all(pool).await?)
}
pub async fn study_items(pool: &SqlitePool, block_id: &str) -> AppResult<Vec<StudyItem>> {
    Ok(sqlx::query_as::<_,StudyItem>(r#"SELECT be.id block_entry_id,be.mastery_score,v.id,v.word,v.ipa,v.part_of_speech,v.vi_meaning,v.en_definition,v.example_meaning_en,v.example_meaning_vi,v.example_usage_en,v.example_usage_vi,v.collocations,v.usage_note,v.register,v.word_family,v.synonyms,v.antonyms,v.accepted_answers,v.extra_metadata,v.source_key,v.source_name,v.source_level,v.source_index,v.cefr,v.audio_path,v.audio_voice,v.audio_checksum FROM block_entries be JOIN vocabulary_entries v ON v.id=be.entry_id WHERE be.block_id=? ORDER BY v.source_index IS NULL,v.source_index,v.word COLLATE NOCASE"#).bind(block_id).fetch_all(pool).await?)
}
pub async fn remove(pool: &SqlitePool, block_entry_id: &str) -> AppResult<()> {
    sqlx::query("DELETE FROM block_entries WHERE id=?")
        .bind(block_entry_id)
        .execute(pool)
        .await?;
    Ok(())
}
pub async fn update(pool: &SqlitePool, v: &VocabularyEntry) -> AppResult<()> {
    sqlx::query("UPDATE vocabulary_entries SET word=?,ipa=?,part_of_speech=?,vi_meaning=?,en_definition=?,example_meaning_en=?,example_meaning_vi=?,example_usage_en=?,example_usage_vi=?,usage_note=?,updated_at=? WHERE id=?").bind(&v.word).bind(&v.ipa).bind(&v.part_of_speech).bind(&v.vi_meaning).bind(&v.en_definition).bind(&v.example_meaning_en).bind(&v.example_meaning_vi).bind(&v.example_usage_en).bind(&v.example_usage_vi).bind(&v.usage_note).bind(chrono::Utc::now().to_rfc3339()).bind(&v.id).execute(pool).await?;
    Ok(())
}
