use rusqlite::{params, Connection};

use crate::error::AppError;
use crate::models::AppSettings;

/// Allowlist of valid setting keys that may be stored.
const ALLOWED_SETTING_KEYS: &[&str] = &[
    "data_dir",
    "archive_format",
    "max_concurrent_tasks",
    "auto_check_interval_minutes",
];

/// Get a single setting value by key.
pub fn get_setting(conn: &Connection, key: &str) -> Result<Option<String>, AppError> {
    let mut stmt = conn.prepare("SELECT value FROM settings WHERE key = ?1")?;
    let mut rows = stmt.query_map(params![key], |row| row.get::<_, String>(0))?;
    match rows.next() {
        Some(r) => Ok(Some(r?)),
        None => Ok(None),
    }
}

/// Set a setting value (insert or update).
/// Only keys in `ALLOWED_SETTING_KEYS` are accepted.
pub fn set_setting(conn: &Connection, key: &str, value: &str) -> Result<(), AppError> {
    if !ALLOWED_SETTING_KEYS.contains(&key) {
        return Err(AppError::UserVisible(format!(
            "Invalid setting key: '{}'",
            key
        )));
    }
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?1, ?2)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        params![key, value],
    )?;
    Ok(())
}

/// Load application settings from the database, using defaults for missing keys.
pub fn get_app_settings(conn: &Connection) -> Result<AppSettings, AppError> {
    let defaults = AppSettings::default();

    let data_dir = get_setting(conn, "data_dir")?
        .unwrap_or(defaults.data_dir);

    let archive_format = get_setting(conn, "archive_format")?
        .unwrap_or(defaults.archive_format);

    let max_concurrent_tasks = get_setting(conn, "max_concurrent_tasks")?
        .and_then(|v| v.parse::<u32>().ok())
        .unwrap_or(defaults.max_concurrent_tasks);

    let auto_check_interval_minutes = get_setting(conn, "auto_check_interval_minutes")?
        .and_then(|v| v.parse::<u32>().ok());

    Ok(AppSettings {
        data_dir,
        archive_format,
        max_concurrent_tasks,
        auto_check_interval_minutes,
    })
}

/// Helper to set a setting within a transaction context using `execute` directly.
fn set_setting_in_tx(conn: &Connection, key: &str, value: &str) -> Result<(), AppError> {
    if !ALLOWED_SETTING_KEYS.contains(&key) {
        return Err(AppError::UserVisible(format!(
            "Invalid setting key: '{}'",
            key
        )));
    }
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?1, ?2)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        params![key, value],
    )?;
    Ok(())
}

/// Save application settings to the database as individual key-value pairs.
/// All writes are wrapped in a single transaction for atomicity.
pub fn save_app_settings(conn: &mut Connection, settings: &AppSettings) -> Result<(), AppError> {
    let tx = conn.transaction()?;

    set_setting_in_tx(&tx, "data_dir", &settings.data_dir)?;
    set_setting_in_tx(&tx, "archive_format", &settings.archive_format)?;
    set_setting_in_tx(
        &tx,
        "max_concurrent_tasks",
        &settings.max_concurrent_tasks.to_string(),
    )?;
    match &settings.auto_check_interval_minutes {
        Some(interval) => set_setting_in_tx(&tx, "auto_check_interval_minutes", &interval.to_string())?,
        None => {
            // Remove the key if the value is None
            tx.execute(
                "DELETE FROM settings WHERE key = 'auto_check_interval_minutes'",
                [],
            )?;
        }
    }

    tx.commit()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::migrations::run_migrations;

    fn setup_db() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        run_migrations(&conn).unwrap();
        conn
    }

    #[test]
    fn test_get_missing_returns_none() {
        let conn = setup_db();
        let result = get_setting(&conn, "nonexistent").unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_set_and_get() {
        let conn = setup_db();
        set_setting(&conn, "data_dir", "/my/data").unwrap();
        let result = get_setting(&conn, "data_dir").unwrap();
        assert_eq!(result, Some("/my/data".to_string()));
    }

    #[test]
    fn test_set_overwrites() {
        let conn = setup_db();
        set_setting(&conn, "data_dir", "/first").unwrap();
        set_setting(&conn, "data_dir", "/second").unwrap();
        let result = get_setting(&conn, "data_dir").unwrap();
        assert_eq!(result, Some("/second".to_string()));
    }

    #[test]
    fn test_set_disallowed_key_fails() {
        let conn = setup_db();
        let result = set_setting(&conn, "evil_key", "value");
        assert!(result.is_err());
    }

    #[test]
    fn test_app_settings_defaults() {
        let conn = setup_db();
        let settings = get_app_settings(&conn).unwrap();
        let defaults = AppSettings::default();

        assert_eq!(settings.data_dir, defaults.data_dir);
        assert_eq!(settings.archive_format, defaults.archive_format);
        assert_eq!(settings.max_concurrent_tasks, defaults.max_concurrent_tasks);
        assert_eq!(settings.auto_check_interval_minutes, defaults.auto_check_interval_minutes);
    }

    #[test]
    fn test_save_and_load_app_settings() {
        let mut conn = setup_db();

        let settings = AppSettings {
            data_dir: "/custom/data".to_string(),
            archive_format: "tar.gz".to_string(),
            max_concurrent_tasks: 8,
            auto_check_interval_minutes: Some(30),
        };

        save_app_settings(&mut conn, &settings).unwrap();
        let loaded = get_app_settings(&conn).unwrap();

        assert_eq!(loaded.data_dir, "/custom/data");
        assert_eq!(loaded.archive_format, "tar.gz");
        assert_eq!(loaded.max_concurrent_tasks, 8);
        assert_eq!(loaded.auto_check_interval_minutes, Some(30));

        // Now save with None interval and verify it is cleared
        let settings2 = AppSettings {
            auto_check_interval_minutes: None,
            ..settings
        };
        save_app_settings(&mut conn, &settings2).unwrap();
        let loaded2 = get_app_settings(&conn).unwrap();
        assert_eq!(loaded2.auto_check_interval_minutes, None);
    }
}
