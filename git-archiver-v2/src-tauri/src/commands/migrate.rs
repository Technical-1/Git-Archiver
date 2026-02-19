use std::collections::HashMap;
use std::path::Path;

use chrono::{DateTime, NaiveDateTime, Utc};
use serde::{Deserialize, Serialize};
use tauri::State;

use crate::core::url::{extract_owner_repo, normalize_repo_url, validate_repo_url};
use crate::db;
use crate::error::AppError;
use crate::models::RepoStatus;
use crate::state::AppState;

/// Result summary returned after migrating from legacy JSON format.
#[derive(Debug, Clone, Serialize)]
pub struct MigrateResult {
    pub repos_imported: u32,
    pub repos_skipped: u32,
    pub archives_found: u32,
    pub errors: Vec<String>,
}

/// Legacy repository entry from the Python version's cloned_repos.json.
#[derive(Debug, Deserialize)]
struct LegacyRepoEntry {
    local_path: Option<String>,
    last_cloned: Option<String>,
    last_updated: Option<String>,
    status: Option<String>,
    description: Option<String>,
}

/// Parse a legacy date string ("YYYY-MM-DD HH:MM:SS") into DateTime<Utc>.
///
/// Returns None if the string is empty or cannot be parsed.
fn parse_legacy_date(date_str: &str) -> Option<DateTime<Utc>> {
    NaiveDateTime::parse_from_str(date_str, "%Y-%m-%d %H:%M:%S")
        .ok()
        .map(|naive| naive.and_utc())
}

/// Parse a legacy status string into RepoStatus.
///
/// Falls back to RepoStatus::Pending for unrecognized values.
fn parse_legacy_status(status_str: &str) -> RepoStatus {
    match status_str {
        "pending" => RepoStatus::Pending,
        "active" => RepoStatus::Active,
        "archived" => RepoStatus::Archived,
        "deleted" => RepoStatus::Deleted,
        "error" => RepoStatus::Error,
        _ => RepoStatus::Pending,
    }
}

