use std::collections::HashMap;

use chrono::Utc;
use rusqlite::{params, Connection};

use crate::error::AppError;

/// Insert or update a file hash for a repo. Updates md5_hash and last_seen on conflict.
pub fn upsert_file_hash(
    conn: &Connection,
    repo_id: i64,
    file_path: &str,
    md5_hash: &str,
) -> Result<(), AppError> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO file_hashes (repo_id, file_path, md5_hash, last_seen) VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT(repo_id, file_path) DO UPDATE SET md5_hash = excluded.md5_hash, last_seen = excluded.last_seen",
        params![repo_id, file_path, md5_hash, now],
    )?;
    Ok(())
}

/// Get all file hashes for a repository as a map from file_path to md5_hash.
pub fn get_file_hashes(
    conn: &Connection,
    repo_id: i64,
) -> Result<HashMap<String, String>, AppError> {
    let mut stmt =
        conn.prepare("SELECT file_path, md5_hash FROM file_hashes WHERE repo_id = ?1")?;
    let rows = stmt.query_map(params![repo_id], |row| {
        let path: String = row.get(0)?;
        let hash: String = row.get(1)?;
        Ok((path, hash))
    })?;

    let mut map = HashMap::new();
    for row in rows {
        let (path, hash) = row?;
        map.insert(path, hash);
    }
    Ok(map)
}

/// Delete all file hashes for a repository.
#[allow(dead_code)]
pub fn clear_file_hashes(conn: &Connection, repo_id: i64) -> Result<(), AppError> {
    conn.execute(
        "DELETE FROM file_hashes WHERE repo_id = ?1",
        params![repo_id],
    )?;
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
        let repo =
            repos::insert_repo(conn, "octocat", "repo", "https://github.com/octocat/repo").unwrap();
        repo.id.unwrap()
    }

    #[test]
    fn test_upsert_file_hash() {
        let conn = setup_db();
        let repo_id = insert_test_repo(&conn);

        // Insert
        upsert_file_hash(&conn, repo_id, "src/main.rs", "abc123").unwrap();
        let hashes = get_file_hashes(&conn, repo_id).unwrap();
        assert_eq!(hashes.get("src/main.rs"), Some(&"abc123".to_string()));

        // Update (upsert)
        upsert_file_hash(&conn, repo_id, "src/main.rs", "def456").unwrap();
        let hashes = get_file_hashes(&conn, repo_id).unwrap();
        assert_eq!(hashes.get("src/main.rs"), Some(&"def456".to_string()));
    }

    #[test]
    fn test_get_hashes_for_repo() {
        let conn = setup_db();
        let repo_id = insert_test_repo(&conn);

        upsert_file_hash(&conn, repo_id, "file1.txt", "hash1").unwrap();
        upsert_file_hash(&conn, repo_id, "file2.txt", "hash2").unwrap();

        let hashes = get_file_hashes(&conn, repo_id).unwrap();
        assert_eq!(hashes.len(), 2);
        assert_eq!(hashes.get("file1.txt"), Some(&"hash1".to_string()));
        assert_eq!(hashes.get("file2.txt"), Some(&"hash2".to_string()));

        // Different repo should return empty
        let repo2 =
            repos::insert_repo(&conn, "other", "repo2", "https://github.com/other/repo2").unwrap();
        let hashes2 = get_file_hashes(&conn, repo2.id.unwrap()).unwrap();
        assert!(hashes2.is_empty());
    }

    #[test]
    fn test_clear_file_hashes_direct() {
        let conn = setup_db();
        let repo_id = insert_test_repo(&conn);

        upsert_file_hash(&conn, repo_id, "file1.txt", "hash1").unwrap();
        upsert_file_hash(&conn, repo_id, "file2.txt", "hash2").unwrap();

        let hashes = get_file_hashes(&conn, repo_id).unwrap();
        assert_eq!(hashes.len(), 2);

        // Clear hashes without deleting the repo
        clear_file_hashes(&conn, repo_id).unwrap();

        let hashes_after = get_file_hashes(&conn, repo_id).unwrap();
        assert!(hashes_after.is_empty());

        // The repo should still exist
        let repo = repos::get_repo_by_id(&conn, repo_id).unwrap();
        assert!(repo.is_some());
    }

    #[test]
    fn test_clear_hashes_on_repo_delete() {
        let conn = setup_db();
        let repo_id = insert_test_repo(&conn);

        upsert_file_hash(&conn, repo_id, "file1.txt", "hash1").unwrap();
        upsert_file_hash(&conn, repo_id, "file2.txt", "hash2").unwrap();

        // Delete the repo -- cascades to file_hashes
        repos::delete_repo(&conn, repo_id).unwrap();

        let hashes = get_file_hashes(&conn, repo_id).unwrap();
        assert!(hashes.is_empty());
    }
}
