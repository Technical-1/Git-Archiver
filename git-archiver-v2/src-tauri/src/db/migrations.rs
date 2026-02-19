use rusqlite::Connection;

use crate::error::AppError;

const MIGRATION_001: &str = include_str!("../../migrations/001_initial.sql");

pub fn run_migrations(conn: &Connection) -> Result<(), AppError> {
    // Create schema_version table if not exists
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);",
    )?;

    // Enable foreign keys before any migration DML that may reference them
    conn.execute_batch("PRAGMA foreign_keys = ON;")?;

    // Enable WAL mode for concurrent reads
    conn.pragma_update(None, "journal_mode", "WAL")?;

    let current_version: i64 = conn
        .query_row(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version",
            [],
            |row| row.get(0),
        )?;

    if current_version < 1 {
        conn.execute_batch(MIGRATION_001)?;
        conn.execute("INSERT INTO schema_version (version) VALUES (1)", [])?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;

    fn setup_db() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        run_migrations(&conn).unwrap();
        conn
    }

    #[test]
    fn test_run_migrations_creates_tables() {
        let conn = setup_db();

        // All 5 tables should exist: schema_version, repositories, archives, file_hashes, settings
        let tables: Vec<String> = conn
            .prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            .unwrap()
            .query_map([], |row| row.get(0))
            .unwrap()
            .filter_map(|r| r.ok())
            .collect();

        assert!(tables.contains(&"schema_version".to_string()));
        assert!(tables.contains(&"repositories".to_string()));
        assert!(tables.contains(&"archives".to_string()));
        assert!(tables.contains(&"file_hashes".to_string()));
        assert!(tables.contains(&"settings".to_string()));
    }

    #[test]
    fn test_run_migrations_idempotent() {
        let conn = Connection::open_in_memory().unwrap();
        run_migrations(&conn).unwrap();
        // Running again should not error
        run_migrations(&conn).unwrap();
    }

    #[test]
    fn test_schema_version_set() {
        let conn = setup_db();

        let version: i64 = conn
            .query_row(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version",
                [],
                |row| row.get(0),
            )
            .unwrap();

        assert_eq!(version, 1);
    }

    #[test]
    fn test_foreign_keys_enabled() {
        let conn = setup_db();

        let fk_enabled: bool = conn
            .query_row("PRAGMA foreign_keys", [], |row| row.get(0))
            .unwrap();

        assert!(fk_enabled);
    }
}
