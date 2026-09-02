use crate::{
    AppState,
    error::AppResult,
    models::{ManagedEntry, VocabularyEntry},
    repositories::vocabulary,
};
use tauri::State;
#[tauri::command]
pub async fn list_vocabulary(
    state: State<'_, AppState>,
    block_id: String,
    search: Option<String>,
) -> AppResult<Vec<ManagedEntry>> {
    vocabulary::list(&state.pool, &block_id, search.as_deref().unwrap_or("")).await
}
#[tauri::command]
pub async fn update_vocabulary(
    state: State<'_, AppState>,
    entry: VocabularyEntry,
) -> AppResult<()> {
    vocabulary::update(&state.pool, &entry).await
}
#[tauri::command]
pub async fn remove_vocabulary(
    state: State<'_, AppState>,
    block_entry_id: String,
) -> AppResult<()> {
    vocabulary::remove(&state.pool, &block_entry_id).await
}
