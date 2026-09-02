use crate::{
    AppState,
    error::AppResult,
    models::{Rating, StudyNext, StudyStart},
    services::study,
};
use tauri::State;
#[tauri::command]
pub async fn start_study(state: State<'_, AppState>, block_id: String) -> AppResult<StudyStart> {
    study::start(&state.pool, &state.sessions, &block_id).await
}
#[tauri::command]
pub async fn study_next(state: State<'_, AppState>, turn_id: String) -> AppResult<StudyNext> {
    study::next(&state.sessions, &turn_id).await
}
#[tauri::command]
pub async fn rate_card(
    state: State<'_, AppState>,
    turn_id: String,
    rating: Rating,
    typing_correct: i64,
    typing_errors: i64,
) -> AppResult<()> {
    study::rate(
        &state.pool,
        &state.sessions,
        &turn_id,
        rating,
        typing_correct,
        typing_errors,
    )
    .await
}
