//! Integration tests for the full repository lifecycle pipeline.
//!
//! These tests exercise the same operations as the worker loop
//! (clone → archive → hash → update → incremental archive) using
//! local git repos as fixtures — no network access, no Tauri runtime.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use rusqlite::Connection;
use tempfile::TempDir;

use git_archiver_v2_lib::core::archive;
use git_archiver_v2_lib::core::git;
use git_archiver_v2_lib::core::hasher;
use git_archiver_v2_lib::core::url::{extract_owner_repo, normalize_repo_url, validate_repo_url};
use git_archiver_v2_lib::db::{archives, file_hashes, migrations, repos, settings};
use git_archiver_v2_lib::models::RepoStatus;

// ─── Helpers ────────────────────────────────────────────────────────────────

/// Create an in-memory SQLite DB with migrations applied.
fn setup_db() -> Connection {
    let conn = Connection::open_in_memory().unwrap();
    migrations::run_migrations(&conn).unwrap();
    conn
}

/// Clone a local repo without shallow depth (libgit2 local transport doesn't support shallow fetch).
fn clone_local(source: &Path, dest: &Path) {
    git2::Repository::clone(source.to_str().unwrap(), dest).expect("Local clone should succeed");
}

/// Create a local git repo with an initial commit containing test files.
/// Returns the path to the repo (acts as our "remote").
fn create_test_repo(base_dir: &Path) -> PathBuf {
    let repo_path = base_dir.join("test-remote");
    std::fs::create_dir_all(repo_path.join("src")).unwrap();

    let repo = git2::Repository::init(&repo_path).unwrap();

    // Create test files
    std::fs::write(
        repo_path.join("README.md"),
        "# Test Repo\nA test repository.\n",
    )
    .unwrap();
    std::fs::write(
        repo_path.join("src/main.rs"),
        "fn main() {\n    println!(\"hello\");\n}\n",
    )
    .unwrap();
    std::fs::write(
        repo_path.join("Cargo.toml"),
        "[package]\nname = \"test-repo\"\nversion = \"0.1.0\"\n",
    )
    .unwrap();

    // Stage and commit
    let mut index = repo.index().unwrap();
    index
        .add_all(["*"].iter(), git2::IndexAddOption::DEFAULT, None)
        .unwrap();
    index.write().unwrap();
    let tree_id = index.write_tree().unwrap();
    let tree = repo.find_tree(tree_id).unwrap();
    let sig = git2::Signature::now("Test User", "test@example.com").unwrap();
    repo.commit(Some("HEAD"), &sig, &sig, "Initial commit", &tree, &[])
        .unwrap();

    repo_path
}

/// Add a new commit to an existing repo (modify or create a file).
fn add_commit(repo_path: &Path, filename: &str, content: &str, message: &str) {
    // Ensure parent directories exist
    let file_path = repo_path.join(filename);
    if let Some(parent) = file_path.parent() {
        std::fs::create_dir_all(parent).unwrap();
    }
    std::fs::write(&file_path, content).unwrap();

    let repo = git2::Repository::open(repo_path).unwrap();
    let mut index = repo.index().unwrap();
    index
        .add_all(["*"].iter(), git2::IndexAddOption::DEFAULT, None)
        .unwrap();
    index.write().unwrap();
    let tree_id = index.write_tree().unwrap();
    let tree = repo.find_tree(tree_id).unwrap();
    let sig = git2::Signature::now("Test User", "test@example.com").unwrap();
    let head = repo.head().unwrap().peel_to_commit().unwrap();
    repo.commit(Some("HEAD"), &sig, &sig, message, &tree, &[&head])
        .unwrap();
}

/// Set up a complete clone pipeline: create remote, clone it, return paths and DB state.
fn setup_cloned_repo(
    tmp: &TempDir,
) -> (Connection, PathBuf, PathBuf, i64, HashMap<String, String>) {
    let remote_path = create_test_repo(tmp.path());
    let clone_path = tmp.path().join("clone").join("owner").join("test-repo.git");

    // Clone (local transport, no shallow)
    clone_local(&remote_path, &clone_path);

    // Set up DB
    let conn = setup_db();
    let repo = repos::insert_repo(
        &conn,
        "owner",
        "test-repo",
        "https://github.com/owner/test-repo",
    )
    .unwrap();
    let repo_id = repo.id.unwrap();

    // Update DB status
    repos::update_repo_status(&conn, repo_id, &RepoStatus::Active, None).unwrap();
    repos::set_repo_local_path(&conn, repo_id, clone_path.to_str().unwrap()).unwrap();

    // Hash files and store
    let hashes = hasher::hash_directory(&clone_path).unwrap();
    for (path, hash) in &hashes {
        file_hashes::upsert_file_hash(&conn, repo_id, path, hash).unwrap();
    }

    (conn, remote_path, clone_path, repo_id, hashes)
}

