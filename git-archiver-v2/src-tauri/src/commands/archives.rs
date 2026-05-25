use std::path::Path;

use tauri::State;

use crate::core::archive;
use crate::db;
use crate::error::AppError;
use crate::models::ArchiveView;
use crate::state::AppState;

/// Validate that an extract destination is a real directory under the user's
/// home. Mirrors the threat model of `validate_import_path` in commands::repos
/// — a renderer-side XSS or malicious dependency could otherwise extract
/// archive contents to /etc/, /Library/LaunchAgents/, ~/.ssh/, etc. The normal
/// flow goes through the Tauri directory dialog (Hub #298), but the IPC is
/// still callable directly.
fn validate_extract_dest(dest: &Path) -> Result<(), AppError> {
    let canonical = dest.canonicalize().map_err(|e| {
        AppError::UserVisible(format!(
            "Cannot resolve destination '{}': {}",
            dest.display(),
            e
        ))
    })?;

    if !canonical.is_dir() {
        return Err(AppError::UserVisible(format!(
            "Extraction destination '{}' is not a directory.",
            canonical.display()
        )));
    }

    let home = dirs::home_dir()
        .ok_or_else(|| AppError::Custom("Could not determine home directory.".to_string()))?;
    let canonical_home = home
        .canonicalize()
        .map_err(|e| AppError::Custom(format!("Cannot resolve home dir: {}", e)))?;

    if !canonical.starts_with(&canonical_home) {
        return Err(AppError::UserVisible(format!(
            "Extraction destination must be inside your home directory; got '{}'.",
            canonical.display()
        )));
    }

    Ok(())
}

/// List all archives for a repository, returning frontend-safe views.
#[tauri::command]
pub async fn list_archives(
    repo_id: i64,
    state: State<'_, AppState>,
) -> Result<Vec<ArchiveView>, AppError> {
    let db = state.db.lock().await;
    let archives = db::archives::list_archives(&db, repo_id)?;
    let views: Vec<ArchiveView> = archives.iter().map(ArchiveView::from).collect();
    Ok(views)
}

/// Extract an archive to a destination directory.
#[tauri::command]
pub async fn extract_archive(
    archive_id: i64,
    dest_dir: String,
    state: State<'_, AppState>,
) -> Result<(), AppError> {
    let db = state.db.lock().await;
    let archive_record = db::archives::get_archive_by_id(&db, archive_id)?.ok_or_else(|| {
        AppError::UserVisible(format!("Archive with ID {} not found.", archive_id))
    })?;
    // Drop the lock before the potentially long extraction
    drop(db);

    let archive_path = Path::new(&archive_record.file_path);
    let dest = Path::new(&dest_dir);

    validate_extract_dest(dest)?;

    if !archive_path.exists() {
        return Err(AppError::UserVisible(format!(
            "Archive file not found on disk: '{}'",
            archive_record.file_path
        )));
    }

    archive::extract_archive(archive_path, dest)?;
    Ok(())
}

/// Get the README content for a specific archive.
#[tauri::command]
pub async fn get_archive_readme(
    archive_id: i64,
    state: State<'_, AppState>,
) -> Result<Option<String>, AppError> {
    let db = state.db.lock().await;
    db::archives::get_archive_readme(&db, archive_id)
}

/// Get the README content from the latest archive for a repository.
#[tauri::command]
pub async fn get_repo_readme(
    repo_id: i64,
    state: State<'_, AppState>,
) -> Result<Option<String>, AppError> {
    let db = state.db.lock().await;
    db::archives::get_latest_readme(&db, repo_id)
}

/// Delete an archive: remove the file from disk and the record from the database.
#[tauri::command]
pub async fn delete_archive(archive_id: i64, state: State<'_, AppState>) -> Result<(), AppError> {
    // Look up the archive and drop the lock before filesystem I/O
    let file_path = {
        let db = state.db.lock().await;
        let archive_record =
            db::archives::get_archive_by_id(&db, archive_id)?.ok_or_else(|| {
                AppError::UserVisible(format!("Archive with ID {} not found.", archive_id))
            })?;
        archive_record.file_path.clone()
    };

    // Delete file from disk (ignore error if file already missing)
    let archive_path = Path::new(&file_path);
    if archive_path.exists() {
        archive::delete_archive_file(archive_path)?;
    }

    // Re-acquire lock for DB deletion
    let db = state.db.lock().await;
    db::archives::delete_archive(&db, archive_id)?;
    Ok(())
}
