use std::collections::HashMap;

use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, Row};

use crate::error::AppError;
use crate::models::{RepoStatus, Repository};

/// Parse a RepoStatus from its database string representation.
fn parse_status(s: &str) -> Result<RepoStatus, AppError> {
    match s {
        "pending" => Ok(RepoStatus::Pending),
        "active" => Ok(RepoStatus::Active),
        "archived" => Ok(RepoStatus::Archived),
        "deleted" => Ok(RepoStatus::Deleted),
        "error" => Ok(RepoStatus::Error),
        other => Err(AppError::Custom(format!("Unknown repo status: {}", other))),
    }
}

/// Parse an optional ISO 8601 datetime string into Option<DateTime<Utc>>.
fn parse_optional_datetime(s: Option<String>) -> Option<DateTime<Utc>> {
    s.and_then(|v| v.parse::<DateTime<Utc>>().ok())
}

/// Map a rusqlite Row to a Repository struct.
///
/// Expected column order:
///   0: id, 1: owner, 2: name, 3: url, 4: description, 5: status,
///   6: is_private, 7: local_path, 8: last_checked,
///   9: last_updated (mapped to last_archived), 10: error_message, 11: created_at
fn row_to_repo(row: &Row) -> Result<Repository, rusqlite::Error> {
    let id: i64 = row.get(0)?;
    let owner: String = row.get(1)?;
    let name: String = row.get(2)?;
    let url: String = row.get(3)?;
    let description: Option<String> = row.get(4)?;
    let status_str: String = row.get(5)?;
    let is_private: bool = row.get(6)?;
    let local_path: Option<String> = row.get(7)?;
    let last_checked_str: Option<String> = row.get(8)?;
    let last_updated_str: Option<String> = row.get(9)?;
    let error_message: Option<String> = row.get(10)?;
    let created_at_str: String = row.get(11)?;

    let status = match parse_status(&status_str) {
        Ok(s) => s,
        Err(_) => {
            log::warn!(
                "Unknown repo status '{}' for repo id={}, falling back to Error",
                status_str,
                id
            );
            RepoStatus::Error
        }
    };
    let last_checked = parse_optional_datetime(last_checked_str);
    let last_archived = parse_optional_datetime(last_updated_str);
    let created_at = match created_at_str.parse::<DateTime<Utc>>() {
        Ok(dt) => dt,
        Err(_) => {
            log::warn!(
                "Failed to parse created_at '{}' for repo id={}, falling back to Utc::now()",
                created_at_str,
                id
            );
            Utc::now()
        }
    };

    Ok(Repository {
        id: Some(id),
        owner,
        name,
        url,
        status,
        description,
        is_private,
        local_path,
        last_checked,
        last_archived,
        error_message,
        created_at,
    })
}

const SELECT_COLS: &str =
    "id, owner, name, url, description, status, is_private, local_path, last_checked, last_updated, error_message, created_at";

/// Insert a new repository with pending status.
pub fn insert_repo(
    conn: &Connection,
    owner: &str,
    name: &str,
    url: &str,
) -> Result<Repository, AppError> {
    conn.execute(
        "INSERT INTO repositories (owner, name, url) VALUES (?1, ?2, ?3)",
        params![owner, name, url],
    )?;

    let id = conn.last_insert_rowid();
    get_repo_by_id(conn, id)?
        .ok_or_else(|| AppError::Custom("Failed to retrieve inserted repository".to_string()))
}

/// Get a repository by its primary key.
pub fn get_repo_by_id(conn: &Connection, id: i64) -> Result<Option<Repository>, AppError> {
    let sql = format!("SELECT {} FROM repositories WHERE id = ?1", SELECT_COLS);
    let mut stmt = conn.prepare(&sql)?;
    let mut rows = stmt.query_map(params![id], row_to_repo)?;
    match rows.next() {
        Some(r) => Ok(Some(r?)),
        None => Ok(None),
    }
}

/// Get a repository by its URL.
pub fn get_repo_by_url(conn: &Connection, url: &str) -> Result<Option<Repository>, AppError> {
    let sql = format!("SELECT {} FROM repositories WHERE url = ?1", SELECT_COLS);
    let mut stmt = conn.prepare(&sql)?;
    let mut rows = stmt.query_map(params![url], row_to_repo)?;
    match rows.next() {
        Some(r) => Ok(Some(r?)),
        None => Ok(None),
    }
}

/// List all repositories, optionally filtered by status.
pub fn list_repos(
    conn: &Connection,
    status_filter: Option<&RepoStatus>,
) -> Result<Vec<Repository>, AppError> {
    match status_filter {
        Some(status) => {
            let sql = format!(
                "SELECT {} FROM repositories WHERE status = ?1 ORDER BY id",
                SELECT_COLS
            );
            let mut stmt = conn.prepare(&sql)?;
            let repos = stmt
                .query_map(params![status.to_string()], row_to_repo)?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(repos)
        }
        None => {
            let sql = format!("SELECT {} FROM repositories ORDER BY id", SELECT_COLS);
            let mut stmt = conn.prepare(&sql)?;
            let repos = stmt
                .query_map([], row_to_repo)?
                .collect::<Result<Vec<_>, _>>()?;
            Ok(repos)
        }
    }
}

