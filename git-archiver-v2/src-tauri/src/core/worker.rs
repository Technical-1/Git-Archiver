use std::path::{Path, PathBuf};
use std::sync::Arc;

use chrono::Utc;
use rusqlite::Connection;
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::{mpsc, Mutex};

use crate::core::archive;
use crate::core::git;
use crate::core::github_api::GitHubClient;
use crate::core::hasher;
use crate::core::task_manager::{Task, TaskManager};
use crate::db;
use crate::error::AppError;
use crate::models::{RepoStatus, TaskProgress, TaskStage};

/// Resolve a data_dir to an absolute path. If the stored data_dir is relative,
/// it is resolved against the app's data directory.
fn resolve_data_dir(app_handle: &AppHandle, data_dir: &str) -> PathBuf {
    let path = PathBuf::from(data_dir);
    if path.is_relative() {
        if let Ok(app_data) = app_handle.path().app_data_dir() {
            return app_data.join(data_dir);
        }
    }
    path
}

/// Remove working tree files from a cloned repo, keeping only `.git/` (for
/// future fetch/pull) and `versions/` (the compressed archives).
///
/// This prevents the data folder from storing raw source code alongside the
/// archives, roughly halving disk usage per repository.
fn clean_working_tree(repo_dir: &Path) {
    for entry in match std::fs::read_dir(repo_dir) {
        Ok(entries) => entries,
        Err(e) => {
            log::warn!("Failed to read dir {} for cleanup: {}", repo_dir.display(), e);
            return;
        }
    } {
        let entry = match entry {
            Ok(e) => e,
            Err(_) => continue,
        };
        let name = entry.file_name();
        let name_str = name.to_string_lossy();

        // Keep git metadata and archive versions
        if name_str == ".git" || name_str == "versions" {
            continue;
        }

        let path = entry.path();
        let result = if path.is_dir() {
            std::fs::remove_dir_all(&path)
        } else {
            std::fs::remove_file(&path)
        };

        if let Err(e) = result {
            log::warn!("Failed to remove {}: {}", path.display(), e);
        }
    }
}

/// README filenames to search for, in priority order.
const README_CANDIDATES: &[&str] = &[
    "README.md",
    "readme.md",
    "Readme.md",
    "README.rst",
    "README.txt",
    "README",
];

/// Read the README file from a directory, trying common filenames in order.
/// Returns None if no README is found or if reading fails.
fn read_readme_from_dir(dir: &Path) -> Option<String> {
    for candidate in README_CANDIDATES {
        let path = dir.join(candidate);
        if path.is_file() {
            match std::fs::read_to_string(&path) {
                Ok(content) => return Some(content),
                Err(e) => {
                    log::warn!("Failed to read {}: {}", path.display(), e);
                    return None;
                }
            }
        }
    }
    None
}

/// Main worker loop that processes tasks from the channel.
///
/// Spawned once at application startup. Each task acquires a semaphore permit
/// from the TaskManager before execution, limiting concurrency.
///
/// The loop runs until a `Task::Stop` sentinel is received or the channel closes.
pub async fn worker_loop(
    mut rx: mpsc::Receiver<Task>,
    app_handle: AppHandle,
    db: Arc<Mutex<Connection>>,
    github_client: Arc<GitHubClient>,
    task_manager: Arc<TaskManager>,
) {
    while let Some(task) = rx.recv().await {
        match task {
            Task::Stop => {
                log::info!("Worker loop received Stop signal, shutting down.");
                break;
            }
            task => {
                let permit = match task_manager.semaphore.clone().acquire_owned().await {
                    Ok(p) => p,
                    Err(_) => {
                        log::error!("Semaphore closed, stopping worker loop.");
                        break;
                    }
                };

                let handle = app_handle.clone();
                let db = db.clone();
                let gh = github_client.clone();
                let tm = task_manager.clone();

                tokio::spawn(async move {
                    process_task(task, &handle, &db, &gh, &tm).await;
                    drop(permit);
                });
            }
        }
    }
    log::info!("Worker loop exited.");
}

