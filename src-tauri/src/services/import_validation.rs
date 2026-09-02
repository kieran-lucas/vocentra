use crate::{
    error::{AppError, AppResult},
    models::{ImportBatch, ImportPreview, ImportResult},
};
use chrono::Utc;
use sqlx::SqlitePool;
use uuid::Uuid;

pub fn parse(json: &str) -> AppResult<ImportBatch> {
    serde_json::from_str(json).map_err(|e| AppError::Validation(format!("Invalid JSON: {e}")))
}
pub fn validate(batch: &ImportBatch) -> Vec<String> {
    let mut errors = Vec::new();
    for (i, e) in batch.entries.iter().enumerate() {
        let required = [
            ("word", &e.word),
            ("ipa", &e.ipa),
            ("partOfSpeech", &e.part_of_speech),
            ("viMeaning", &e.vi_meaning),
            ("enDefinition", &e.en_definition),
            ("exampleMeaning.en", &e.example_meaning.en),
            ("exampleMeaning.vi", &e.example_meaning.vi),
            ("exampleUsage.en", &e.example_usage.en),
            ("exampleUsage.vi", &e.example_usage.vi),
        ];
        for (field, value) in required {
            if value.trim().is_empty() {
                errors.push(format!("Entry {}: {} is required", i + 1, field));
            }
        }
    }
    errors
}
pub fn preview(json: &str) -> AppResult<ImportPreview> {
    let batch = parse(json)?;
    let errors = validate(&batch);
    Ok(ImportPreview {
        valid_count: if errors.is_empty() {
            batch.entries.len()
        } else {
            0
        },
        errors,
    })
}
pub async fn import(pool: &SqlitePool, block_id: &str, json: &str) -> AppResult<ImportResult> {
    let batch = parse(json)?;
    let errors = validate(&batch);
    if !errors.is_empty() {
        return Err(AppError::Validation(errors.join("; ")));
    }
    let child_count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM blocks WHERE parent_id=?")
        .bind(block_id)
        .fetch_one(pool)
        .await?;
    if child_count > 0 {
        return Err(AppError::Validation(
            "Vocabulary can only be imported into a leaf block".into(),
        ));
    }
    let mut tx = pool.begin().await?;
    let now = Utc::now().to_rfc3339();
    for e in &batch.entries {
        let id = Uuid::new_v4().to_string();
        sqlx::query(r#"INSERT INTO vocabulary_entries(id,word,ipa,part_of_speech,vi_meaning,en_definition,example_meaning_en,example_meaning_vi,example_usage_en,example_usage_vi,collocations,usage_note,register,word_family,synonyms,antonyms,accepted_answers,extra_metadata,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"#).bind(&id).bind(e.word.trim()).bind(e.ipa.trim()).bind(e.part_of_speech.trim()).bind(e.vi_meaning.trim()).bind(e.en_definition.trim()).bind(e.example_meaning.en.trim()).bind(e.example_meaning.vi.trim()).bind(e.example_usage.en.trim()).bind(e.example_usage.vi.trim()).bind(serde_json::to_string(&e.extras.collocations).unwrap_or_default()).bind(e.example_usage.note.as_deref()).bind(e.extras.register.as_deref()).bind(serde_json::to_string(&e.extras.word_family).unwrap_or_default()).bind(serde_json::to_string(&e.extras.synonyms).unwrap_or_default()).bind(serde_json::to_string(&e.extras.antonyms).unwrap_or_default()).bind(serde_json::to_string(&e.accepted_answers).unwrap_or_default()).bind("{}").bind(&now).bind(&now).execute(&mut *tx).await?;
        sqlx::query("INSERT INTO block_entries(id,block_id,entry_id,created_at,updated_at) VALUES(?,?,?,?,?)").bind(Uuid::new_v4().to_string()).bind(block_id).bind(id).bind(&now).bind(&now).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(ImportResult {
        imported_count: batch.entries.len(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn batch_import_is_atomic_and_mastery_isolated() {
        let p = crate::db::memory().await.unwrap();
        let now = Utc::now().to_rfc3339();
        for id in ["a", "b"] {
            sqlx::query("INSERT INTO blocks(id,name,icon_key,created_at,updated_at)VALUES(?,?, 'book-open',?,?)").bind(id).bind(id).bind(&now).bind(&now).execute(&p).await.unwrap();
        }
        let json = r#"{"entries":[{"word":"commit","ipa":"/kəˈmɪt/","partOfSpeech":"verb","viMeaning":"cam kết","enDefinition":"to promise firmly","exampleMeaning":{"en":"We commit to it.","vi":"Chúng tôi cam kết."},"exampleUsage":{"en":"Commit funds to research.","vi":"Dành quỹ cho nghiên cứu."}}]}"#;
        import(&p, "a", json).await.unwrap();
        let entry: String =
            sqlx::query_scalar("SELECT entry_id FROM block_entries WHERE block_id='a'")
                .fetch_one(&p)
                .await
                .unwrap();
        sqlx::query("INSERT INTO block_entries(id,block_id,entry_id,mastery_score,created_at,updated_at)VALUES('other','b',?,9,?,?)").bind(entry).bind(&now).bind(&now).execute(&p).await.unwrap();
        sqlx::query("UPDATE block_entries SET mastery_score=2 WHERE block_id='a'")
            .execute(&p)
            .await
            .unwrap();
        let scores: Vec<i64> = sqlx::query_scalar(
            "SELECT mastery_score FROM block_entries WHERE block_id IN ('a','b') ORDER BY block_id",
        )
        .fetch_all(&p)
        .await
        .unwrap();
        assert_eq!(scores, vec![2, 9]);
        assert!(import(&p, "b", "{bad").await.is_err());
        let count: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM block_entries WHERE block_id='b'")
                .fetch_one(&p)
                .await
                .unwrap();
        assert_eq!(count, 1);
    }
}
