use tauri::State;

use crate::core::github_api::RateLimitInfo;
use crate::db;
use crate::error::AppError;
use crate::models::AppSettings;
use crate::state::AppState;

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
            // Empty string means clear the token
            let _ = entry.delete_credential();
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
