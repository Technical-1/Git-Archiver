use std::sync::Arc;

use chrono::{DateTime, Local, NaiveDateTime, NaiveTime, TimeZone};
use tauri::{AppHandle, Manager};
use tokio::sync::watch;

use crate::core::task_manager::{Task, TaskManager};
use crate::state::AppState;

/// Resolve a naive local datetime to a timezone-aware instant, picking a
/// sensible answer when DST makes the local time ambiguous or nonexistent.
///
/// - **Ambiguous (fall-back day):** the wall clock reads the same time twice;
///   use the earlier of the two instants so a 1:30 sync fires once on the
///   first 1:30 and won't double-fire after the rewind.
/// - **None (spring-forward gap):** the wall clock skips a time (e.g. 2:30
///   doesn't exist). Shift the naive time forward by one hour so it lands
///   in the post-gap zone, then resolve from there.
fn local_naive_to_instant(naive: NaiveDateTime, fallback: DateTime<Local>) -> DateTime<Local> {
    match Local.from_local_datetime(&naive) {
        chrono::LocalResult::Single(dt) => dt,
        chrono::LocalResult::Ambiguous(earlier, _later) => earlier,
        chrono::LocalResult::None => {
            let shifted = naive + chrono::Duration::hours(1);
            Local
                .from_local_datetime(&shifted)
                .single()
                .unwrap_or(fallback)
        }
    }
}

/// Compute the duration from now until the next occurrence of `target_time`
/// in the local timezone, DST-aware.
fn duration_until(target_time: NaiveTime) -> std::time::Duration {
    let now = Local::now();

    let today_naive = now.date_naive().and_time(target_time);
    let today_target = local_naive_to_instant(today_naive, now + chrono::Duration::hours(1));

    let next = if now < today_target {
        today_target
    } else {
        let tomorrow_naive = (now.date_naive() + chrono::Duration::days(1)).and_time(target_time);
        local_naive_to_instant(tomorrow_naive, now + chrono::Duration::days(1))
    };

    (next - now)
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

                        // Brief cooldown to avoid re-triggering within the same
                        // minute, but also watch for sync_time changes during the
                        // cooldown so a user edit doesn't have to wait 61s+1 day
                        // to take effect.
                        tokio::select! {
                            _ = tokio::time::sleep(std::time::Duration::from_secs(61)) => {}
                            _ = sync_time_rx.changed() => {
                                log::info!("Sync time changed during cooldown, re-scheduling");
                            }
                        }
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
