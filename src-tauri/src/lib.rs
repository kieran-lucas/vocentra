mod commands;
mod db;
mod error;
mod models;
mod repositories;
mod services;
use services::study::StudySessions;
use sqlx::SqlitePool;
use std::path::PathBuf;
use tokio::sync::OnceCell;
pub struct AppState {
    pool: OnceCell<Result<SqlitePool, String>>,
    sessions: StudySessions,
    app_data_dir: PathBuf,
}
impl AppState {
    async fn pool(&self) -> error::AppResult<&SqlitePool> {
        self.pool
            .get_or_init(|| async {
                db::connect(&self.app_data_dir.join("lexium.sqlite3"))
                    .await
                    .map_err(|error| error.to_string())
            })
            .await
            .as_ref()
            .map_err(|message| error::AppError::Internal(message.clone()))
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            use tauri::Manager;
            let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
            app.manage(AppState {
                pool: OnceCell::new(),
                sessions: StudySessions::default(),
                app_data_dir,
            });
            // Start migrations alongside WebView creation. Commands await the same
            // initialization, so no query can run against a partial schema.
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let state = handle.state::<AppState>();
                let _ = state.pool().await;
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::audio::load_audio,
            commands::blocks::list_blocks,
            commands::blocks::create_block,
            commands::blocks::update_block,
            commands::blocks::delete_block,
            commands::vocabulary::list_vocabulary,
            commands::vocabulary::update_vocabulary,
            commands::vocabulary::remove_vocabulary,
            commands::import::preview_import,
            commands::import::import_vocabulary,
            commands::external_import::import_external_json,
            commands::external_import::speech_profile,
            commands::study::start_study,
            commands::study::study_next,
            commands::study::end_study,
            commands::study::rate_card_and_next,
            commands::study::rate_card
        ])
        .run(tauri::generate_context!())
        .expect("error while running Lexium");
}

#[cfg(test)]
mod startup_tests {
    use super::*;

    #[tokio::test]
    async fn concurrent_commands_share_one_migrated_pool() {
        let directory = tempfile::tempdir().unwrap();
        let state = AppState {
            pool: OnceCell::new(),
            sessions: StudySessions::default(),
            app_data_dir: directory.path().to_path_buf(),
        };
        let (first, second) = tokio::join!(state.pool(), state.pool());
        assert!(std::ptr::eq(first.unwrap(), second.unwrap()));
        assert!(
            !repositories::blocks::list(state.pool().await.unwrap(), None)
                .await
                .unwrap()
                .is_empty()
        );
    }

    #[tokio::test]
    async fn initialization_failure_reaches_every_waiting_command() {
        let directory = tempfile::tempdir().unwrap();
        let file = directory.path().join("file");
        std::fs::write(&file, "not a directory").unwrap();
        let state = AppState {
            pool: OnceCell::new(),
            sessions: StudySessions::default(),
            app_data_dir: file,
        };
        let (first, second) = tokio::join!(state.pool(), state.pool());
        assert_eq!(
            first.unwrap_err().to_string(),
            second.unwrap_err().to_string()
        );
        assert!(state.pool.initialized());
    }
}
