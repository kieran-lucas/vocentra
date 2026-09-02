use crate::error::AppResult;
use sqlx::{
    SqlitePool,
    sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous},
};
use std::path::Path;

pub async fn connect(path: &Path) -> AppResult<SqlitePool> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| crate::error::AppError::Internal(e.to_string()))?;
    }
    let options = SqliteConnectOptions::new()
        .filename(path)
        .create_if_missing(true)
        .foreign_keys(true)
        .journal_mode(SqliteJournalMode::Wal)
        .synchronous(SqliteSynchronous::Normal)
        .busy_timeout(std::time::Duration::from_secs(5));
    let pool = SqlitePoolOptions::new()
        .max_connections(4)
        .connect_with(options)
        .await?;
    sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .map_err(|e| crate::error::AppError::Internal(e.to_string()))?;
    Ok(pool)
}

#[cfg(test)]
pub async fn memory() -> AppResult<SqlitePool> {
    let pool = SqlitePoolOptions::new()
        .max_connections(1)
        .connect("sqlite::memory:")
        .await?;
    sqlx::query("PRAGMA foreign_keys = ON")
        .execute(&pool)
        .await?;
    sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .map_err(|e| crate::error::AppError::Internal(e.to_string()))?;
    Ok(pool)
}

#[cfg(test)]
mod tests {
    #[tokio::test]
    async fn migrations_create_schema() {
        let pool = super::memory().await.unwrap();
        let count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('study_events','ingestion_items')",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(count, 2);
    }

    #[tokio::test]
    async fn migrations_create_the_lexical_model_and_card_backlink() {
        let pool = super::memory().await.unwrap();
        let tables: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN              ('lexical_entries','lexical_forms','lexical_pronunciations','lexical_senses',              'lexical_glosses','lexical_examples','lexical_example_translations',              'lexical_additional_items','lexical_audio_assets','lexical_import_batches','lexical_import_items')",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(tables, 11);
        let backlink: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM pragma_table_info('vocabulary_entries') WHERE name='sense_id'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(backlink, 1);
    }
}
