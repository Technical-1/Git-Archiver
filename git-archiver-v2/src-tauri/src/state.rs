use std::sync::Arc;

use rusqlite::Connection;
use tokio::sync::Mutex;

use crate::core::github_api::GitHubClient;
use crate::core::task_manager::TaskManager;

/// Shared application state managed by Tauri.
///
/// This struct is registered as Tauri managed state and is accessible
/// from all command handlers via `State<'_, AppState>`.
pub struct AppState {
    pub db: Arc<Mutex<Connection>>,
    pub task_manager: Arc<TaskManager>,
    pub github_client: Arc<GitHubClient>,
}
