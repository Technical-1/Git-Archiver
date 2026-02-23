mod commands;
pub mod core;
pub mod db;
pub mod error;
pub mod models;
mod state;
mod tray;

use std::sync::Arc;

use chrono::NaiveTime;
use rusqlite::Connection;
use tauri::{Manager, RunEvent, WindowEvent};
use tokio::sync::{watch, Mutex};

use crate::core::github_api::GitHubClient;
use crate::core::scheduler::scheduler_loop;
use crate::core::task_manager::TaskManager;
use crate::core::worker::worker_loop;
use crate::db::migrations::run_migrations;
use crate::db::settings::get_app_settings;
use crate::state::AppState;

/// Parse a "HH:MM" string into a `NaiveTime`.
fn parse_sync_time(s: &str) -> Option<NaiveTime> {
    NaiveTime::parse_from_str(s, "%H:%M").ok()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            // --- Initialize database ---
            let app_data_dir = app.path().app_data_dir().map_err(|e| {
                Box::new(std::io::Error::other(format!(
                    "Failed to resolve app data directory: {}",
                    e
                )))
            })?;
            std::fs::create_dir_all(&app_data_dir).map_err(|e| {
                Box::new(std::io::Error::other(format!(
                    "Failed to create app data directory: {}",
                    e
                )))
            })?;

            let db_path = app_data_dir.join("git-archiver.db");
            let conn = Connection::open(&db_path).map_err(|e| {
                Box::new(std::io::Error::other(format!(
                    "Failed to open database: {}",
                    e
                )))
            })?;

            run_migrations(&conn).map_err(|e| {
                Box::new(std::io::Error::other(format!(
                    "Failed to run database migrations: {}",
                    e
                )))
            })?;

            // --- Load settings ---
            let settings = get_app_settings(&conn).unwrap_or_default();
            let max_concurrent = settings.max_concurrent_tasks;

            // If data_dir is relative, resolve it relative to the app data dir
            let data_dir = if std::path::Path::new(&settings.data_dir).is_relative() {
                app_data_dir.join(&settings.data_dir)
            } else {
                std::path::PathBuf::from(&settings.data_dir)
            };
            std::fs::create_dir_all(&data_dir).ok();

            // --- Load GitHub token from keychain ---
            let token = keyring::Entry::new("git-archiver", "github-token")
                .ok()
                .and_then(|entry| entry.get_password().ok());

            // --- Initialize components ---
            let github_client = Arc::new(GitHubClient::new(token));
            let (task_manager, rx) = TaskManager::new(max_concurrent);
            let db = Arc::new(Mutex::new(conn));

            // --- Scheduler watch channel ---
            let initial_sync_time = settings.sync_time.as_deref().and_then(parse_sync_time);
            let (sync_time_tx, sync_time_rx) = watch::channel(initial_sync_time);

            let app_state = AppState {
                db: db.clone(),
                task_manager: task_manager.clone(),
                github_client: github_client.clone(),
                last_sync_time: Arc::new(std::sync::Mutex::new(None)),
                sync_time_tx,
            };

            app.manage(app_state);

            // --- Set up system tray ---
            let app_handle = app.handle().clone();
            tray::setup_tray(&app_handle).map_err(|e| {
                Box::new(std::io::Error::other(format!(
                    "Failed to set up system tray: {}",
                    e
                )))
            })?;

            // --- Spawn the worker loop ---
            let worker_app_handle = app_handle.clone();
            tauri::async_runtime::spawn(worker_loop(
                rx,
                worker_app_handle,
                db,
                github_client,
                task_manager.clone(),
            ));

            // --- Spawn the scheduler ---
            tauri::async_runtime::spawn(scheduler_loop(sync_time_rx, task_manager, app_handle));

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Hide the window instead of closing it
                api.prevent_close();
                let _ = window.hide();

                // On macOS, hide from the dock when the window is hidden
                #[cfg(target_os = "macos")]
                let _ = window
                    .app_handle()
                    .set_activation_policy(tauri::ActivationPolicy::Accessory);
            }
        })
        .invoke_handler(tauri::generate_handler![
            // Repository commands
            commands::repos::add_repo,
            commands::repos::list_repos,
            commands::repos::delete_repo,
            commands::repos::import_from_file,
            // Task commands
            commands::tasks::clone_repo,
            commands::tasks::update_repo,
            commands::tasks::update_all,
            commands::tasks::stop_all_tasks,
            // Archive commands
            commands::archives::list_archives,
            commands::archives::extract_archive,
            commands::archives::delete_archive,
            // Settings commands
            commands::settings::get_settings,
            commands::settings::save_settings,
            commands::settings::check_rate_limit,
            // Migration commands
            commands::migrate::migrate_from_json,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_app_handle, event| {
        // Prevent the app from exiting when all windows are closed
        if let RunEvent::ExitRequested { api, .. } = event {
            api.prevent_exit();
        }
    });
}
