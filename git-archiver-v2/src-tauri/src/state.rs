use std::sync::Arc;

use chrono::{DateTime, NaiveTime, Utc};
use rusqlite::Connection;
use tokio::sync::{watch, Mutex};

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
    /// Timestamp of the last completed scheduled sync.
    pub last_sync_time: Arc<std::sync::Mutex<Option<DateTime<Utc>>>>,
    /// Channel to notify the scheduler when sync_time settings change.
    pub sync_time_tx: watch::Sender<Option<NaiveTime>>,
}
