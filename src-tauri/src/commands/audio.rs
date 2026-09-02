use crate::{
    AppState,
    error::{AppError, AppResult},
};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde::Serialize;
use std::path::Component;
use tauri::State;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AudioPayload {
    mime_type: &'static str,
    base64: String,
}

#[tauri::command]
pub async fn load_audio(
    state: State<'_, AppState>,
    relative_path: String,
) -> AppResult<AudioPayload> {
    let relative = std::path::Path::new(&relative_path);
    if relative.is_absolute()
        || relative.components().any(|part| {
            matches!(
                part,
                Component::ParentDir | Component::RootDir | Component::Prefix(_)
            )
        })
    {
        return Err(AppError::Validation("Invalid audio path".into()));
    }
    if relative.extension().and_then(|value| value.to_str()) != Some("ogg") {
        return Err(AppError::Validation(
            "Only local Ogg audio is supported".into(),
        ));
    }
    let bytes = tokio::fs::read(state.app_data_dir.join(relative))
        .await
        .map_err(|error| AppError::Internal(format!("Audio file is unavailable: {error}")))?;
    Ok(AudioPayload {
        mime_type: "audio/ogg",
        base64: STANDARD.encode(bytes),
    })
}
