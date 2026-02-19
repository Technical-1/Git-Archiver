use std::path::Path;

use tauri::State;

use crate::core::archive;
use crate::db;
use crate::error::AppError;
use crate::models::ArchiveView;
use crate::state::AppState;

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

    if !archive_path.exists() {
        return Err(AppError::UserVisible(format!(
            "Archive file not found on disk: '{}'",
            archive_record.file_path
        )));
    }

    archive::extract_archive(archive_path, dest)?;
    Ok(())
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
