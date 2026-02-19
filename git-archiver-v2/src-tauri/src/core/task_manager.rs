use std::sync::Arc;

use dashmap::DashMap;
use tokio::sync::{mpsc, Semaphore};
use tokio_util::sync::CancellationToken;

use crate::error::AppError;

/// Channel buffer size for the task queue.
const CHANNEL_BUFFER: usize = 100;

/// A task to be processed by the worker loop.
#[derive(Debug)]
pub enum Task {
    /// Clone a repository by its database ID.
    Clone(i64),
    /// Update (pull) a repository by its database ID.
    Update(i64),
    /// Update all tracked repositories.
    UpdateAll { include_archived: bool },
    /// Refresh statuses for all tracked repositories.
    RefreshStatuses,
    /// Graceful shutdown sentinel.
    Stop,
}

/// Async task queue with configurable concurrency, deduplication, and cancellation.
///
/// The `TaskManager` sits between Tauri commands and the worker loop (M8).
/// When the frontend invokes an operation, the corresponding Tauri command
/// enqueues a [`Task`] here. The worker loop receives tasks from the channel
/// and processes them, acquiring a semaphore permit for each concurrent task.
pub struct TaskManager {
    /// Sender half of the task channel.
    tx: mpsc::Sender<Task>,
    /// Map of active per-repo tasks to their cancellation tokens.
    /// Only `Task::Clone` and `Task::Update` are tracked here.
    active_tasks: DashMap<i64, CancellationToken>,
    /// Semaphore controlling maximum concurrent task execution.
    /// The worker loop acquires a permit before spawning each task.
    pub semaphore: Arc<Semaphore>,
}

impl TaskManager {
    /// Creates a new `TaskManager` with the given concurrency limit.
    ///
    /// Returns an `Arc<TaskManager>` and the receiving half of the task channel.
    /// The receiver should be owned by the worker loop (M8).
    ///
    /// `max_concurrent` is clamped to the range `[1, 16]`.
    pub fn new(max_concurrent: u32) -> (Arc<Self>, mpsc::Receiver<Task>) {
        let clamped = max_concurrent.clamp(1, 16) as usize;
        let (tx, rx) = mpsc::channel(CHANNEL_BUFFER);

        let manager = Arc::new(Self {
            tx,
            active_tasks: DashMap::new(),
            semaphore: Arc::new(Semaphore::new(clamped)),
        });

        (manager, rx)
    }

    /// Enqueues a task for processing.
    ///
    /// For `Task::Clone` and `Task::Update`, performs deduplication: if the
    /// given repo ID is already active, returns `AppError::UserVisible`.
    ///
    /// `Task::UpdateAll`, `Task::RefreshStatuses`, and `Task::Stop` are sent
    /// directly through the channel without deduplication.
    pub async fn enqueue(&self, task: Task) -> Result<(), AppError> {
        match &task {
            Task::Clone(id) | Task::Update(id) => {
                let repo_id = *id;

                // Deduplication check: reject if already active.
                if self.active_tasks.contains_key(&repo_id) {
                    return Err(AppError::UserVisible(format!(
                        "A task for repository {} is already in progress.",
                        repo_id
                    )));
                }

                // Register the task with a new cancellation token.
                let token = CancellationToken::new();
                self.active_tasks.insert(repo_id, token);

                // Send through the channel.
                self.tx.send(task).await.map_err(|_| {
                    // If send fails, clean up the active entry.
                    self.active_tasks.remove(&repo_id);
                    AppError::Custom("Task channel closed.".to_string())
                })?;
            }
            Task::UpdateAll { .. } | Task::RefreshStatuses | Task::Stop => {
                self.tx
                    .send(task)
                    .await
                    .map_err(|_| AppError::Custom("Task channel closed.".to_string()))?;
            }
        }

        Ok(())
    }

    /// Cancels the task for the given repo ID.
    ///
    /// Triggers the cancellation token and removes the task from active tracking.
    /// No-op if the repo ID is not active.
    pub async fn cancel(&self, repo_id: i64) {
        if let Some((_, token)) = self.active_tasks.remove(&repo_id) {
            token.cancel();
        }
    }

    /// Cancels all active per-repo tasks.
    pub async fn cancel_all(&self) {
        // Collect all entries first to avoid holding the lock during cancellation.
        let entries: Vec<(i64, CancellationToken)> = self
            .active_tasks
            .iter()
            .map(|entry| (*entry.key(), entry.value().clone()))
            .collect();

        for (id, token) in entries {
            token.cancel();
            self.active_tasks.remove(&id);
        }
    }

