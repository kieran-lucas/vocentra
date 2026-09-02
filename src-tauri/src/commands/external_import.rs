use crate::{
    AppState,
    error::{AppError, AppResult},
    services::external_import,
};
use serde_json::Value;
use tauri::{AppHandle, Emitter, State};

/// The locked production audio profile, so the import screen can state what it
/// will use instead of offering a choice.
#[tauri::command]
pub fn speech_profile() -> Value {
    serde_json::json!({
        "provider": "Microsoft Edge Read Aloud",
        "voice": "en-US-JennyNeural",
        "sourceFormat": "audio-24khz-48kbitrate-mono-mp3",
        "finalFormat": "Ogg Opus 64 kbps mono",
    })
}

/// Import one external vocabulary JSON document.
///
/// The text is written to a private file under app data and handed to the
/// importer; the file never comes from a caller-supplied path, so nothing in the
/// document can point the pipeline at another location.
#[tauri::command]
pub async fn import_external_json(
    app: AppHandle,
    state: State<'_, AppState>,
    json: String,
    target_block_id: String,
) -> AppResult<Value> {
    if json.trim().is_empty() {
        return Err(AppError::Validation(
            "Choose a vocabulary JSON file first".into(),
        ));
    }
    let exists: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM blocks WHERE id=?")
        .bind(&target_block_id)
        .fetch_one(&state.pool)
        .await?;
    if exists == 0 {
        return Err(AppError::Validation(
            "The selected target block no longer exists".into(),
        ));
    }
    let children: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM blocks WHERE parent_id=?")
        .bind(&target_block_id)
        .fetch_one(&state.pool)
        .await?;
    if children > 0 {
        return Err(AppError::Validation(
            "Vocabulary can only be imported into a leaf block".into(),
        ));
    }
    let staging = state.app_data_dir.join("imports");
    tokio::fs::create_dir_all(&staging).await.map_err(|error| {
        AppError::Internal(format!("Could not prepare the import folder: {error}"))
    })?;
    let file = staging.join(format!("{}.json", uuid::Uuid::new_v4()));
    tokio::fs::write(&file, json.as_bytes())
        .await
        .map_err(|error| AppError::Internal(format!("Could not stage the import file: {error}")))?;

    let database = state.app_data_dir.join("lexium.sqlite3");
    let handle = app.clone();
    let outcome = external_import::run(
        &file,
        &target_block_id,
        &database,
        &state.app_data_dir,
        move |event| {
            let _ = handle.emit(external_import::PROGRESS_EVENT, event);
        },
    )
    .await;
    let _ = tokio::fs::remove_file(&file).await;
    outcome
}
