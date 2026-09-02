use crate::{
    AppState,
    error::AppResult,
    models::{ImportPreview, ImportResult},
    services::import_validation,
};
use tauri::State;
#[tauri::command]
pub fn preview_import(json: String) -> AppResult<ImportPreview> {
    import_validation::preview(&json)
}
#[tauri::command]
pub async fn import_vocabulary(
    state: State<'_, AppState>,
    block_id: String,
    json: String,
) -> AppResult<ImportResult> {
    import_validation::import(&state.pool, &block_id, &json).await
}