/// Dispatch a task to the appropriate handler.
async fn process_task(
    task: Task,
    app_handle: &AppHandle,
    db: &Arc<Mutex<Connection>>,
    github_client: &Arc<GitHubClient>,
    task_manager: &Arc<TaskManager>,
) {
    match task {
        Task::Clone(id) => {
            handle_clone(id, app_handle, db, github_client, task_manager).await;
        }
        Task::Update(id) => {
            handle_update(id, app_handle, db, github_client, task_manager).await;
        }
        Task::UpdateAll { include_archived } => {
            handle_update_all(include_archived, db, task_manager).await;
        }
        Task::RefreshStatuses => {
            handle_refresh_statuses(app_handle, db, github_client).await;
        }
        Task::Stop => {
            // Already handled in the main loop
        }
    }
}

/// Emit a task-complete event so the frontend can remove the task from the UI.
fn emit_task_complete(app_handle: &AppHandle, repo_url: &str) {
    let _ = app_handle.emit("task-complete", repo_url);
}

/// Payload for task-error events emitted to the frontend.
#[derive(Debug, Clone, serde::Serialize)]
struct TaskErrorPayload {
    repo_url: String,
    message: String,
}

/// Emit a task-error event so the frontend can log the failure.
fn emit_task_error(app_handle: &AppHandle, repo_url: &str, message: &str) {
    let _ = app_handle.emit(
        "task-error",
        &TaskErrorPayload {
            repo_url: repo_url.to_string(),
            message: message.to_string(),
        },
    );
}

/// Handle cloning a repository.
///
/// 1. Load repo from DB
/// 2. Determine clone path based on data_dir setting
/// 3. Clone with git2
/// 4. Create initial archive
/// 5. Update DB status, timestamps, and file hashes
async fn handle_clone(
    repo_id: i64,
    app_handle: &AppHandle,
    db: &Arc<Mutex<Connection>>,
    github_client: &Arc<GitHubClient>,
    task_manager: &Arc<TaskManager>,
) {
    // Get repo URL before running so we can emit task-complete even on error
    let repo_url = {
        let db = db.lock().await;
        db::repos::get_repo_by_id(&db, repo_id)
            .ok()
            .flatten()
            .map(|r| r.url)
    };

    let result = handle_clone_inner(repo_id, app_handle, db, github_client, task_manager).await;
    if let Err(e) = &result {
        log::error!("Clone task failed for repo {}: {}", repo_id, e);
        // Update repo status to error
        let db = db.lock().await;
        let _ = db::repos::update_repo_status(
            &db,
            repo_id,
            &RepoStatus::Error,
            Some(&format!("{}", e)),
        );
    }
    if let Some(url) = &repo_url {
        if let Err(e) = &result {
            emit_task_error(app_handle, url, &format!("{}", e));
        }
        emit_task_complete(app_handle, url);
    }
    task_manager.mark_complete(repo_id);
}

