use crate::{
    AppState,
    error::AppResult,
    models::{BlockSummary, NewBlock},
    repositories::blocks,
};
use tauri::State;
#[tauri::command]
pub async fn list_blocks(
    state: State<'_, AppState>,
    parent_id: Option<String>,
) -> AppResult<Vec<BlockSummary>> {
    blocks::list(&state.pool, parent_id.as_deref()).await
}
#[tauri::command]
pub async fn create_block(state: State<'_, AppState>, input: NewBlock) -> AppResult<String> {
    blocks::create(&state.pool, input).await
}
#[tauri::command]
pub async fn update_block(
    state: State<'_, AppState>,
    id: String,
    name: String,
    icon_key: String,
) -> AppResult<()> {
    blocks::update(&state.pool, &id, &name, &icon_key).await
}
#[tauri::command]
pub async fn delete_block(state: State<'_, AppState>, id: String) -> AppResult<()> {
    blocks::delete(&state.pool, &id).await
}
