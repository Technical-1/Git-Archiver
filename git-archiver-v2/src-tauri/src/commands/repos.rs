use serde::Serialize;
use tauri::State;

use crate::core::url::{extract_owner_repo, normalize_repo_url, validate_repo_url};
use crate::db;
use crate::error::AppError;
use crate::models::Repository;
use crate::state::AppState;

/// Summary returned after a bulk URL import.
#[derive(Debug, Clone, Serialize)]
pub struct BulkAddResult {
    pub added: u32,
    pub skipped: u32,
    pub errors: Vec<String>,
}

/// Add a single repository by URL.
///
/// Normalizes and validates the URL, extracts owner/repo, and inserts into the DB.
/// Returns the newly created repository record.
#[tauri::command]
pub async fn add_repo(url: String, state: State<'_, AppState>) -> Result<Repository, AppError> {
    // Validate the raw URL first
    validate_repo_url(&url)?;

    let normalized = normalize_repo_url(&url);
    let (owner, repo_name) = extract_owner_repo(&normalized)?;

    let db = state.db.lock().await;

    // Check for duplicate
    if let Some(_existing) = db::repos::get_repo_by_url(&db, &normalized)? {
        return Err(AppError::UserVisible(format!(
            "Repository '{}' is already tracked.",
            normalized
        )));
    }

    let repo = db::repos::insert_repo(&db, &owner, &repo_name, &normalized)?;
    Ok(repo)
}

/// List repositories with an optional status filter.
///
/// `status_filter` accepts: "pending", "active", "archived", "deleted", "error", or None for all.
#[tauri::command]
pub async fn list_repos(
    status_filter: Option<String>,
    state: State<'_, AppState>,
) -> Result<Vec<Repository>, AppError> {
    let db = state.db.lock().await;

    let status = match status_filter.as_deref() {
        Some("pending") => Some(crate::models::RepoStatus::Pending),
        Some("active") => Some(crate::models::RepoStatus::Active),
        Some("archived") => Some(crate::models::RepoStatus::Archived),
        Some("deleted") => Some(crate::models::RepoStatus::Deleted),
        Some("error") => Some(crate::models::RepoStatus::Error),
        Some(other) => {
            return Err(AppError::UserVisible(format!(
                "Unknown status filter: '{}'",
                other
            )));
        }
        None => None,
    };

    let repos = db::repos::list_repos(&db, status.as_ref())?;
    Ok(repos)
}

/// Delete a repository by ID.
///
/// Cancels any active task for the repo, removes it from the database,
/// and optionally deletes the cloned files from disk.
#[tauri::command]
pub async fn delete_repo(
    id: i64,
    remove_files: bool,
    state: State<'_, AppState>,
) -> Result<(), AppError> {
    // Cancel any active task for this repo
    state.task_manager.cancel(id).await;

    let db = state.db.lock().await;

    // Get the repo to find its local path before deleting
    let repo = db::repos::get_repo_by_id(&db, id)?;

    if let Some(ref repo) = repo {
        if remove_files {
            if let Some(ref local_path) = repo.local_path {
                let path = std::path::Path::new(local_path);
                if path.exists() {
                    std::fs::remove_dir_all(path).map_err(|e| {
                        AppError::Custom(format!(
                            "Failed to remove files at '{}': {}",
                            local_path, e
                        ))
                    })?;
                }
            }
        }
    }

    db::repos::delete_repo(&db, id)?;
    Ok(())
}

/// Import repository URLs from a text file (one URL per line).
///
/// Validates each URL, skips duplicates, and returns a summary of what happened.
#[tauri::command]
pub async fn import_from_file(
    path: String,
    state: State<'_, AppState>,
) -> Result<BulkAddResult, AppError> {
    let content = std::fs::read_to_string(&path).map_err(|e| {
        AppError::UserVisible(format!("Failed to read file '{}': {}", path, e))
    })?;

    let mut added: u32 = 0;
    let mut skipped: u32 = 0;
    let mut errors: Vec<String> = Vec::new();

    let db = state.db.lock().await;

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        // Validate
        if let Err(e) = validate_repo_url(trimmed) {
            errors.push(format!("{}: {}", trimmed, e));
            continue;
        }

        let normalized = normalize_repo_url(trimmed);
        let (owner, repo_name) = match extract_owner_repo(&normalized) {
            Ok(pair) => pair,
            Err(e) => {
                errors.push(format!("{}: {}", trimmed, e));
                continue;
            }
        };

        // Check for duplicate
        match db::repos::get_repo_by_url(&db, &normalized) {
            Ok(Some(_)) => {
                skipped += 1;
                continue;
            }
            Ok(None) => {}
            Err(e) => {
                errors.push(format!("{}: {}", trimmed, e));
                continue;
            }
        }

        match db::repos::insert_repo(&db, &owner, &repo_name, &normalized) {
            Ok(_) => added += 1,
            Err(e) => errors.push(format!("{}: {}", trimmed, e)),
        }
    }

    Ok(BulkAddResult {
        added,
        skipped,
        errors,
    })
}
