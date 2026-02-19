use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Status of a tracked repository
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RepoStatus {
    Pending,
    Active,
    Archived,
    Deleted,
    Error,
}

impl std::fmt::Display for RepoStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            RepoStatus::Pending => write!(f, "pending"),
            RepoStatus::Active => write!(f, "active"),
            RepoStatus::Archived => write!(f, "archived"),
            RepoStatus::Deleted => write!(f, "deleted"),
            RepoStatus::Error => write!(f, "error"),
        }
    }
}

/// A tracked GitHub repository
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Repository {
    pub id: Option<i64>,
    pub owner: String,
    pub name: String,
    pub url: String,
    pub status: RepoStatus,
    pub description: Option<String>,
    pub is_private: bool,
    pub local_path: Option<String>,
    pub last_checked: Option<DateTime<Utc>>,
    pub last_archived: Option<DateTime<Utc>>,
    pub error_message: Option<String>,
    pub created_at: DateTime<Utc>,
}

/// An archive snapshot of a repository
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Archive {
    pub id: Option<i64>,
    pub repo_id: i64,
    pub file_path: String,
    pub file_size: u64,
    pub file_count: u32,
    pub is_incremental: bool,
    pub commit_hash: Option<String>,
    pub created_at: DateTime<Utc>,
}

/// Stage of an in-progress task (for progress reporting)
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskStage {
    Cloning,
    Pulling,
    Archiving,
    Compressing,
    CheckingStatus,
}

impl std::fmt::Display for TaskStage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TaskStage::Cloning => write!(f, "Cloning"),
            TaskStage::Pulling => write!(f, "Pulling"),
            TaskStage::Archiving => write!(f, "Archiving"),
            TaskStage::Compressing => write!(f, "Compressing"),
            TaskStage::CheckingStatus => write!(f, "Checking status"),
        }
    }
}

/// Progress information for a running task
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskProgress {
    pub repo_url: String,
    pub stage: TaskStage,
    pub progress: Option<f64>,
    pub message: Option<String>,
}

/// Application settings
/// Note: github_token is NOT stored here. It is managed exclusively
/// via the `keyring` crate and never serialized to the frontend.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    pub data_dir: String,
    pub archive_format: String,
    pub max_concurrent_tasks: u32,
    pub auto_check_interval_minutes: Option<u32>,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            data_dir: "data".to_string(),
            archive_format: "tar.xz".to_string(),
            max_concurrent_tasks: 4,
            auto_check_interval_minutes: None,
        }
    }
}

/// Frontend-safe view of an archive (no internal file paths exposed)
#[derive(Debug, Clone, Serialize)]
pub struct ArchiveView {
    pub id: Option<i64>,
    pub repo_id: i64,
    pub filename: String,
    pub file_size: u64,
    pub file_count: u32,
    pub is_incremental: bool,
    pub created_at: DateTime<Utc>,
}

impl From<&Archive> for ArchiveView {
    fn from(archive: &Archive) -> Self {
        let filename = std::path::Path::new(&archive.file_path)
            .file_name()
            .map(|f| f.to_string_lossy().to_string())
            .unwrap_or_default();

        Self {
            id: archive.id,
            repo_id: archive.repo_id,
            filename,
            file_size: archive.file_size,
            file_count: archive.file_count,
            is_incremental: archive.is_incremental,
            created_at: archive.created_at,
        }
    }
}
