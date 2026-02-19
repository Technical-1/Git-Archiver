use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, Row};

use crate::error::AppError;
use crate::models::Archive;

/// Map a rusqlite Row to an Archive struct.
///
/// Expected column order:
///   0: id, 1: repo_id, 2: file_path, 3: size_bytes, 4: file_count, 5: created_at
fn row_to_archive(row: &Row) -> Result<Archive, rusqlite::Error> {
    let id: i64 = row.get(0)?;
    let repo_id: i64 = row.get(1)?;
    let file_path: String = row.get(2)?;
    let size_bytes: i64 = row.get(3)?;
    let file_count: i64 = row.get(4)?;
    let created_at_str: String = row.get(5)?;

    let created_at = created_at_str
        .parse::<DateTime<Utc>>()
        .unwrap_or_else(|_| Utc::now());

    Ok(Archive {
        id: Some(id),
        repo_id,
        file_path,
        file_size: size_bytes as u64,
        file_count: file_count as u32,
        commit_hash: None,
        created_at,
    })
}

const SELECT_COLS: &str = "id, repo_id, file_path, size_bytes, file_count, created_at";

/// Insert a new archive record.
pub fn insert_archive(
    conn: &Connection,
    repo_id: i64,
    filename: &str,
    file_path: &str,
    size_bytes: u64,
    file_count: u32,
    is_incremental: bool,
) -> Result<Archive, AppError> {
    conn.execute(
        "INSERT INTO archives (repo_id, filename, file_path, size_bytes, file_count, is_incremental) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![repo_id, filename, file_path, size_bytes as i64, file_count as i64, is_incremental],
    )?;

    let id = conn.last_insert_rowid();
    get_archive_by_id(conn, id)?
        .ok_or_else(|| AppError::Custom("Failed to retrieve inserted archive".to_string()))
}

/// List all archives for a given repository, ordered by creation time descending.
pub fn list_archives(conn: &Connection, repo_id: i64) -> Result<Vec<Archive>, AppError> {
    let sql = format!(
        "SELECT {} FROM archives WHERE repo_id = ?1 ORDER BY created_at DESC",
        SELECT_COLS
    );
    let mut stmt = conn.prepare(&sql)?;
    let archives = stmt
        .query_map(params![repo_id], row_to_archive)?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(archives)
}

/// Get a single archive by its primary key.
pub fn get_archive_by_id(conn: &Connection, id: i64) -> Result<Option<Archive>, AppError> {
    let sql = format!("SELECT {} FROM archives WHERE id = ?1", SELECT_COLS);
    let mut stmt = conn.prepare(&sql)?;
    let mut rows = stmt.query_map(params![id], row_to_archive)?;
    match rows.next() {
        Some(r) => Ok(Some(r?)),
        None => Ok(None),
    }
}

/// Delete an archive by id.
pub fn delete_archive(conn: &Connection, id: i64) -> Result<(), AppError> {
    conn.execute("DELETE FROM archives WHERE id = ?1", params![id])?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::migrations::run_migrations;
    use crate::db::repos;

    fn setup_db() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        run_migrations(&conn).unwrap();
        conn
    }

    fn insert_test_repo(conn: &Connection) -> i64 {
        let repo = repos::insert_repo(conn, "octocat", "repo", "https://github.com/octocat/repo").unwrap();
        repo.id.unwrap()
    }

    #[test]
    fn test_insert_archive() {
        let conn = setup_db();
        let repo_id = insert_test_repo(&conn);

        let archive = insert_archive(
            &conn,
            repo_id,
            "repo-2024-01-01.tar.xz",
            "/data/repo/versions/repo-2024-01-01.tar.xz",
            1024,
            42,
            false,
        )
        .unwrap();

        assert!(archive.id.is_some());
        assert_eq!(archive.repo_id, repo_id);
        assert_eq!(archive.file_path, "/data/repo/versions/repo-2024-01-01.tar.xz");
        assert_eq!(archive.file_size, 1024);
        assert_eq!(archive.file_count, 42);
    }

    #[test]
    fn test_list_archives_for_repo() {
        let conn = setup_db();
        let repo_id1 = insert_test_repo(&conn);
        let repo2 = repos::insert_repo(&conn, "other", "repo2", "https://github.com/other/repo2").unwrap();
        let repo_id2 = repo2.id.unwrap();

        // Insert archives for both repos
        insert_archive(&conn, repo_id1, "a1.tar.xz", "/path/a1.tar.xz", 100, 10, false).unwrap();
        insert_archive(&conn, repo_id1, "a2.tar.xz", "/path/a2.tar.xz", 200, 20, true).unwrap();
        insert_archive(&conn, repo_id2, "b1.tar.xz", "/path/b1.tar.xz", 300, 30, false).unwrap();

        // Only repo1's archives
        let archives = list_archives(&conn, repo_id1).unwrap();
        assert_eq!(archives.len(), 2);

        // Only repo2's archives
        let archives2 = list_archives(&conn, repo_id2).unwrap();
        assert_eq!(archives2.len(), 1);
        assert_eq!(archives2[0].file_size, 300);
    }

    #[test]
    fn test_delete_archive() {
        let conn = setup_db();
        let repo_id = insert_test_repo(&conn);

        let archive = insert_archive(&conn, repo_id, "a.tar.xz", "/path/a.tar.xz", 100, 10, false).unwrap();
        let archive_id = archive.id.unwrap();

        delete_archive(&conn, archive_id).unwrap();
        let result = get_archive_by_id(&conn, archive_id).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_cascade_delete() {
        let conn = setup_db();
        let repo_id = insert_test_repo(&conn);

        let archive = insert_archive(&conn, repo_id, "a.tar.xz", "/path/a.tar.xz", 100, 10, false).unwrap();
        let archive_id = archive.id.unwrap();

        // Delete the repo -- should cascade to archives
        repos::delete_repo(&conn, repo_id).unwrap();

        let result = get_archive_by_id(&conn, archive_id).unwrap();
        assert!(result.is_none());
    }
}