async fn handle_clone_inner(
    repo_id: i64,
    app_handle: &AppHandle,
    db: &Arc<Mutex<Connection>>,
    github_client: &Arc<GitHubClient>,
    task_manager: &Arc<TaskManager>,
) -> Result<(), AppError> {
    // Load repo from DB
    let (repo, data_dir) = {
        let db = db.lock().await;
        let repo = db::repos::get_repo_by_id(&db, repo_id)?
            .ok_or_else(|| AppError::UserVisible(format!("Repository {} not found.", repo_id)))?;
        let settings = db::settings::get_app_settings(&db)?;
        let resolved_dir = resolve_data_dir(app_handle, &settings.data_dir);
        (repo, resolved_dir)
    };

    // Check cancellation
    if let Some(token) = task_manager.get_cancellation_token(repo_id) {
        if token.is_cancelled() {
            return Ok(());
        }
    }

    // Emit progress: cloning
    let _ = app_handle.emit(
        "task-progress",
        &TaskProgress {
            repo_url: repo.url.clone(),
            stage: TaskStage::Cloning,
            progress: Some(0.0),
            message: Some(format!("Cloning {}/{}...", repo.owner, repo.name)),
        },
    );

    // Determine clone path: {data_dir}/{owner}/{name}.git
    let clone_path = data_dir
        .join(&repo.owner)
        .join(format!("{}.git", &repo.name));

    // Create parent directories
    if let Some(parent) = clone_path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    // If the clone path already contains a valid git repo (e.g., from a previous
    // delete-without-removing-files), reuse it instead of failing.
    let already_cloned =
        clone_path.join(".git").exists() || clone_path.join("HEAD").exists();

    if already_cloned {
        log::info!(
            "Reusing existing clone at {} for {}/{}",
            clone_path.display(),
            repo.owner,
            repo.name
        );
    } else {
        // Clone the repository (blocking git2 operation) with progress reporting
        let url = repo.url.clone();
        let dest = clone_path.clone();
        let clone_app = app_handle.clone();
        let clone_repo_url = repo.url.clone();
        let cancel_token = task_manager.get_cancellation_token(repo_id);
        tokio::task::spawn_blocking(move || {
            git::clone_repo(
                &url,
                &dest,
                Some(move |pct: f32, msg: &str| -> bool {
                    // Check cancellation
                    if let Some(ref token) = cancel_token {
                        if token.is_cancelled() {
                            return false;
                        }
                    }
                    let _ = clone_app.emit(
                        "task-progress",
                        &TaskProgress {
                            repo_url: clone_repo_url.clone(),
                            stage: TaskStage::Cloning,
                            progress: Some(pct as f64),
                            message: Some(msg.to_string()),
                        },
                    );
                    true
                }),
            )
        })
        .await
        .map_err(|e| AppError::Custom(format!("Clone task panicked: {}", e)))??;
    }

    // Fetch repo description from GitHub (non-fatal)
    match github_client
        .get_repo_info(&repo.owner, &repo.name)
        .await
    {
        Ok(info) => {
            let db = db.lock().await;
            let _ = db::repos::update_repo_metadata(
                &db,
                repo_id,
                info.description.as_deref(),
                info.is_private,
            );
        }
        Err(e) => {
            log::warn!(
                "Failed to fetch description for {}/{}: {}",
                repo.owner,
                repo.name,
                e
            );
        }
    }

    // Check cancellation before archiving
    if let Some(token) = task_manager.get_cancellation_token(repo_id) {
        if token.is_cancelled() {
            return Ok(());
        }
    }

    // Create initial archive with progress reporting
    let timestamp = Utc::now().format("%Y%m%d-%H%M%S");
    let versions_dir = clone_path.join("versions");
    let archive_filename = format!("{}-{}.tar.xz", repo.name, timestamp);
    let archive_path = versions_dir.join(&archive_filename);

    let src_dir = clone_path.clone();
    let arch_path = archive_path.clone();
    let archive_app = app_handle.clone();
    let archive_repo_url = repo.url.clone();
    let archive_owner = repo.owner.clone();
    let archive_name = repo.name.clone();
    let archive_info = tokio::task::spawn_blocking(move || {
        archive::create_archive(
            &src_dir,
            &arch_path,
            None,
            Some(move |processed: u32, total: u32| {
                let pct = if total > 0 {
                    processed as f64 / total as f64
                } else {
                    0.0
                };
                let _ = archive_app.emit(
                    "task-progress",
                    &TaskProgress {
                        repo_url: archive_repo_url.clone(),
                        stage: TaskStage::Archiving,
                        progress: Some(pct),
                        message: Some(format!(
                            "Archiving {}/{}: {}/{} files",
                            archive_owner, archive_name, processed, total
                        )),
                    },
                );
            }),
        )
    })
    .await
    .map_err(|e| AppError::Custom(format!("Archive task panicked: {}", e)))??;

    // Read README content from the cloned repo (best-effort)
    let readme_content = read_readme_from_dir(&clone_path);

    // Compute file hashes for future incremental detection
    let hash_dir = clone_path.clone();
    let hashes = tokio::task::spawn_blocking(move || hasher::hash_directory(&hash_dir))
        .await
        .map_err(|e| AppError::Custom(format!("Hash task panicked: {}", e)))??;

    // Update DB: status, path, timestamps, archive record, file hashes
    let now = Utc::now();
    {
        let db = db.lock().await;
        let clone_path_str = clone_path.to_string_lossy().to_string();

        db::repos::update_repo_status(&db, repo_id, &RepoStatus::Active, None)?;
        db::repos::set_repo_local_path(&db, repo_id, &clone_path_str)?;
        db::repos::update_repo_timestamps(&db, repo_id, Some(now), Some(now), Some(now))?;

        let archive_path_str = archive_path.to_string_lossy().to_string();
        db::archives::insert_archive(
            &db,
            repo_id,
            &archive_filename,
            &archive_path_str,
            archive_info.size_bytes,
            archive_info.file_count,
            false,
            readme_content.as_deref(),
        )?;

        // Store file hashes
        for (file_path, hash) in &hashes {
            db::file_hashes::upsert_file_hash(&db, repo_id, file_path, hash)?;
        }

        // Emit repo-updated event
        if let Some(updated_repo) = db::repos::get_repo_by_id(&db, repo_id)? {
            let _ = app_handle.emit("repo-updated", &updated_repo);
        }
    }

    // Clean up working tree — keep only .git/ and versions/
    clean_working_tree(&clone_path);

    // Emit progress: complete
    let _ = app_handle.emit(
        "task-progress",
        &TaskProgress {
            repo_url: repo.url.clone(),
            stage: TaskStage::Archiving,
            progress: Some(1.0),
            message: Some(format!("Clone complete for {}/{}.", repo.owner, repo.name)),
        },
    );

    Ok(())
}

