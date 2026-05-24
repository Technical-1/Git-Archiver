use std::path::Path;

use serde::Serialize;
use tauri::State;

use crate::core::task_manager::Task;
use crate::core::url::{extract_owner_repo, normalize_repo_url, validate_repo_url};
use crate::db;
use crate::error::AppError;
use crate::models::Repository;
use crate::state::AppState;

/// Validate that an import file path is reasonable: under the user's home
/// directory, a regular file, and with a known-safe extension. Prevents the
/// renderer from coercing a read of arbitrary sensitive files.
///
/// Note: There is a TOCTOU window between this validation and the subsequent
/// `read_to_string`. The threat model is renderer-side coercion (XSS,
/// malicious dependency) — NOT a local-privilege boundary. A local attacker
/// who can swap files between validation and read can already read them
/// directly, so the TOCTOU gap is acceptable.
fn validate_import_path(path: &Path) -> Result<(), AppError> {
    let canonical = path.canonicalize().map_err(|e| {
        AppError::UserVisible(format!("Cannot resolve path '{}': {}", path.display(), e))
    })?;

    if !canonical.is_file() {
        return Err(AppError::UserVisible(format!(
            "Path '{}' is not a regular file.",
            canonical.display()
        )));
    }

    let home = dirs::home_dir()
        .ok_or_else(|| AppError::Custom("Could not determine home directory.".to_string()))?;
    let canonical_home = home.canonicalize().map_err(|e| {
        AppError::Custom(format!("Cannot resolve home dir: {}", e))
    })?;
    if !canonical.starts_with(&canonical_home) {
        return Err(AppError::UserVisible(format!(
            "Import path must be inside your home directory; got '{}'.",
            canonical.display()
        )));
    }

    // Allowlist of extensions commonly used for plaintext URL lists. Comparison
    // is case-insensitive (".TXT" accepts as ".txt"). Markdown is included
    // because users sometimes maintain repo lists as bullet-point .md files;
    // we never execute or render the file, only line-split it.
    let allowed_exts = ["txt", "csv", "list", "md"];
    let ext_ok = canonical
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| allowed_exts.contains(&e.to_lowercase().as_str()))
        .unwrap_or(false);
    if !ext_ok {
        return Err(AppError::UserVisible(format!(
            "Import file must have one of these extensions: {}. Got '{}'.",
            allowed_exts.join(", "),
            canonical.display()
        )));
    }

    Ok(())
}

/// Summary returned after a bulk URL import.
#[derive(Debug, Clone, Serialize)]
pub struct BulkAddResult {
    pub added: u32,
    pub skipped: u32,
    pub errors: Vec<String>,
}

/// Add a single repository by URL.
///
/// Normalizes and validates the URL, extracts owner/repo, inserts into the DB,
/// and automatically enqueues a clone task.
#[tauri::command]
pub async fn add_repo(url: String, state: State<'_, AppState>) -> Result<Repository, AppError> {
    validate_repo_url(&url)?;

    let normalized = normalize_repo_url(&url);
    let (owner, repo_name) = extract_owner_repo(&normalized)?;

    // Scope the DB lock so it's dropped before the async enqueue
    let repo = {
        let db = state.db.lock().await;

        if let Some(_existing) = db::repos::get_repo_by_url(&db, &normalized)? {
            return Err(AppError::UserVisible(format!(
                "Repository '{}' is already tracked.",
                normalized
            )));
        }

        db::repos::insert_repo(&db, &owner, &repo_name, &normalized)?
    };

    // Auto-clone the newly added repo
    if let Some(id) = repo.id {
        if let Err(e) = state.task_manager.enqueue(Task::Clone(id)).await {
            log::warn!(
                "Auto-clone enqueue failed for {}/{}: {}",
                owner,
                repo_name,
                e
            );
        }
    }

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
    // Cancel any active task and wait briefly for the worker to acknowledge
    // so we don't race with in-flight file writes or archive inserts.
    let acknowledged = state
        .task_manager
        .cancel_and_wait(id, std::time::Duration::from_secs(5))
        .await;
    if !acknowledged {
        log::warn!(
            "Task for repo {} did not acknowledge cancellation within 5s; \
             proceeding with deletion (in-flight writes may produce orphan files).",
            id
        );
    }

    let db = state.db.lock().await;

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
/// Validates each URL, skips duplicates, inserts into the DB,
/// and automatically enqueues clone tasks for all newly added repos.
#[tauri::command]
pub async fn import_from_file(
    path: String,
    state: State<'_, AppState>,
) -> Result<BulkAddResult, AppError> {
    let path_ref = std::path::Path::new(&path);
    validate_import_path(path_ref)?;

    let content = std::fs::read_to_string(path_ref)
        .map_err(|e| AppError::UserVisible(format!("Failed to read file '{}': {}", path, e)))?;

    let mut added: u32 = 0;
    let mut skipped: u32 = 0;
    let mut errors: Vec<String> = Vec::new();
    let mut new_repo_ids: Vec<i64> = Vec::new();

    // Scope the DB lock — drop before async enqueue operations
    {
        let db = state.db.lock().await;

        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }

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
                Ok(repo) => {
                    added += 1;
                    if let Some(id) = repo.id {
                        new_repo_ids.push(id);
                    }
                }
                Err(e) => errors.push(format!("{}: {}", trimmed, e)),
            }
        }
    } // DB lock dropped here

    // Auto-clone all newly added repos
    for id in new_repo_ids {
        if let Err(e) = state.task_manager.enqueue(Task::Clone(id)).await {
            log::warn!("Auto-clone enqueue failed for repo {}: {}", id, e);
        }
    }

    Ok(BulkAddResult {
        added,
        skipped,
        errors,
    })
}

#[cfg(test)]
mod tests {
    use super::validate_import_path;
    use std::path::Path;

    #[test]
    fn test_validate_rejects_outside_home() {
        // /usr is guaranteed to exist on every Unix-like system and is outside $HOME,
        // making this assertion stable across local dev and CI without depending on
        // /etc/passwd presence.
        let result = validate_import_path(Path::new("/usr"));
        assert!(result.is_err(), "Should reject /usr (outside home)");
    }

    #[test]
    fn test_validate_rejects_disallowed_extension() {
        let home = dirs::home_dir().unwrap();
        let tmp_file = home.join(".audit-test-import.key");
        std::fs::write(&tmp_file, "").unwrap();

        let result = validate_import_path(&tmp_file);
        assert!(result.is_err(), "Should reject .key extension");

        let _ = std::fs::remove_file(&tmp_file);
    }

    #[test]
    fn test_validate_accepts_txt_under_home() {
        let home = dirs::home_dir().unwrap();
        let tmp_file = home.join(".audit-test-import.txt");
        std::fs::write(&tmp_file, "https://github.com/foo/bar").unwrap();

        let result = validate_import_path(&tmp_file);
        assert!(result.is_ok(), "Should accept .txt under home, got: {:?}", result);

        let _ = std::fs::remove_file(&tmp_file);
    }
}
