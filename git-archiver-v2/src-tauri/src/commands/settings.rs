use std::path::Path;

use tauri::State;

use crate::core::github_api::RateLimitInfo;
use crate::db;
use crate::error::AppError;
use crate::models::AppSettings;
use crate::state::AppState;

/// Validate that a data_dir setting is safe to use as the clone root.
///
/// Relative paths are always resolved against the app's own data dir at
/// runtime (lib.rs::run), so they're inherently safe. Absolute paths must
/// be under the user's home directory — otherwise a compromised renderer
/// could redirect every future clone to /etc/, /System/, etc.
///
/// If the absolute path doesn't yet exist (the worker will create it on
/// first clone), walk up to the first existing ancestor and check that.
fn validate_data_dir(data_dir: &str) -> Result<(), AppError> {
    let path = Path::new(data_dir);

    if path.is_relative() {
        return Ok(());
    }

    let home = dirs::home_dir()
        .ok_or_else(|| AppError::Custom("Could not determine home directory.".to_string()))?;
    let canonical_home = home
        .canonicalize()
        .map_err(|e| AppError::Custom(format!("Cannot resolve home dir: {}", e)))?;

    // Walk up to the first existing ancestor so a not-yet-created data_dir
    // can still be validated.
    let mut existing = path;
    while !existing.exists() {
        match existing.parent() {
            Some(p) if !p.as_os_str().is_empty() => existing = p,
            _ => {
                return Err(AppError::UserVisible(format!(
                    "Data directory '{}' has no existing ancestor on disk.",
                    path.display()
                )));
            }
        }
    }

    let canonical_existing = existing.canonicalize().map_err(|e| {
        AppError::Custom(format!(
            "Cannot resolve '{}': {}",
            existing.display(),
            e
        ))
    })?;

    if !canonical_existing.starts_with(&canonical_home) {
        return Err(AppError::UserVisible(format!(
            "Data directory must be inside your home directory; got '{}'.",
            path.display()
        )));
    }

    Ok(())
}

/// Load application settings from the database.
#[tauri::command]
pub async fn get_settings(state: State<'_, AppState>) -> Result<AppSettings, AppError> {
    let db = state.db.lock().await;
    let settings = db::settings::get_app_settings(&db)?;
    Ok(settings)
}

/// Save application settings to the database.
///
/// If `token` is provided, it is stored in the OS keychain.
/// The token is never persisted in the database or returned to the frontend.
///
/// When `sync_time` changes, the scheduler is notified via a watch channel
/// so it can recalculate its next wake-up time without a restart.
#[tauri::command]
pub async fn save_settings(
    settings: AppSettings,
    token: Option<String>,
    state: State<'_, AppState>,
) -> Result<(), AppError> {
    validate_data_dir(&settings.data_dir)?;

    let mut db = state.db.lock().await;
    db::settings::save_app_settings(&mut db, &settings)?;

    // Notify the scheduler of sync_time changes
    let new_sync_time = settings
        .sync_time
        .as_deref()
        .and_then(|s| chrono::NaiveTime::parse_from_str(s, "%H:%M").ok());
    let _ = state.sync_time_tx.send(new_sync_time);

    // Save token to keychain if provided
    if let Some(ref token_value) = token {
        let entry =
            keyring::Entry::new("git-archiver", "github-token").map_err(AppError::Keyring)?;
        if token_value.is_empty() {
            // Empty string means clear the token. `NoEntry` is a benign no-op
            // (nothing to clear); other errors mean the keychain is locked or
            // access was denied — propagate so the user knows the clear failed
            // and the GitHub client may still be using the old token at runtime.
            match entry.delete_credential() {
                Ok(()) => {}
                Err(keyring::Error::NoEntry) => {}
                Err(e) => {
                    log::warn!("Failed to clear GitHub token from keychain: {}", e);
                    return Err(AppError::Keyring(e));
                }
            }
        } else {
            entry.set_password(token_value).map_err(AppError::Keyring)?;
        }
    }

    Ok(())
}

/// Check the current GitHub API rate limit status.
#[tauri::command]
pub async fn check_rate_limit(state: State<'_, AppState>) -> Result<RateLimitInfo, AppError> {
    let info = state.github_client.get_rate_limit().await?;
    Ok(info)
}