/// Handle updating (pulling) a repository.
///
/// 1. Load repo from DB
/// 2. Fetch and check for updates
/// 3. If updates: pull, compute changed files, create incremental archive
/// 4. Update DB timestamps and file hashes
async fn handle_update(
    repo_id: i64,
    app_handle: &AppHandle,
    db: &Arc<Mutex<Connection>>,
    github_client: &Arc<GitHubClient>,
    task_manager: &Arc<TaskManager>,
) {
    // Get repo URL before running so we can emit task-complete even on error
    let repo_url = {
        let db = db.lock().await;
        db::repos::get_repo_by_id(&db, repo_id)
            .ok()
            .flatten()
            .map(|r| r.url)
    };

    let result = handle_update_inner(repo_id, app_handle, db, github_client, task_manager).await;
    if let Err(e) = &result {
        log::error!("Update task failed for repo {}: {}", repo_id, e);
        let db = db.lock().await;
        let _ = db::repos::update_repo_status(
            &db,
            repo_id,
            &RepoStatus::Error,
            Some(&format!("{}", e)),
        );
    }
    if let Some(url) = &repo_url {
        if let Err(e) = &result {
            emit_task_error(app_handle, url, &format!("{}", e));
        }
        emit_task_complete(app_handle, url);
    }
    task_manager.mark_complete(repo_id);
}