// ─── Test 1: Full Clone Pipeline ────────────────────────────────────────────

#[test]
fn test_full_clone_pipeline() {
    let tmp = TempDir::new().unwrap();
    let remote_path = create_test_repo(tmp.path());
    let clone_path = tmp.path().join("clone").join("owner").join("test-repo.git");

    // Step 1: Insert repo into DB
    let conn = setup_db();
    let repo = repos::insert_repo(
        &conn,
        "owner",
        "test-repo",
        "https://github.com/owner/test-repo",
    )
    .unwrap();
    let repo_id = repo.id.unwrap();
    assert_eq!(repo.status, RepoStatus::Pending);

    // Step 2: Clone from local path (non-shallow for local transport)
    clone_local(&remote_path, &clone_path);

    // Verify clone
    assert!(
        clone_path.join(".git").exists(),
        "Clone should have .git directory"
    );

    // Step 3: Create full archive
    let versions_dir = clone_path.join("versions");
    let archive_path = versions_dir.join("test-repo-20260101-000000.tar.xz");
    let archive_info =
        archive::create_archive::<fn(u32, u32)>(&clone_path, &archive_path, None, None)
            .expect("Archive creation should succeed");

    assert!(archive_path.exists());
    assert!(archive_info.file_count >= 3, "Should have at least 3 files");
    assert!(archive_info.size_bytes > 0);

    // Step 4: Hash directory
    let hashes = hasher::hash_directory(&clone_path).expect("Hashing should succeed");
    assert!(hashes.len() >= 3, "Should have hashes for at least 3 files");
    assert!(hashes.contains_key("README.md"));
    assert!(hashes.contains_key("src/main.rs"));
    assert!(hashes.contains_key("Cargo.toml"));

    // Step 5: Update DB (mirrors handle_clone_inner)
    repos::update_repo_status(&conn, repo_id, &RepoStatus::Active, None).unwrap();
    repos::set_repo_local_path(&conn, repo_id, clone_path.to_str().unwrap()).unwrap();

    archives::insert_archive(
        &conn,
        repo_id,
        "test-repo-20260101-000000.tar.xz",
        archive_path.to_str().unwrap(),
        archive_info.size_bytes,
        archive_info.file_count,
        false,
    )
    .unwrap();

    for (path, hash) in &hashes {
        file_hashes::upsert_file_hash(&conn, repo_id, path, hash).unwrap();
    }

    // Step 6: Verify DB state
    let updated_repo = repos::get_repo_by_id(&conn, repo_id).unwrap().unwrap();
    assert_eq!(updated_repo.status, RepoStatus::Active);
    assert!(updated_repo.local_path.is_some());

    let repo_archives = archives::list_archives(&conn, repo_id).unwrap();
    assert_eq!(repo_archives.len(), 1);
    assert!(!repo_archives[0].is_incremental);

    let stored_hashes = file_hashes::get_file_hashes(&conn, repo_id).unwrap();
    assert_eq!(stored_hashes.len(), hashes.len());
}

// ─── Test 2: Update with Incremental Archive ────────────────────────────────

