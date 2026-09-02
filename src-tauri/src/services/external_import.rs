//! Bridge to the one authoritative importer.
//!
//! The app never parses the vocabulary contract, never talks to the speech
//! service and never encodes audio: it hands the file to
//! `tools/ingest/import_external_vocabulary.py` and relays that process's
//! JSON-lines progress. The importer launches only when an import is requested
//! and exits when it is done, so nothing runs in the background.

use crate::error::{AppError, AppResult};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

pub const PROGRESS_EVENT: &str = "external-import://progress";

/// How to launch the importer, resolved at call time rather than at startup.
pub enum Importer {
    /// A packaged single-file build shipped next to the executable.
    Sidecar(PathBuf),
    /// The checked-out repository, run through uv. Development only.
    Repository(PathBuf),
}

impl Importer {
    fn program_and_args(
        &self,
        file: &Path,
        target_block_id: &str,
        database: &Path,
        app_data: &Path,
    ) -> (String, Vec<String>) {
        let common = |mut args: Vec<String>| {
            args.extend([
                file.to_string_lossy().into_owned(),
                "--target-block-id".into(),
                target_block_id.to_owned(),
                "--progress-json".into(),
                "--db".into(),
                database.to_string_lossy().into_owned(),
                "--app-data".into(),
                app_data.to_string_lossy().into_owned(),
            ]);
            args
        };
        match self {
            Self::Sidecar(path) => (path.to_string_lossy().into_owned(), common(Vec::new())),
            Self::Repository(script) => (
                "uv".into(),
                common(vec!["run".into(), script.to_string_lossy().into_owned()]),
            ),
        }
    }
}

fn sidecar_name() -> &'static str {
    if cfg!(windows) {
        "lexium-import.exe"
    } else {
        "lexium-import"
    }
}

impl Importer {
    /// Which route was taken, for the progress log and the release smoke test.
    pub fn describe(&self) -> (&'static str, String) {
        match self {
            Self::Sidecar(path) => ("sidecar", path.display().to_string()),
            Self::Repository(path) => ("repository", path.display().to_string()),
        }
    }
}

/// Resolve the importer, bundled copy first.
///
/// An installed build always finds the sidecar Tauri placed beside the
/// executable, so release behaviour does not depend on the environment.
/// `LEXIUM_IMPORTER` and the checked-out script are development fallbacks only.
pub fn resolve_importer() -> AppResult<Importer> {
    if let Ok(executable) = std::env::current_exe()
        && let Some(directory) = executable.parent()
    {
        let sidecar = directory.join(sidecar_name());
        if sidecar.is_file() {
            return Ok(Importer::Sidecar(sidecar));
        }
    }
    if let Ok(custom) = std::env::var("LEXIUM_IMPORTER") {
        let path = PathBuf::from(custom);
        if path.is_file() {
            return Ok(Importer::Sidecar(path));
        }
        return Err(AppError::Internal(format!(
            "LEXIUM_IMPORTER points at {}, which is not a file",
            path.display()
        )));
    }
    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../tools/ingest/import_external_vocabulary.py");
    if script.is_file() {
        return Ok(Importer::Repository(script));
    }
    Err(AppError::Internal(format!(
        "The vocabulary importer is unavailable. This build is missing {}, which \
         the installer should place beside the application.",
        sidecar_name()
    )))
}