    /// Returns `true` if a task for the given repo ID is currently active.
    pub fn is_active(&self, repo_id: i64) -> bool {
        self.active_tasks.contains_key(&repo_id)
    }

    /// Returns the number of currently active per-repo tasks.
    pub fn active_count(&self) -> usize {
        self.active_tasks.len()
    }

    /// Marks a per-repo task as complete, removing it from active tracking.
    ///
    /// Called by the worker loop when a task finishes (successfully or with error).
    pub fn mark_complete(&self, repo_id: i64) {
        self.active_tasks.remove(&repo_id);
    }

    /// Returns a clone of the cancellation token for the given repo ID.
    ///
    /// The worker loop uses this to pass into long-running operations
    /// (e.g., git2 progress callbacks) so they can be interrupted.
    pub fn get_cancellation_token(&self, repo_id: i64) -> Option<CancellationToken> {
        self.active_tasks
            .get(&repo_id)
            .map(|entry| entry.value().clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_enqueue_and_receive() {
        let (manager, mut rx) = TaskManager::new(4);

        manager.enqueue(Task::Clone(1)).await.unwrap();

        let task = rx.try_recv().unwrap();
        assert!(matches!(task, Task::Clone(1)));
    }

    #[tokio::test]
    async fn test_dedup_rejects_duplicate() {
        let (manager, _rx) = TaskManager::new(4);

        manager.enqueue(Task::Clone(1)).await.unwrap();

        let result = manager.enqueue(Task::Clone(1)).await;
        assert!(result.is_err());

        // Verify the error is UserVisible.
        match result.unwrap_err() {
            AppError::UserVisible(msg) => {
                assert!(msg.contains("already in progress"), "got: {}", msg);
            }
            other => panic!("Expected UserVisible error, got: {:?}", other),
        }
    }

    #[tokio::test]
    async fn test_dedup_rejects_duplicate_update_after_clone() {
        let (manager, _rx) = TaskManager::new(4);

        // Clone(1) occupies the slot for repo 1.
        manager.enqueue(Task::Clone(1)).await.unwrap();

        // Update(1) should also be rejected — same repo ID.
        let result = manager.enqueue(Task::Update(1)).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_dedup_allows_different_ids() {
        let (manager, _rx) = TaskManager::new(4);

        manager.enqueue(Task::Clone(1)).await.unwrap();
        manager.enqueue(Task::Clone(2)).await.unwrap();

        assert!(manager.is_active(1));
        assert!(manager.is_active(2));
        assert_eq!(manager.active_count(), 2);
    }

    #[tokio::test]
    async fn test_cancel_removes_and_cancels() {
        let (manager, _rx) = TaskManager::new(4);

        manager.enqueue(Task::Clone(42)).await.unwrap();
        assert!(manager.is_active(42));

        // Grab the token before cancel so we can check it was cancelled.
        let token = manager.get_cancellation_token(42).unwrap();
        assert!(!token.is_cancelled());

        manager.cancel(42).await;

        assert!(!manager.is_active(42));
        assert!(token.is_cancelled());
    }

    #[tokio::test]
    async fn test_cancel_noop_for_unknown_id() {
        let (manager, _rx) = TaskManager::new(4);

        // Should not panic or error.
        manager.cancel(999).await;
        assert_eq!(manager.active_count(), 0);
    }

    #[tokio::test]
    async fn test_cancel_all() {
        let (manager, _rx) = TaskManager::new(4);

        manager.enqueue(Task::Clone(1)).await.unwrap();
        manager.enqueue(Task::Clone(2)).await.unwrap();
        manager.enqueue(Task::Update(3)).await.unwrap();
        assert_eq!(manager.active_count(), 3);

        // Grab tokens to verify they get cancelled.
        let t1 = manager.get_cancellation_token(1).unwrap();
        let t2 = manager.get_cancellation_token(2).unwrap();
        let t3 = manager.get_cancellation_token(3).unwrap();

        manager.cancel_all().await;

        assert_eq!(manager.active_count(), 0);
        assert!(t1.is_cancelled());
        assert!(t2.is_cancelled());
        assert!(t3.is_cancelled());
    }

    #[tokio::test]
    async fn test_mark_complete() {
        let (manager, _rx) = TaskManager::new(4);

        manager.enqueue(Task::Clone(1)).await.unwrap();
        assert!(manager.is_active(1));

        manager.mark_complete(1);
        assert!(!manager.is_active(1));

        // Should be able to enqueue the same repo again after completion.
        manager.enqueue(Task::Clone(1)).await.unwrap();
        assert!(manager.is_active(1));
    }

    #[tokio::test]
    async fn test_update_all_no_dedup() {
        let (manager, mut rx) = TaskManager::new(4);

        // Enqueue a per-repo task.
        manager.enqueue(Task::Clone(1)).await.unwrap();

        // UpdateAll should succeed regardless of active tasks.
        manager
            .enqueue(Task::UpdateAll {
                include_archived: false,
            })
            .await
            .unwrap();

        manager
            .enqueue(Task::UpdateAll {
                include_archived: true,
            })
            .await
            .unwrap();

        // Verify all three came through the channel.
        let t1 = rx.try_recv().unwrap();
        let t2 = rx.try_recv().unwrap();
        let t3 = rx.try_recv().unwrap();

        assert!(matches!(t1, Task::Clone(1)));
        assert!(matches!(
            t2,
            Task::UpdateAll {
                include_archived: false
            }
        ));
        assert!(matches!(
            t3,
            Task::UpdateAll {
                include_archived: true
            }
        ));

        // UpdateAll does not appear in active_tasks.
        assert_eq!(manager.active_count(), 1);
    }

    #[tokio::test]
    async fn test_refresh_statuses_no_dedup() {
        let (manager, mut rx) = TaskManager::new(4);

        manager.enqueue(Task::RefreshStatuses).await.unwrap();
        manager.enqueue(Task::RefreshStatuses).await.unwrap();

        let t1 = rx.try_recv().unwrap();
        let t2 = rx.try_recv().unwrap();

        assert!(matches!(t1, Task::RefreshStatuses));
        assert!(matches!(t2, Task::RefreshStatuses));
        assert_eq!(manager.active_count(), 0);
    }

    #[tokio::test]
    async fn test_stop_goes_through_channel() {
        let (manager, mut rx) = TaskManager::new(4);

        manager.enqueue(Task::Stop).await.unwrap();

        let task = rx.try_recv().unwrap();
        assert!(matches!(task, Task::Stop));
        assert_eq!(manager.active_count(), 0);
    }

    #[tokio::test]
    async fn test_get_cancellation_token() {
        let (manager, _rx) = TaskManager::new(4);

        manager.enqueue(Task::Clone(1)).await.unwrap();

        // Token exists for active task.
        let token = manager.get_cancellation_token(1);
        assert!(token.is_some());

        // Token does not exist for unknown ID.
        let token = manager.get_cancellation_token(999);
        assert!(token.is_none());
    }

    #[tokio::test]
    async fn test_semaphore_is_accessible() {
        let (manager, _rx) = TaskManager::new(8);

        // Verify the semaphore has the expected number of permits.
        // Acquiring 8 permits should succeed; the 9th should not be immediately available.
        let mut permits = Vec::new();
        for _ in 0..8 {
            permits.push(manager.semaphore.acquire().await.unwrap());
        }

        // The 9th acquire should not be immediately available.
        let try_ninth = manager.semaphore.try_acquire();
        assert!(try_ninth.is_err());

        // Drop one permit, now the 9th should succeed.
        drop(permits.pop());
        let ninth = manager.semaphore.try_acquire();
        assert!(ninth.is_ok());
    }

    #[tokio::test]
    async fn test_max_concurrent_clamped_min() {
        // 0 should be clamped to 1.
        let (manager, _rx) = TaskManager::new(0);

        let permit = manager.semaphore.try_acquire();
        assert!(permit.is_ok());

        // Second permit should fail (only 1 allowed).
        let second = manager.semaphore.try_acquire();
        assert!(second.is_err());
    }

    #[tokio::test]
    async fn test_max_concurrent_clamped_max() {
        // 100 should be clamped to 16.
        let (manager, _rx) = TaskManager::new(100);

        let mut permits = Vec::new();
        for _ in 0..16 {
            permits.push(manager.semaphore.acquire().await.unwrap());
        }

        // 17th should fail.
        let try_17 = manager.semaphore.try_acquire();
        assert!(try_17.is_err());
    }
}