#[test]
fn test_update_with_incremental_archive() {
    let tmp = TempDir::new().unwrap();
    let (conn, remote_path, clone_path, repo_id, old_hashes) = setup_cloned_repo(&tmp);

    // Add changes to the remote: modify one file, add a new one
    add_commit(
        &remote_path,
        "README.md",
        "# Test Repo\nUpdated content.\n",
        "Update README",
    );
    add_commit(
        &remote_path,
        "src/lib.rs",
        "pub fn greet() -> &'static str { \"hello\" }\n",
        "Add lib.rs",
    );

    // Fetch and check for updates
    let has_updates =
        git::fetch_and_check_updates(&clone_path).expect("Fetch check should succeed");
    assert!(has_updates, "Should detect updates after new commits");

    // Pull updates
    let pulled = git::pull_repo(&clone_path).expect("Pull should succeed");
    assert!(pulled, "Pull should return true when updates exist");

    // Compute new hashes and detect changes
    let new_hashes = hasher::hash_directory(&clone_path).expect("Hashing should succeed");
    let changed_files = hasher::detect_changed_files(&old_hashes, &new_hashes);

    assert!(
        changed_files.len() >= 2,
        "Should detect at least 2 changed files (README.md modified, src/lib.rs added), got: {:?}",
        changed_files
    );
    assert!(
        changed_files.contains(&"README.md".to_string()),
        "README.md should be in changed files"
    );
    assert!(
        changed_files.contains(&"src/lib.rs".to_string()),
        "src/lib.rs should be in changed files"
    );

    // Create incremental archive
    let versions_dir = clone_path.join("versions");
    let archive_path = versions_dir.join("test-repo-20260101-000001-incremental.tar.xz");
    let archive_info = archive::create_archive::<fn(u32, u32)>(
        &clone_path,
        &archive_path,
        Some(&changed_files),
        None,
    )
    .expect("Incremental archive should succeed");

    assert!(archive_path.exists());
    assert_eq!(
        archive_info.file_count as usize,
        changed_files.len(),
        "Incremental archive should contain only changed files"
    );

    // Update DB with new hashes and archive record
    archives::insert_archive(
        &conn,
        repo_id,
        "test-repo-20260101-000001-incremental.tar.xz",
        archive_path.to_str().unwrap(),
        archive_info.size_bytes,
        archive_info.file_count,
        true,
    )
    .unwrap();

    for (path, hash) in &new_hashes {
        file_hashes::upsert_file_hash(&conn, repo_id, path, hash).unwrap();
    }

    // Verify: DB should now have the new hashes
    let stored_hashes = file_hashes::get_file_hashes(&conn, repo_id).unwrap();
    assert!(
        stored_hashes.contains_key("src/lib.rs"),
        "New file hash should be stored"
    );
}

// ─── Test 3: Update No Changes ──────────────────────────────────────────────

#[test]
fn test_update_no_changes() {
    let tmp = TempDir::new().unwrap();
    let remote_path = create_test_repo(tmp.path());
    let clone_path = tmp.path().join("clone").join("repo.git");

    // Clone (local transport, no shallow)
    clone_local(&remote_path, &clone_path);

    // Immediately check for updates — should be none
    let has_updates =
        git::fetch_and_check_updates(&clone_path).expect("Fetch check should succeed");
    assert!(!has_updates, "Freshly cloned repo should not have updates");
}

// ─── Test 4: Clone → Archive → Extract Roundtrip ────────────────────────────

#[test]
fn test_clone_archive_extract_roundtrip() {
    let tmp = TempDir::new().unwrap();
    let remote_path = create_test_repo(tmp.path());
    let clone_path = tmp.path().join("clone").join("repo.git");

    // Clone (local transport, no shallow)
    clone_local(&remote_path, &clone_path);

    // Create archive
    let archive_path = tmp.path().join("archives").join("test.tar.xz");
    archive::create_archive::<fn(u32, u32)>(&clone_path, &archive_path, None, None)
        .expect("Archive creation should succeed");

    // Extract to a new location
    let extract_dir = tmp.path().join("extracted");
    archive::extract_archive(&archive_path, &extract_dir).expect("Extraction should succeed");

    // Verify extracted content matches original
    let original_readme = std::fs::read_to_string(clone_path.join("README.md")).unwrap();
    let extracted_readme = std::fs::read_to_string(extract_dir.join("README.md")).unwrap();
    assert_eq!(original_readme, extracted_readme);

    let original_main = std::fs::read_to_string(clone_path.join("src/main.rs")).unwrap();
    let extracted_main = std::fs::read_to_string(extract_dir.join("src/main.rs")).unwrap();
    assert_eq!(original_main, extracted_main);

    let original_cargo = std::fs::read_to_string(clone_path.join("Cargo.toml")).unwrap();
    let extracted_cargo = std::fs::read_to_string(extract_dir.join("Cargo.toml")).unwrap();
    assert_eq!(original_cargo, extracted_cargo);
}

// ─── Test 5: Full DB Record Lifecycle ────────────────────────────────────────