async fn handle_update_inner(
    repo_id: i64,
    app_handle: &AppHandle,
    db: &Arc<Mutex<Connection>>,
    github_client: &Arc<GitHubClient>,
    task_manager: &Arc<TaskManager>,
) -> Result<(), AppError> {
    // Load repo from DB
    let repo = {
        let db = db.lock().await;
        db::repos::get_repo_by_id(&db, repo_id)?
            .ok_or_else(|| AppError::UserVisible(format!("Repository {} not found.", repo_id)))?
    };

    let local_path = repo.local_path.as_ref().ok_or_else(|| {
        AppError::UserVisible(format!(
            "Repository {}/{} has no local path. Clone it first.",
            repo.owner, repo.name
        ))
    })?;

    let repo_path = PathBuf::from(local_path);
    if !repo_path.exists() {
        return Err(AppError::UserVisible(format!(
            "Local path '{}' does not exist. The repository may need to be re-cloned.",
            local_path
        )));
    }

    // Check cancellation
    if let Some(token) = task_manager.get_cancellation_token(repo_id) {
        if token.is_cancelled() {
            return Ok(());
        }
    }

    // Emit progress: pulling
    let _ = app_handle.emit(
        "task-progress",
        &TaskProgress {
            repo_url: repo.url.clone(),
            stage: TaskStage::Pulling,
            progress: Some(0.0),
            message: Some(format!(
                "Checking for updates to {}/{}...",
                repo.owner, repo.name
            )),
        },
    );

    // Fetch + pull in one pass (avoids redundant double-fetch) with progress reporting
    let pull_path = repo_path.clone();
    let pull_app = app_handle.clone();
    let pull_repo_url = repo.url.clone();
    let pull_owner = repo.owner.clone();
    let pull_name = repo.name.clone();
    let cancel_token = task_manager.get_cancellation_token(repo_id);
    let has_updates = tokio::task::spawn_blocking(move || {
        git::fetch_and_pull(
            &pull_path,
            Some(move |pct: f32, msg: &str| -> bool {
                // Check cancellation
                if let Some(ref token) = cancel_token {
                    if token.is_cancelled() {
                        return false;
                    }
                }
                let _ = pull_app.emit(
                    "task-progress",
                    &TaskProgress {
                        repo_url: pull_repo_url.clone(),
                        stage: TaskStage::Pulling,
                        progress: Some(pct as f64),
                        message: Some(format!("Pulling {}/{}: {}", pull_owner, pull_name, msg)),
                    },
                );
                true
            }),
        )
    })
    .await
    .map_err(|e| AppError::Custom(format!("Pull task panicked: {}", e)))??;

    // Refresh repo description from GitHub (non-fatal, runs regardless of updates)
    match github_client
        .get_repo_info(&repo.owner, &repo.name)
        .await
    {
        Ok(info) => {
            let db = db.lock().await;
            let _ = db::repos::update_repo_metadata(
                &db,
                repo_id,
                info.description.as_deref(),
                info.is_private,
            );
        }
        Err(e) => {
            log::warn!(
                "Failed to refresh description for {}/{}: {}",
                repo.owner,
                repo.name,
                e
            );
        }
    }

    if !has_updates {
        // Update last_checked timestamp
        let now = Utc::now();
        {
            let db = db.lock().await;
            db::repos::update_repo_timestamps(&db, repo_id, None, None, Some(now))?;

            // Emit repo-updated so the frontend gets the refreshed description
            if let Some(updated_repo) = db::repos::get_repo_by_id(&db, repo_id)? {
                let _ = app_handle.emit("repo-updated", &updated_repo);
            }
        }

        let _ = app_handle.emit(
            "task-progress",
            &TaskProgress {
                repo_url: repo.url.clone(),
                stage: TaskStage::Pulling,
                progress: Some(1.0),
                message: Some(format!(
                    "{}/{} is already up to date.",
                    repo.owner, repo.name
                )),
            },
        );
        return Ok(());
    }

    // Transition to compressing stage while hashing
    let _ = app_handle.emit(
        "task-progress",
        &TaskProgress {
            repo_url: repo.url.clone(),
            stage: TaskStage::Compressing,
            progress: Some(0.0),
            message: Some(format!(
                "Computing file hashes for {}/{}...",
                repo.owner, repo.name
            )),
        },
    );

    // Get old file hashes and compute new ones to detect changes
    let old_hashes = {
        let db = db.lock().await;
        db::file_hashes::get_file_hashes(&db, repo_id)?
    };

    let hash_dir = repo_path.clone();
    let new_hashes = tokio::task::spawn_blocking(move || hasher::hash_directory(&hash_dir))
        .await
        .map_err(|e| AppError::Custom(format!("Hash task panicked: {}", e)))??;

    let changed_files = hasher::detect_changed_files(&old_hashes, &new_hashes);

    // Create archive (incremental if we have previous hashes, full otherwise)
    let timestamp = Utc::now().format("%Y%m%d-%H%M%S");
    let versions_dir = repo_path.join("versions");
    let is_incremental = !old_hashes.is_empty() && !changed_files.is_empty();

    let archive_filename = if is_incremental {
        format!("{}-{}-incremental.tar.xz", repo.name, timestamp)
    } else {
        format!("{}-{}.tar.xz", repo.name, timestamp)
    };
    let archive_path = versions_dir.join(&archive_filename);

    let src_dir = repo_path.clone();
    let arch_path = archive_path.clone();
    let changed = if is_incremental {
        Some(changed_files)
    } else {
        None
    };
    let archive_app = app_handle.clone();
    let archive_repo_url = repo.url.clone();
    let archive_owner = repo.owner.clone();
    let archive_name = repo.name.clone();
    let archive_info = tokio::task::spawn_blocking(move || {
        archive::create_archive(
            &src_dir,
            &arch_path,
            changed.as_deref(),
            Some(move |processed: u32, total: u32| {
                let pct = if total > 0 {
                    processed as f64 / total as f64
                } else {
                    0.0
                };
                let _ = archive_app.emit(
                    "task-progress",
                    &TaskProgress {
                        repo_url: archive_repo_url.clone(),
                        stage: TaskStage::Archiving,
                        progress: Some(pct),
                        message: Some(format!(
                            "Archiving {}/{}: {}/{} files",
                            archive_owner, archive_name, processed, total
                        )),
                    },
                );
            }),
        )
    })
    .await
    .map_err(|e| AppError::Custom(format!("Archive task panicked: {}", e)))??;

    // Read README content from the repo (best-effort)
    let readme_content = read_readme_from_dir(&repo_path);

    // Update DB
    let now = Utc::now();
    {
        let db = db.lock().await;
        db::repos::update_repo_timestamps(&db, repo_id, None, Some(now), Some(now))?;

        let archive_path_str = archive_path.to_string_lossy().to_string();
        db::archives::insert_archive(
            &db,
            repo_id,
            &archive_filename,
            &archive_path_str,
            archive_info.size_bytes,
            archive_info.file_count,
            is_incremental,
            readme_content.as_deref(),
        )?;

        // Update file hashes
        for (file_path, hash) in &new_hashes {
            db::file_hashes::upsert_file_hash(&db, repo_id, file_path, hash)?;
        }

        // Emit repo-updated event
        if let Some(updated_repo) = db::repos::get_repo_by_id(&db, repo_id)? {
            let _ = app_handle.emit("repo-updated", &updated_repo);
        }
    }

    // Clean up working tree — keep only .git/ and versions/
    clean_working_tree(&repo_path);

    // Emit progress: complete
    let _ = app_handle.emit(
        "task-progress",
        &TaskProgress {
            repo_url: repo.url.clone(),
            stage: TaskStage::Archiving,
            progress: Some(1.0),
            message: Some(format!("Update complete for {}/{}.", repo.owner, repo.name)),
        },
    );

    Ok(())
}