/// Update a repository's status and optionally set an error message.
pub fn update_repo_status(
    conn: &Connection,
    id: i64,
    status: &RepoStatus,
    error_msg: Option<&str>,
) -> Result<(), AppError> {
    conn.execute(
        "UPDATE repositories SET status = ?1, error_message = ?2 WHERE id = ?3",
        params![status.to_string(), error_msg, id],
    )?;
    Ok(())
}

/// Update a repository's description and private flag.
pub fn update_repo_metadata(
    conn: &Connection,
    id: i64,
    description: Option<&str>,
    is_private: bool,
) -> Result<(), AppError> {
    conn.execute(
        "UPDATE repositories SET description = ?1, is_private = ?2 WHERE id = ?3",
        params![description, is_private, id],
    )?;
    Ok(())
}

/// Update timestamp fields on a repository.
///
/// Maps: cloned -> last_cloned, updated -> last_updated, checked -> last_checked.
pub fn update_repo_timestamps(
    conn: &Connection,
    id: i64,
    cloned: Option<DateTime<Utc>>,
    updated: Option<DateTime<Utc>>,
    checked: Option<DateTime<Utc>>,
) -> Result<(), AppError> {
    let cloned_str = cloned.map(|d| d.to_rfc3339());
    let updated_str = updated.map(|d| d.to_rfc3339());
    let checked_str = checked.map(|d| d.to_rfc3339());

    conn.execute(
        "UPDATE repositories SET last_cloned = COALESCE(?1, last_cloned), last_updated = COALESCE(?2, last_updated), last_checked = COALESCE(?3, last_checked) WHERE id = ?4",
        params![cloned_str, updated_str, checked_str, id],
    )?;
    Ok(())
}

/// Set the local file path for a cloned repository.
pub fn set_repo_local_path(conn: &Connection, id: i64, path: &str) -> Result<(), AppError> {
    conn.execute(
        "UPDATE repositories SET local_path = ?1 WHERE id = ?2",
        params![path, id],
    )?;
    Ok(())
}

/// Delete a repository by id (cascades to archives and file_hashes).
pub fn delete_repo(conn: &Connection, id: i64) -> Result<(), AppError> {
    conn.execute("DELETE FROM repositories WHERE id = ?1", params![id])?;
    Ok(())
}

