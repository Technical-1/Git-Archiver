mod commands;
mod core;
mod db;
mod error;
mod models;
mod state;

use std::sync::Arc;

use rusqlite::Connection;
use tauri::Manager;
use tokio::sync::Mutex;

use crate::core::github_api::GitHubClient;
use crate::core::task_manager::TaskManager;
use crate::core::worker::worker_loop;
use crate::db::migrations::run_migrations;
use crate::db::settings::get_app_settings;
use crate::state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // --- Initialize database ---
            let app_data_dir = app.path().app_data_dir().map_err(|e| {
                Box::new(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    format!("Failed to resolve app data directory: {}", e),
                ))
            })?;
            std::fs::create_dir_all(&app_data_dir).map_err(|e| {
                Box::new(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    format!("Failed to create app data directory: {}", e),
                ))
            })?;

            let db_path = app_data_dir.join("git-archiver.db");
            let conn = Connection::open(&db_path).map_err(|e| {
                Box::new(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    format!("Failed to open database: {}", e),
                ))
            })?;

            run_migrations(&conn).map_err(|e| {
                Box::new(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    format!("Failed to run database migrations: {}", e),
                ))
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

            let app_state = AppState {
                db: db.clone(),
                task_manager: task_manager.clone(),
                github_client: github_client.clone(),
            };

            app.manage(app_state);

            // --- Spawn the worker loop ---
            let app_handle = app.handle().clone();
            tokio::spawn(worker_loop(
                rx,
                app_handle,
                db,
                github_client,
                task_manager,
            ));

            Ok(())
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
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