#[test]
fn test_full_db_lifecycle() {
    let conn = setup_db();

    // Insert repo (pending by default)
    let repo = repos::insert_repo(
        &conn,
        "testowner",
        "testrepo",
        "https://github.com/testowner/testrepo",
    )
    .unwrap();
    let repo_id = repo.id.unwrap();
    assert_eq!(repo.status, RepoStatus::Pending);

    // Update status to active
    repos::update_repo_status(&conn, repo_id, &RepoStatus::Active, None).unwrap();
    let repo = repos::get_repo_by_id(&conn, repo_id).unwrap().unwrap();
    assert_eq!(repo.status, RepoStatus::Active);

    // Set local path
    repos::set_repo_local_path(&conn, repo_id, "/tmp/testowner/testrepo.git").unwrap();
    let repo = repos::get_repo_by_id(&conn, repo_id).unwrap().unwrap();
    assert_eq!(
        repo.local_path.as_deref(),
        Some("/tmp/testowner/testrepo.git")
    );

    // Insert archive record
    archives::insert_archive(
        &conn,
        repo_id,
        "testrepo-20260101.tar.xz",
        "/tmp/archives/testrepo-20260101.tar.xz",
        1024,
        10,
        false,
    )
    .unwrap();
    let repo_archives = archives::list_archives(&conn, repo_id).unwrap();
    assert_eq!(repo_archives.len(), 1);

    // Store file hashes
    file_hashes::upsert_file_hash(&conn, repo_id, "src/main.rs", "abc123").unwrap();
    file_hashes::upsert_file_hash(&conn, repo_id, "README.md", "def456").unwrap();
    let hashes = file_hashes::get_file_hashes(&conn, repo_id).unwrap();
    assert_eq!(hashes.len(), 2);

    // Delete repo — cascades to archives and file hashes
    repos::delete_repo(&conn, repo_id).unwrap();
    assert!(repos::get_repo_by_id(&conn, repo_id).unwrap().is_none());
    assert!(archives::list_archives(&conn, repo_id).unwrap().is_empty());
    assert!(file_hashes::get_file_hashes(&conn, repo_id)
        .unwrap()
        .is_empty());
}

// ─── Test 6: Bulk URL Import Logic ──────────────────────────────────────────

#[test]
fn test_import_from_file_content() {
    let tmp = TempDir::new().unwrap();
    let conn = setup_db();

    // Create a test file with mixed content
    let import_file = tmp.path().join("repos.txt");
    std::fs::write(
        &import_file,
        "# This is a comment\n\
         https://github.com/rust-lang/rust\n\
         https://github.com/tauri-apps/tauri\n\
         \n\
         not-a-valid-url\n\
         https://github.com/rust-lang/rust\n\
         https://github.com/tokio-rs/tokio.git\n\
         https://notgithub.com/foo/bar\n",
    )
    .unwrap();

    // Process each line (mirrors import_from_file command logic)
    let content = std::fs::read_to_string(&import_file).unwrap();
    let mut added: u32 = 0;
    let mut skipped: u32 = 0;
    let mut errors: Vec<String> = Vec::new();

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        if let Err(e) = validate_repo_url(trimmed) {
            errors.push(format!("{}: {}", trimmed, e));
            continue;
        }

        let normalized = normalize_repo_url(trimmed);
        let (owner, repo_name) = match extract_owner_repo(&normalized) {
            Ok(pair) => pair,
            Err(e) => {
                errors.push(format!("{}: {}", trimmed, e));
                continue;
            }
        };

        // Check for duplicate
        match repos::get_repo_by_url(&conn, &normalized) {
            Ok(Some(_)) => {
                skipped += 1;
                continue;
            }
            Ok(None) => {}
            Err(e) => {
                errors.push(format!("{}: {}", trimmed, e));
                continue;
            }
        }

        match repos::insert_repo(&conn, &owner, &repo_name, &normalized) {
            Ok(_) => added += 1,
            Err(e) => errors.push(format!("{}: {}", trimmed, e)),
        }
    }

    assert_eq!(added, 3, "Should add 3 valid unique repos");
    assert_eq!(skipped, 1, "Should skip 1 duplicate");
    assert_eq!(
        errors.len(),
        2,
        "Should have 2 errors (not-a-valid-url, notgithub.com)"
    );

    // Verify repos in DB
    let all_repos = repos::list_repos(&conn, None).unwrap();
    assert_eq!(all_repos.len(), 3);

    // Verify settings defaults exist
    let app_settings = settings::get_app_settings(&conn).unwrap();
    assert_eq!(app_settings.max_concurrent_tasks, 4);
}
