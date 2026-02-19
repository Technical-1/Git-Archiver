use tauri::State;

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
#[tauri::command]
pub async fn update_all(
    include_archived: bool,
    state: State<'_, AppState>,
) -> Result<(), AppError> {
    state
        .task_manager
        .enqueue(Task::UpdateAll { include_archived })
        .await
}

/// Cancel all active tasks and send a stop signal through the task channel.
#[tauri::command]
pub async fn stop_all_tasks(state: State<'_, AppState>) -> Result<(), AppError> {
    state.task_manager.cancel_all().await;
    Ok(())
}