/// Migrate repositories from a legacy Python-version JSON file into the SQLite database.
///
/// Reads the JSON file at `json_path`, parses each entry, inserts repositories into the
/// database, and scans for existing archive files. Entries with invalid URLs or other
/// errors are skipped and reported in the result.
#[tauri::command]
pub async fn migrate_from_json(
    json_path: String,
    state: State<'_, AppState>,
) -> Result<MigrateResult, AppError> {
    // Read and parse the JSON file
    let content = std::fs::read_to_string(&json_path).map_err(|e| {
        AppError::UserVisible(format!("Failed to read file '{}': {}", json_path, e))
    })?;

    let legacy_data: HashMap<String, LegacyRepoEntry> =
        serde_json::from_str(&content).map_err(|e| {
            AppError::UserVisible(format!("Failed to parse JSON file '{}': {}", json_path, e))
        })?;

    let mut repos_imported: u32 = 0;
    let mut repos_skipped: u32 = 0;
    let mut archives_found: u32 = 0;
    let mut errors: Vec<String> = Vec::new();

    let db = state.db.lock().await;

    for (url, entry) in &legacy_data {
        // Validate URL
        if let Err(e) = validate_repo_url(url) {
            errors.push(format!("{}: {}", url, e));
            continue;
        }

        let normalized = normalize_repo_url(url);

        // Extract owner/repo
        let (owner, repo_name) = match extract_owner_repo(&normalized) {
            Ok(pair) => pair,
            Err(e) => {
                errors.push(format!("{}: {}", url, e));
                continue;
            }
        };

        // Check for duplicate
        match db::repos::get_repo_by_url(&db, &normalized) {
            Ok(Some(_)) => {
                repos_skipped += 1;
                continue;
            }
            Ok(None) => {}
            Err(e) => {
                errors.push(format!("{}: {}", url, e));
                continue;
            }
        }

        // Insert the repo
        let repo = match db::repos::insert_repo(&db, &owner, &repo_name, &normalized) {
            Ok(r) => r,
            Err(e) => {
                errors.push(format!("{}: Failed to insert: {}", url, e));
                continue;
            }
        };

        let repo_id = match repo.id {
            Some(id) => id,
            None => {
                errors.push(format!("{}: Failed to get repo ID after insert", url));
                continue;
            }
        };

        // Update status
        let status = entry
            .status
            .as_deref()
            .map(parse_legacy_status)
            .unwrap_or(RepoStatus::Pending);

        if let Err(e) = db::repos::update_repo_status(&db, repo_id, &status, None) {
            errors.push(format!("{}: Failed to update status: {}", url, e));
        }

        // Update timestamps
        let last_cloned = entry.last_cloned.as_deref().and_then(parse_legacy_date);
        let last_updated = entry.last_updated.as_deref().and_then(parse_legacy_date);

        if last_cloned.is_some() || last_updated.is_some() {
            if let Err(e) =
                db::repos::update_repo_timestamps(&db, repo_id, last_cloned, last_updated, None)
            {
                errors.push(format!("{}: Failed to update timestamps: {}", url, e));
            }
        }

        // Update local_path
        if let Some(ref local_path) = entry.local_path {
            if let Err(e) = db::repos::set_repo_local_path(&db, repo_id, local_path) {
                errors.push(format!("{}: Failed to set local path: {}", url, e));
            }
        }

        // Update description
        if let Some(ref description) = entry.description {
            if let Err(e) = db::repos::update_repo_metadata(&db, repo_id, Some(description), false)
            {
                errors.push(format!("{}: Failed to update description: {}", url, e));
            }
        }

        // Scan for archive files
        if let Some(ref local_path) = entry.local_path {
            let versions_dir = Path::new(local_path).join("versions");
            if versions_dir.exists() && versions_dir.is_dir() {
                if let Ok(entries) = std::fs::read_dir(&versions_dir) {
                    for dir_entry in entries.flatten() {
                        let file_path = dir_entry.path();
                        if let Some(ext) = file_path.extension() {
                            // Match .xz files (the .tar part is in the stem)
                            if ext == "xz" {
                                let filename = file_path
                                    .file_name()
                                    .map(|f| f.to_string_lossy().to_string())
                                    .unwrap_or_default();

                                let file_path_str = file_path.to_string_lossy().to_string();

                                let size_bytes =
                                    std::fs::metadata(&file_path).map(|m| m.len()).unwrap_or(0);

                                match db::archives::insert_archive(
                                    &db,
                                    repo_id,
                                    &filename,
                                    &file_path_str,
                                    size_bytes,
                                    0, // file_count unknown from legacy data
                                    false,
                                ) {
                                    Ok(_) => archives_found += 1,
                                    Err(e) => {
                                        errors.push(format!(
                                            "{}: Failed to insert archive '{}': {}",
                                            url, filename, e
                                        ));
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        repos_imported += 1;
    }

    Ok(MigrateResult {
        repos_imported,
        repos_skipped,
        archives_found,
        errors,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::migrations::run_migrations;
    use rusqlite::Connection;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn setup_db() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        run_migrations(&conn).unwrap();
        conn
    }

    #[test]
    fn test_parse_legacy_date_valid() {
        let result = parse_legacy_date("2025-01-01 12:00:00");
        assert!(result.is_some());
        let dt = result.unwrap();
        assert_eq!(
            dt.format("%Y-%m-%d %H:%M:%S").to_string(),
            "2025-01-01 12:00:00"
        );
    }

    #[test]
    fn test_parse_legacy_date_invalid() {
        assert!(parse_legacy_date("not-a-date").is_none());
        assert!(parse_legacy_date("").is_none());
        assert!(parse_legacy_date("2025/01/01 12:00:00").is_none());
    }

    #[test]
    fn test_parse_legacy_status_known() {
        assert_eq!(parse_legacy_status("pending"), RepoStatus::Pending);
        assert_eq!(parse_legacy_status("active"), RepoStatus::Active);
        assert_eq!(parse_legacy_status("archived"), RepoStatus::Archived);
        assert_eq!(parse_legacy_status("deleted"), RepoStatus::Deleted);
        assert_eq!(parse_legacy_status("error"), RepoStatus::Error);
    }

    #[test]
    fn test_parse_legacy_status_unknown_falls_back() {
        assert_eq!(parse_legacy_status("unknown"), RepoStatus::Pending);
        assert_eq!(parse_legacy_status(""), RepoStatus::Pending);
    }

    #[test]
    fn test_parse_legacy_json() {
        let json = r#"{
            "https://github.com/owner/repo": {
                "local_path": "data/owner_repo",
                "last_cloned": "2025-01-01 12:00:00",
                "last_updated": "2025-06-15 08:30:00",
                "status": "active",
                "description": "A cool repo"
            }
        }"#;

        let data: HashMap<String, LegacyRepoEntry> = serde_json::from_str(json).unwrap();
        assert_eq!(data.len(), 1);

        let entry = data.get("https://github.com/owner/repo").unwrap();
        assert_eq!(entry.local_path.as_deref(), Some("data/owner_repo"));
        assert_eq!(entry.last_cloned.as_deref(), Some("2025-01-01 12:00:00"));
        assert_eq!(entry.last_updated.as_deref(), Some("2025-06-15 08:30:00"));
        assert_eq!(entry.status.as_deref(), Some("active"));
        assert_eq!(entry.description.as_deref(), Some("A cool repo"));
    }

    #[test]
    fn test_handles_null_fields() {
        let json = r#"{
            "https://github.com/another/project": {
                "local_path": "data/another_project",
                "last_cloned": "2025-03-01 10:00:00",
                "last_updated": null,
                "status": "pending",
                "description": null
            }
        }"#;

        let data: HashMap<String, LegacyRepoEntry> = serde_json::from_str(json).unwrap();
        let entry = data.get("https://github.com/another/project").unwrap();
        assert!(entry.last_updated.is_none());
        assert!(entry.description.is_none());
        assert_eq!(entry.status.as_deref(), Some("pending"));
    }

    #[test]
    fn test_handles_missing_fields() {
        let json = r#"{
            "https://github.com/owner/repo": {}
        }"#;

        let data: HashMap<String, LegacyRepoEntry> = serde_json::from_str(json).unwrap();
        let entry = data.get("https://github.com/owner/repo").unwrap();
        assert!(entry.local_path.is_none());
        assert!(entry.last_cloned.is_none());
        assert!(entry.last_updated.is_none());
        assert!(entry.status.is_none());
        assert!(entry.description.is_none());
    }

    #[test]
    fn test_migrate_inserts_repos_into_db() {
        let conn = setup_db();

        let json = r#"{
            "https://github.com/owner/repo": {
                "local_path": "data/owner_repo",
                "last_cloned": "2025-01-01 12:00:00",
                "last_updated": "2025-06-15 08:30:00",
                "status": "active",
                "description": "A cool repo"
            },
            "https://github.com/another/project": {
                "local_path": "data/another_project",
                "last_cloned": "2025-03-01 10:00:00",
                "last_updated": null,
                "status": "pending",
                "description": null
            }
        }"#;

        let mut tmp = NamedTempFile::new().unwrap();
        write!(tmp, "{}", json).unwrap();

        let legacy_data: HashMap<String, LegacyRepoEntry> = serde_json::from_str(json).unwrap();

        let mut repos_imported: u32 = 0;
        let errors: Vec<String> = Vec::new();

        for (url, entry) in &legacy_data {
            if validate_repo_url(url).is_err() {
                continue;
            }

            let normalized = normalize_repo_url(url);
            let (owner, repo_name) = extract_owner_repo(&normalized).unwrap();

            let repo = db::repos::insert_repo(&conn, &owner, &repo_name, &normalized).unwrap();
            let repo_id = repo.id.unwrap();

            let status = entry
                .status
                .as_deref()
                .map(parse_legacy_status)
                .unwrap_or(RepoStatus::Pending);
            db::repos::update_repo_status(&conn, repo_id, &status, None).unwrap();

            if let Some(ref desc) = entry.description {
                db::repos::update_repo_metadata(&conn, repo_id, Some(desc), false).unwrap();
            }

            if let Some(ref local_path) = entry.local_path {
                db::repos::set_repo_local_path(&conn, repo_id, local_path).unwrap();
            }

            let last_cloned = entry.last_cloned.as_deref().and_then(parse_legacy_date);
            let last_updated = entry.last_updated.as_deref().and_then(parse_legacy_date);
            if last_cloned.is_some() || last_updated.is_some() {
                db::repos::update_repo_timestamps(&conn, repo_id, last_cloned, last_updated, None)
                    .unwrap();
            }

            repos_imported += 1;
        }

        assert_eq!(repos_imported, 2);
        assert!(errors.is_empty());

        // Verify repos are in the database
        let all_repos = db::repos::list_repos(&conn, None).unwrap();
        assert_eq!(all_repos.len(), 2);

        // Find the active repo and verify its fields
        let active_repo = all_repos
            .iter()
            .find(|r| r.owner == "owner" && r.name == "repo")
            .unwrap();
        assert_eq!(active_repo.status, RepoStatus::Active);
        assert_eq!(active_repo.description.as_deref(), Some("A cool repo"));
        assert_eq!(active_repo.local_path.as_deref(), Some("data/owner_repo"));

        // Find the pending repo
        let pending_repo = all_repos
            .iter()
            .find(|r| r.owner == "another" && r.name == "project")
            .unwrap();
        assert_eq!(pending_repo.status, RepoStatus::Pending);
        assert!(pending_repo.description.is_none());
    }

    #[test]
    fn test_handles_invalid_url() {
        let json = r#"{
            "not-a-valid-url": {
                "local_path": "data/invalid",
                "last_cloned": null,
                "last_updated": null,
                "status": "pending",
                "description": null
            },
            "https://gitlab.com/owner/repo": {
                "local_path": "data/gitlab",
                "last_cloned": null,
                "last_updated": null,
                "status": "active",
                "description": null
            },
            "https://github.com/valid/repo": {
                "local_path": "data/valid_repo",
                "last_cloned": "2025-01-01 12:00:00",
                "last_updated": null,
                "status": "active",
                "description": "Valid one"
            }
        }"#;

        let conn = setup_db();
        let legacy_data: HashMap<String, LegacyRepoEntry> = serde_json::from_str(json).unwrap();

        let mut repos_imported: u32 = 0;
        let mut errors: Vec<String> = Vec::new();

        for (url, _entry) in &legacy_data {
            if let Err(e) = validate_repo_url(url) {
                errors.push(format!("{}: {}", url, e));
                continue;
            }

            let normalized = normalize_repo_url(url);
            let (owner, repo_name) = match extract_owner_repo(&normalized) {
                Ok(pair) => pair,
                Err(e) => {
                    errors.push(format!("{}: {}", url, e));
                    continue;
                }
            };

            match db::repos::insert_repo(&conn, &owner, &repo_name, &normalized) {
                Ok(_) => repos_imported += 1,
                Err(e) => errors.push(format!("{}: {}", url, e)),
            }
        }

        // Only the valid GitHub URL should be imported
        assert_eq!(repos_imported, 1);
        // Two invalid URLs should produce errors
        assert_eq!(errors.len(), 2);

        let all_repos = db::repos::list_repos(&conn, None).unwrap();
        assert_eq!(all_repos.len(), 1);
        assert_eq!(all_repos[0].owner, "valid");
        assert_eq!(all_repos[0].name, "repo");
    }

    #[test]
    fn test_skips_duplicate_repos() {
        let conn = setup_db();

        // Pre-insert a repo
        db::repos::insert_repo(&conn, "owner", "repo", "https://github.com/owner/repo").unwrap();

        let json = r#"{
            "https://github.com/owner/repo": {
                "local_path": "data/owner_repo",
                "last_cloned": "2025-01-01 12:00:00",
                "last_updated": null,
                "status": "active",
                "description": "A cool repo"
            },
            "https://github.com/new/project": {
                "local_path": "data/new_project",
                "last_cloned": null,
                "last_updated": null,
                "status": "pending",
                "description": null
            }
        }"#;

        let legacy_data: HashMap<String, LegacyRepoEntry> = serde_json::from_str(json).unwrap();

        let mut repos_imported: u32 = 0;
        let mut repos_skipped: u32 = 0;

        for (url, _entry) in &legacy_data {
            if validate_repo_url(url).is_err() {
                continue;
            }

            let normalized = normalize_repo_url(url);
            let (owner, repo_name) = extract_owner_repo(&normalized).unwrap();

            match db::repos::get_repo_by_url(&conn, &normalized) {
                Ok(Some(_)) => {
                    repos_skipped += 1;
                    continue;
                }
                Ok(None) => {}
                Err(_) => continue,
            }

            db::repos::insert_repo(&conn, &owner, &repo_name, &normalized).unwrap();
            repos_imported += 1;
        }

        assert_eq!(repos_imported, 1);
        assert_eq!(repos_skipped, 1);

        let all_repos = db::repos::list_repos(&conn, None).unwrap();
        assert_eq!(all_repos.len(), 2);
    }

    #[test]
    fn test_archive_scanning() {
        let conn = setup_db();

        // Create a temporary directory structure mimicking legacy layout
        let tmp_dir = tempfile::tempdir().unwrap();
        let versions_dir = tmp_dir.path().join("versions");
        std::fs::create_dir_all(&versions_dir).unwrap();

        // Create fake archive files
        let archive1 = versions_dir.join("repo-2025-01-01.tar.xz");
        let archive2 = versions_dir.join("repo-2025-02-01.tar.xz");
        let not_archive = versions_dir.join("readme.txt");

        std::fs::write(&archive1, b"fake archive 1").unwrap();
        std::fs::write(&archive2, b"fake archive 2 longer").unwrap();
        std::fs::write(&not_archive, b"not an archive").unwrap();

        // Insert a repo
        let repo = db::repos::insert_repo(&conn, "owner", "repo", "https://github.com/owner/repo")
            .unwrap();
        let repo_id = repo.id.unwrap();

        // Scan for archives (mimicking the migration logic)
        let mut archives_found: u32 = 0;
        let local_path = tmp_dir.path().to_string_lossy().to_string();

        let scan_dir = Path::new(&local_path).join("versions");
        if scan_dir.exists() && scan_dir.is_dir() {
            for dir_entry in std::fs::read_dir(&scan_dir).unwrap().flatten() {
                let file_path = dir_entry.path();
                if let Some(ext) = file_path.extension() {
                    if ext == "xz" {
                        let filename = file_path
                            .file_name()
                            .map(|f| f.to_string_lossy().to_string())
                            .unwrap_or_default();
                        let file_path_str = file_path.to_string_lossy().to_string();
                        let size_bytes =
                            std::fs::metadata(&file_path).map(|m| m.len()).unwrap_or(0);

                        db::archives::insert_archive(
                            &conn,
                            repo_id,
                            &filename,
                            &file_path_str,
                            size_bytes,
                            0,
                            false,
                        )
                        .unwrap();
                        archives_found += 1;
                    }
                }
            }
        }

        // Should find exactly 2 .tar.xz files, not the .txt
        assert_eq!(archives_found, 2);

        let archives = db::archives::list_archives(&conn, repo_id).unwrap();
        assert_eq!(archives.len(), 2);
    }
}
