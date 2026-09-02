mod commands;
mod db;
mod error;
mod models;
mod repositories;
mod services;
use services::study::StudySessions;
use sqlx::SqlitePool;
use std::path::PathBuf;
pub struct AppState {
    pool: SqlitePool,
    sessions: StudySessions,
    app_data_dir: PathBuf,
}
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            use tauri::Manager;
            let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
            let path = app_data_dir.join("lexium.sqlite3");
            let pool =
                tauri::async_runtime::block_on(db::connect(&path)).map_err(|e| e.to_string())?;
            app.manage(AppState {
                pool,
                sessions: StudySessions::default(),
                app_data_dir,
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
            commands::study::rate_card
        ])
        .run(tauri::generate_context!())
        .expect("error while running Lexium");
}
