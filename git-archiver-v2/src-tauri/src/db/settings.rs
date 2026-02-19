use rusqlite::{params, Connection};

use crate::error::AppError;
use crate::models::AppSettings;

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
pub fn set_setting(conn: &Connection, key: &str, value: &str) -> Result<(), AppError> {
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

/// Save application settings to the database as individual key-value pairs.
pub fn save_app_settings(conn: &Connection, settings: &AppSettings) -> Result<(), AppError> {
    set_setting(conn, "data_dir", &settings.data_dir)?;
    set_setting(conn, "archive_format", &settings.archive_format)?;
    set_setting(
        conn,
        "max_concurrent_tasks",
        &settings.max_concurrent_tasks.to_string(),
    )?;
    match &settings.auto_check_interval_minutes {
        Some(interval) => set_setting(conn, "auto_check_interval_minutes", &interval.to_string())?,
        None => {
            // Remove the key if the value is None
            conn.execute(
                "DELETE FROM settings WHERE key = 'auto_check_interval_minutes'",
                [],
            )?;
        }
    }
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
        set_setting(&conn, "theme", "dark").unwrap();
        let result = get_setting(&conn, "theme").unwrap();
        assert_eq!(result, Some("dark".to_string()));
    }

    #[test]
    fn test_set_overwrites() {
        let conn = setup_db();
        set_setting(&conn, "theme", "dark").unwrap();
        set_setting(&conn, "theme", "light").unwrap();
        let result = get_setting(&conn, "theme").unwrap();
        assert_eq!(result, Some("light".to_string()));
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
        let conn = setup_db();

        let settings = AppSettings {
            data_dir: "/custom/data".to_string(),
            archive_format: "tar.gz".to_string(),
            max_concurrent_tasks: 8,
            auto_check_interval_minutes: Some(30),
        };

        save_app_settings(&conn, &settings).unwrap();
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
        save_app_settings(&conn, &settings2).unwrap();
        let loaded2 = get_app_settings(&conn).unwrap();
        assert_eq!(loaded2.auto_check_interval_minutes, None);
    }
}
