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
    offset: Option<i64>,
    limit: Option<i64>,
) -> AppResult<Vec<ManagedEntry>> {
    vocabulary::list(
        state.pool().await?,
        &block_id,
        search.as_deref().unwrap_or(""),
        offset.unwrap_or(0).max(0),
        limit.unwrap_or(1000).clamp(1, 1000),
    )
    .await
}
#[tauri::command]
pub async fn update_vocabulary(
    state: State<'_, AppState>,
    entry: VocabularyEntry,
) -> AppResult<()> {
    vocabulary::update(state.pool().await?, &entry).await
}
#[tauri::command]
pub async fn remove_vocabulary(
    state: State<'_, AppState>,
    block_entry_id: String,
) -> AppResult<()> {
    vocabulary::remove(state.pool().await?, &block_entry_id).await
}
