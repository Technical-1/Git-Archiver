use chrono::Local;
use tauri::{AppHandle, State};

use crate::core::task_manager::Task;
use crate::error::AppError;
use crate::state::AppState;

/// Enqueue a clone task for a repository by its database ID.
#[tauri::command]
pub async fn clone_repo(id: i64, state: State<'_, AppState>) -> Result<(), AppError> {
    state.task_manager.enqueue(Task::Clone(id)).await
}

/// Enqueue an update (pull) task for a repository by its database ID.
#[tauri::command]
pub async fn update_repo(id: i64, state: State<'_, AppState>) -> Result<(), AppError> {
    state.task_manager.enqueue(Task::Update(id)).await
}

/// Enqueue an update-all task.
///
/// When `include_archived` is true, archived and deleted repos are also updated.
/// Also updates the "last sync" timestamp and tray menu text so manual syncs
/// are reflected the same way as scheduled ones.
#[tauri::command]
pub async fn update_all(
    include_archived: bool,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<(), AppError> {
    state
        .task_manager
        .enqueue(Task::UpdateAll { include_archived })
        .await?;

    // Record this as a sync (same as the scheduler does)
    if let Ok(mut sync_time) = state.last_sync_time.lock() {
        *sync_time = Some(chrono::Utc::now());
    }
    crate::tray::update_last_sync_text(
        &app,
        &format!("Last sync: {}", Local::now().format("%b %d, %I:%M %p")),
    );

    Ok(())
}

/// Cancel all active tasks and send a stop signal through the task channel.
#[tauri::command]
pub async fn stop_all_tasks(state: State<'_, AppState>) -> Result<(), AppError> {
    state.task_manager.cancel_all().await;
    Ok(())
}
