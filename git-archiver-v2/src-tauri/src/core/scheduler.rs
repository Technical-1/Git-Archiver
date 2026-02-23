use std::sync::Arc;

use chrono::{Local, NaiveTime};
use tauri::{AppHandle, Manager};
use tokio::sync::watch;

use crate::core::task_manager::{Task, TaskManager};
use crate::state::AppState;

/// Compute the duration from now until the next occurrence of `target_time` in local timezone.
fn duration_until(target_time: NaiveTime) -> std::time::Duration {
    let now = Local::now();
    let today_target = now.date_naive().and_time(target_time);

    let next = if now.naive_local() < today_target {
        today_target
    } else {
        // Target time already passed today, schedule for tomorrow
        today_target + chrono::Duration::days(1)
    };

    let duration = next - now.naive_local();
    duration
        .to_std()
        .unwrap_or(std::time::Duration::from_secs(60))
}

/// Daily scheduler that triggers update-all at a configurable time.
///
/// Uses `tokio::select!` to either sleep until the target time or wake
/// immediately when the sync_time setting changes (via watch channel).
pub async fn scheduler_loop(
    mut sync_time_rx: watch::Receiver<Option<NaiveTime>>,
    task_manager: Arc<TaskManager>,
    app_handle: AppHandle,
) {
    loop {
        let target_time = *sync_time_rx.borrow();

        match target_time {
            Some(time) => {
                let sleep_duration = duration_until(time);
                log::info!(
                    "Scheduler: next sync at {:?}, sleeping for {:.0}s",
                    time,
                    sleep_duration.as_secs_f64()
                );

                tokio::select! {
                    _ = tokio::time::sleep(sleep_duration) => {
                        log::info!("Scheduled daily sync triggered");

                        // Enqueue update-all
                        if let Err(e) = task_manager.enqueue(Task::UpdateAll { include_archived: false }).await {
                            log::error!("Failed to enqueue scheduled sync: {}", e);
                        }

                        // Update last sync time in AppState
                        if let Some(state) = app_handle.try_state::<AppState>() {
                            if let Ok(mut sync_time) = state.last_sync_time.lock() {
                                *sync_time = Some(chrono::Utc::now());
                            }
                        }

                        // Update tray menu text
                        crate::tray::update_last_sync_text(
                            &app_handle,
                            &format!("Last sync: {}", Local::now().format("%b %d, %I:%M %p")),
                        );

                        // Send notification
                        send_sync_notification(&app_handle);

                        // Brief cooldown to avoid re-triggering within the same minute
                        tokio::time::sleep(std::time::Duration::from_secs(61)).await;
                    }
                    _ = sync_time_rx.changed() => {
                        log::info!("Sync time setting changed, re-scheduling");
                        continue;
                    }
                }
            }
            None => {
                // Sync disabled — wait for settings to change
                log::info!("Scheduler: sync disabled, waiting for settings change");
                if sync_time_rx.changed().await.is_err() {
                    break; // Channel closed, shutting down
                }
            }
        }
    }
    log::info!("Scheduler loop exited");
}

/// Send a system notification after a scheduled sync completes.
fn send_sync_notification(app_handle: &AppHandle) {
    use tauri_plugin_notification::NotificationExt;

    if let Err(e) = app_handle
        .notification()
        .builder()
        .title("Git Archiver")
        .body("Scheduled sync complete — all repos checked for updates.")
        .show()
    {
        log::warn!("Failed to send sync notification: {}", e);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_duration_until_future_time() {
        // If we pick a time 1 hour from now, duration should be ~3600s
        let now = Local::now();
        let future = (now + chrono::Duration::hours(1)).time();
        let duration = duration_until(future);
        // Should be roughly 3600 seconds (allow 5s tolerance)
        assert!(duration.as_secs() >= 3595 && duration.as_secs() <= 3605);
    }

    #[test]
    fn test_duration_until_past_time_wraps_to_tomorrow() {
        // If we pick a time 1 hour ago, duration should be ~23h
        let now = Local::now();
        let past = (now - chrono::Duration::hours(1)).time();
        let duration = duration_until(past);
        // Should be roughly 23 hours (82800s)
        assert!(duration.as_secs() >= 82700 && duration.as_secs() <= 82900);
    }
}