/// Run one import, relaying every progress line through `on_event`.
pub async fn run<F>(
    file: &Path,
    target_block_id: &str,
    database: &Path,
    app_data: &Path,
    mut on_event: F,
) -> AppResult<Value>
where
    F: FnMut(Value),
{
    let importer = resolve_importer()?;
    let (route, location) = importer.describe();
    on_event(serde_json::json!({"stage": "importer", "route": route, "path": location}));
    let (program, args) = importer.program_and_args(file, target_block_id, database, app_data);
    let mut child = Command::new(&program)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| {
            AppError::Internal(format!(
                "Could not start the vocabulary importer ({program}): {error}"
            ))
        })?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| AppError::Internal("importer produced no output".into()))?;
    let stderr = child.stderr.take();
    let mut lines = BufReader::new(stdout).lines();
    let mut summary: Option<Value> = None;
    let mut refusal: Option<String> = None;

    while let Some(line) = lines
        .next_line()
        .await
        .map_err(|error| AppError::Internal(error.to_string()))?
    {
        let Ok(event) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        match event.get("stage").and_then(Value::as_str) {
            Some("summary") => summary = Some(event.clone()),
            Some("rejected") => {
                let errors = event
                    .get("errors")
                    .and_then(Value::as_array)
                    .map(|items| {
                        items
                            .iter()
                            .filter_map(Value::as_str)
                            .collect::<Vec<_>>()
                            .join("\n")
                    })
                    .unwrap_or_default();
                refusal = Some(errors);
            }
            Some("error") => {
                refusal = Some(
                    event
                        .get("message")
                        .and_then(Value::as_str)
                        .unwrap_or("import failed")
                        .to_string(),
                )
            }
            _ => {}
        }
        on_event(event);
    }

    let status = child
        .wait()
        .await
        .map_err(|error| AppError::Internal(error.to_string()))?;
    if let Some(message) = refusal {
        return Err(AppError::Validation(message));
    }
    if let Some(summary) = summary {
        return Ok(summary);
    }
    let mut detail = String::new();
    if let Some(stderr) = stderr {
        let mut lines = BufReader::new(stderr).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            detail.push_str(&line);
            detail.push('\n');
        }
    }
    Err(AppError::Internal(format!(
        "The importer exited with {status} without reporting a result.\n{}",
        detail.trim()
    )))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repository_invocation_passes_the_file_database_and_app_data() {
        let importer = Importer::Repository(PathBuf::from("/repo/import.py"));
        let (program, args) = importer.program_and_args(
            Path::new("/tmp/batch.json"),
            "leaf-123",
            Path::new("/data/lexium.sqlite3"),
            Path::new("/data"),
        );
        assert_eq!(program, "uv");
        assert_eq!(args[0], "run");
        assert!(args.iter().any(|value| value.ends_with("import.py")));
        assert!(args.iter().any(|value| value == "--progress-json"));
        assert!(args.iter().any(|value| value.ends_with("batch.json")));
        assert!(args.iter().any(|value| value.ends_with("lexium.sqlite3")));
        assert!(args.iter().any(|value| value == "--app-data"));
        assert!(
            args.windows(2)
                .any(|pair| pair == ["--target-block-id", "leaf-123"])
        );
    }

    #[test]
    fn sidecar_invocation_has_no_interpreter_arguments() {
        let importer = Importer::Sidecar(PathBuf::from("/apps/lexium-import.exe"));
        let (program, args) = importer.program_and_args(
            Path::new("/tmp/batch.json"),
            "leaf-123",
            Path::new("/data/lexium.sqlite3"),
            Path::new("/data"),
        );
        assert!(program.ends_with("lexium-import.exe"));
        assert!(!args.iter().any(|value| value == "run"));
        assert_eq!(args[0], "/tmp/batch.json");
    }

    #[test]
    fn each_route_reports_itself_for_the_progress_log() {
        let (route, path) = Importer::Sidecar(PathBuf::from("/apps/lexium-import.exe")).describe();
        assert_eq!(route, "sidecar");
        assert!(path.ends_with("lexium-import.exe"));
        let (route, path) = Importer::Repository(PathBuf::from("/repo/import.py")).describe();
        assert_eq!(route, "repository");
        assert!(path.ends_with("import.py"));
    }

    #[test]
    fn the_bundled_sidecar_outranks_the_environment_override() {
        // A release build must resolve the same way regardless of environment,
        // so the sidecar check runs before LEXIUM_IMPORTER is consulted.
        let source = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/src/services/external_import.rs"
        ))
        .unwrap();
        let body = source.split("pub fn resolve_importer").nth(1).unwrap();
        let sidecar_at = body.find("sidecar.is_file()").unwrap();
        let override_at = body.find("LEXIUM_IMPORTER").unwrap();
        assert!(sidecar_at < override_at);
    }

    #[test]
    fn the_release_bundle_is_wired_to_ship_the_importer_and_ffmpeg() {
        // Guards the fail-closed release path: without these the installer would
        // build cleanly and then be unable to import anything.
        let config: serde_json::Value =
            serde_json::from_str(include_str!("../../tauri.conf.json")).unwrap();
        let bundle = &config["bundle"];
        assert_eq!(bundle["externalBin"][0], "binaries/lexium-import");
        assert_eq!(bundle["resources"][0], "ffmpeg/*");
        let before = config["build"]["beforeBuildCommand"].as_str().unwrap();
        assert!(
            before.contains("build_importer_sidecar.ps1"),
            "release builds must build the sidecar, got: {before}"
        );
    }

    #[test]
    fn a_missing_importer_names_the_binary_to_ship() {
        // The repository script exists in a development checkout, so this only
        // asserts the error text when neither route resolves.
        let message = AppError::Internal(format!(
            "The vocabulary importer is unavailable. Ship {} beside the application, \
             or set LEXIUM_IMPORTER to its path.",
            sidecar_name()
        ))
        .to_string();
        assert!(message.contains("lexium-import"));
    }
}