/// Handle updating all tracked repositories.
///
/// Lists repos from the DB and enqueues an Update task for each one.
async fn handle_update_all(
    include_archived: bool,
    db: &Arc<Mutex<Connection>>,
    task_manager: &Arc<TaskManager>,
) {
    let repos = {
        let db = db.lock().await;
        match db::repos::list_repos(&db, None) {
            Ok(repos) => repos,
            Err(e) => {
                log::error!("Failed to list repos for update_all: {}", e);
                return;
            }
        }
    };

    for repo in repos {
        let id = match repo.id {
            Some(id) => id,
            None => continue,
        };

        // Skip repos that are not cloned yet
        if repo.status == RepoStatus::Pending {
            continue;
        }

        // Skip archived/deleted unless explicitly requested
        if !include_archived
            && (repo.status == RepoStatus::Archived || repo.status == RepoStatus::Deleted)
        {
            continue;
        }

        if let Err(e) = task_manager.enqueue(Task::Update(id)).await {
            log::warn!("Skipping update for {}/{}: {}", repo.owner, repo.name, e);
        }
    }
}

/// Handle refreshing repository statuses via the GitHub API.
///
/// Batches all tracked repos and uses the GitHub client to detect
/// whether each is active, archived, or deleted.
async fn handle_refresh_statuses(
    app_handle: &AppHandle,
    db: &Arc<Mutex<Connection>>,
    github_client: &Arc<GitHubClient>,
) {
    // Emit progress
    let _ = app_handle.emit(
        "task-progress",
        &TaskProgress {
            repo_url: String::new(),
            stage: TaskStage::CheckingStatus,
            progress: Some(0.0),
            message: Some("Refreshing repository statuses...".to_string()),
        },
    );

    let repos = {
        let db = db.lock().await;
        match db::repos::list_repos(&db, None) {
            Ok(repos) => repos,
            Err(e) => {
                log::error!("Failed to list repos for status refresh: {}", e);
                return;
            }
        }
    };

    if repos.is_empty() {
        return;
    }

    // Build list of (owner, name) tuples for batch detection
    let repo_pairs: Vec<(String, String)> = repos
        .iter()
        .map(|r| (r.owner.clone(), r.name.clone()))
        .collect();

    let statuses = match github_client.detect_repo_statuses(&repo_pairs).await {
        Ok(s) => s,
        Err(e) => {
            log::error!("Failed to detect repo statuses: {}", e);
            return;
        }
    };

    // Update each repo's status in the DB
    let db = db.lock().await;
    for (i, (_owner, _name, new_status)) in statuses.iter().enumerate() {
        if i < repos.len() {
            if let Some(id) = repos[i].id {
                if repos[i].status != *new_status {
                    let _ = db::repos::update_repo_status(&db, id, new_status, None);

                    // Emit repo-updated event
                    if let Ok(Some(updated_repo)) = db::repos::get_repo_by_id(&db, id) {
                        let _ = app_handle.emit("repo-updated", &updated_repo);
                    }
                }

                // Update last_checked timestamp
                let now = Utc::now();
                let _ = db::repos::update_repo_timestamps(&db, id, None, None, Some(now));
            }
        }
    }

    // Emit progress: complete
    let _ = app_handle.emit(
        "task-progress",
        &TaskProgress {
            repo_url: String::new(),
            stage: TaskStage::CheckingStatus,
            progress: Some(1.0),
            message: Some("Status refresh complete.".to_string()),
        },
    );
}