/// Get count of repositories grouped by status.
#[allow(dead_code)]
pub fn get_repo_count_by_status(conn: &Connection) -> Result<HashMap<String, i64>, AppError> {
    let mut stmt = conn.prepare("SELECT status, COUNT(*) FROM repositories GROUP BY status")?;
    let rows = stmt.query_map([], |row| {
        let status: String = row.get(0)?;
        let count: i64 = row.get(1)?;
        Ok((status, count))
    })?;

    let mut map = HashMap::new();
    for row in rows {
        let (status, count) = row?;
        map.insert(status, count);
    }
    Ok(map)
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
    fn test_insert_repo() {
        let conn = setup_db();
        let repo = insert_repo(
            &conn,
            "octocat",
            "Hello-World",
            "https://github.com/octocat/Hello-World",
        )
        .unwrap();

        assert!(repo.id.is_some());
        assert_eq!(repo.owner, "octocat");
        assert_eq!(repo.name, "Hello-World");
        assert_eq!(repo.url, "https://github.com/octocat/Hello-World");
        assert_eq!(repo.status, RepoStatus::Pending);
        assert!(repo.description.is_none());
        assert!(repo.last_checked.is_none());
        assert!(repo.last_archived.is_none());
        assert!(repo.error_message.is_none());
    }

    #[test]
    fn test_insert_duplicate_url_fails() {
        let conn = setup_db();
        insert_repo(
            &conn,
            "octocat",
            "Hello-World",
            "https://github.com/octocat/Hello-World",
        )
        .unwrap();
        let result = insert_repo(
            &conn,
            "octocat",
            "Hello-World",
            "https://github.com/octocat/Hello-World",
        );
        assert!(result.is_err());
    }

    #[test]
    fn test_list_repos_empty() {
        let conn = setup_db();
        let repos = list_repos(&conn, None).unwrap();
        assert!(repos.is_empty());
    }

    #[test]
    fn test_list_repos_with_status_filter() {
        let conn = setup_db();
        let repo1 =
            insert_repo(&conn, "owner1", "repo1", "https://github.com/owner1/repo1").unwrap();
        let repo2 =
            insert_repo(&conn, "owner2", "repo2", "https://github.com/owner2/repo2").unwrap();

        // Make repo2 active
        update_repo_status(&conn, repo2.id.unwrap(), &RepoStatus::Active, None).unwrap();

        // Filter for active only
        let active_repos = list_repos(&conn, Some(&RepoStatus::Active)).unwrap();
        assert_eq!(active_repos.len(), 1);
        assert_eq!(active_repos[0].owner, "owner2");

        // Filter for pending only
        let pending_repos = list_repos(&conn, Some(&RepoStatus::Pending)).unwrap();
        assert_eq!(pending_repos.len(), 1);
        assert_eq!(pending_repos[0].owner, "owner1");

        // No filter returns all
        let all_repos = list_repos(&conn, None).unwrap();
        assert_eq!(all_repos.len(), 2);

        // Suppress unused variable warning
        let _ = repo1;
    }

    #[test]
    fn test_update_repo_status() {
        let conn = setup_db();
        let repo =
            insert_repo(&conn, "octocat", "repo", "https://github.com/octocat/repo").unwrap();
        let id = repo.id.unwrap();

        update_repo_status(&conn, id, &RepoStatus::Active, None).unwrap();
        let updated = get_repo_by_id(&conn, id).unwrap().unwrap();
        assert_eq!(updated.status, RepoStatus::Active);
        assert!(updated.error_message.is_none());

        // Set to error with message
        update_repo_status(&conn, id, &RepoStatus::Error, Some("clone failed")).unwrap();
        let errored = get_repo_by_id(&conn, id).unwrap().unwrap();
        assert_eq!(errored.status, RepoStatus::Error);
        assert_eq!(errored.error_message.as_deref(), Some("clone failed"));
    }

    #[test]
    fn test_update_repo_metadata() {
        let conn = setup_db();
        let repo =
            insert_repo(&conn, "octocat", "repo", "https://github.com/octocat/repo").unwrap();
        let id = repo.id.unwrap();

        update_repo_metadata(&conn, id, Some("A cool repo"), true).unwrap();
        let updated = get_repo_by_id(&conn, id).unwrap().unwrap();
        assert_eq!(updated.description.as_deref(), Some("A cool repo"));
    }

    #[test]
    fn test_delete_repo() {
        let conn = setup_db();
        let repo =
            insert_repo(&conn, "octocat", "repo", "https://github.com/octocat/repo").unwrap();
        let id = repo.id.unwrap();

        delete_repo(&conn, id).unwrap();
        let result = get_repo_by_id(&conn, id).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_get_repo_by_url() {
        let conn = setup_db();
        let url = "https://github.com/octocat/Hello-World";
        insert_repo(&conn, "octocat", "Hello-World", url).unwrap();

        let found = get_repo_by_url(&conn, url).unwrap();
        assert!(found.is_some());
        assert_eq!(found.unwrap().owner, "octocat");

        let not_found = get_repo_by_url(&conn, "https://github.com/nobody/nothing").unwrap();
        assert!(not_found.is_none());
    }

    #[test]
    fn test_update_repo_timestamps() {
        let conn = setup_db();
        let repo =
            insert_repo(&conn, "octocat", "repo", "https://github.com/octocat/repo").unwrap();
        let id = repo.id.unwrap();

        let now = Utc::now();
        update_repo_timestamps(&conn, id, Some(now), Some(now), Some(now)).unwrap();

        let updated = get_repo_by_id(&conn, id).unwrap().unwrap();
        // last_checked and last_archived (mapped from last_updated) should be set
        assert!(updated.last_checked.is_some());
        assert!(updated.last_archived.is_some());
    }

    #[test]
    fn test_set_repo_local_path() {
        let conn = setup_db();
        let repo =
            insert_repo(&conn, "octocat", "repo", "https://github.com/octocat/repo").unwrap();
        let id = repo.id.unwrap();

        // Initially local_path should be None
        assert!(repo.local_path.is_none());

        set_repo_local_path(&conn, id, "/data/octocat/repo.git").unwrap();
        let updated = get_repo_by_id(&conn, id).unwrap().unwrap();
        assert_eq!(
            updated.local_path.as_deref(),
            Some("/data/octocat/repo.git")
        );
    }

    #[test]
    fn test_get_repo_count_by_status() {
        let conn = setup_db();
        insert_repo(&conn, "o1", "r1", "https://github.com/o1/r1").unwrap();
        insert_repo(&conn, "o2", "r2", "https://github.com/o2/r2").unwrap();

        let repo3 = insert_repo(&conn, "o3", "r3", "https://github.com/o3/r3").unwrap();
        update_repo_status(&conn, repo3.id.unwrap(), &RepoStatus::Active, None).unwrap();

        let counts = get_repo_count_by_status(&conn).unwrap();
        assert_eq!(counts.get("pending"), Some(&2));
        assert_eq!(counts.get("active"), Some(&1));
    }
}
