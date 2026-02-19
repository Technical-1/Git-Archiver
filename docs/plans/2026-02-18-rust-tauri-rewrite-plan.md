# Git Archiver Rust/Tauri Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite Git-Archiver from Python/PyQt5 to Rust/Tauri with React+TypeScript frontend for public distribution on macOS, Windows, and Linux.

**Architecture:** Rust backend using git2, reqwest, rusqlite, tar+xz2 crates. Tauri v2 for windowing and IPC. React + TypeScript + shadcn/ui frontend with zustand state management. SQLite for persistence, OS keychain for secrets.

**Tech Stack:** Rust, Tauri v2, React 18, TypeScript, shadcn/ui, TailwindCSS, @tanstack/react-table, zustand, next-themes

**Design doc:** `docs/plans/2026-02-18-rust-tauri-rewrite-design.md`

---

## Prerequisites

Before starting, ensure these tools are installed:

```bash
# Rust toolchain
rustup --version    # If missing: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Node.js (for React frontend)
node --version      # Need 18+
pnpm --version      # If missing: npm install -g pnpm

# Tauri CLI
cargo install create-tauri-app
cargo install tauri-cli --version "^2"

# System deps (macOS)
xcode-select --install   # If not already installed
```

---

## Milestone 1: Project Scaffolding

**Goal:** A Tauri app that opens a window showing "Hello from Git Archiver" with dark mode toggle. Both `cargo test` and `pnpm test` pass with trivial placeholder tests.

### Task 1.1: Create Tauri v2 Project

**Files:**
- Create: `git-archiver-v2/` (new directory alongside existing Python code)

**Step 1: Scaffold the project**

```bash
cd /Users/jacobkanfer/Desktop/CodeRepositories/Git-Archiver
pnpm create tauri-app git-archiver-v2 --template react-ts --manager pnpm
```

Select these options when prompted:
- Project name: `git-archiver-v2`
- Frontend: `React`
- Language: `TypeScript`
- Package manager: `pnpm`

**Step 2: Verify it builds and opens**

```bash
cd git-archiver-v2
pnpm install
pnpm tauri dev
```

Expected: A window opens showing the Tauri + React starter page.

**Step 3: Commit**

```bash
git add git-archiver-v2/
git commit -m "scaffold: create Tauri v2 project with React+TypeScript"
```

### Task 1.2: Configure Rust Project Structure

**Files:**
- Modify: `git-archiver-v2/src-tauri/Cargo.toml`
- Create: `git-archiver-v2/src-tauri/src/error.rs`
- Create: `git-archiver-v2/src-tauri/src/models.rs`
- Create: `git-archiver-v2/src-tauri/src/db/mod.rs`
- Create: `git-archiver-v2/src-tauri/src/db/migrations.rs`
- Create: `git-archiver-v2/src-tauri/src/core/mod.rs`
- Create: `git-archiver-v2/src-tauri/src/commands/mod.rs`
- Modify: `git-archiver-v2/src-tauri/src/main.rs` (or `lib.rs` depending on Tauri v2 scaffold)

**Step 1: Add all Rust dependencies to Cargo.toml**

Add under `[dependencies]`:

```toml
# Async runtime
tokio = { version = "1", features = ["full"] }

# Database
rusqlite = { version = "0.31", features = ["bundled"] }

# Git operations
git2 = "0.19"

# HTTP client
reqwest = { version = "0.12", features = ["json"] }

# Archive creation
tar = "0.4"
xz2 = "0.1"

# Serialization
serde = { version = "1", features = ["derive"] }
serde_json = "1"

# Error handling
thiserror = "2"

# Concurrency
dashmap = "6"
tokio-util = "0.7"

# Time
chrono = { version = "0.4", features = ["serde"] }

# Keychain
keyring = "3"

# Hashing
md-5 = "0.10"

# Logging
log = "0.4"
env_logger = "0.11"
```

Add under `[dev-dependencies]`:

```toml
tempfile = "3"
mockito = "1"
```

**Step 2: Create module skeleton files**

Create empty module files with just the module declarations:

`src-tauri/src/error.rs`:
```rust
use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Error, Serialize)]
#[serde(tag = "kind", content = "message")]
pub enum AppError {
    #[error("Repository already exists: {0}")]
    DuplicateRepo(String),
    #[error("Invalid GitHub URL: {0}")]
    InvalidUrl(String),
    #[error("Git operation failed: {0}")]
    GitError(String),
    #[error("GitHub API error: {0}")]
    ApiError(String),
    #[error("Rate limited -- resets at {0}")]
    RateLimited(String),
    #[error("Archive operation failed: {0}")]
    ArchiveError(String),
    #[error("Database error: {0}")]
    DbError(String),
    #[error("Task already in progress for this repository")]
    AlreadyInProgress,
    #[error("Task was cancelled")]
    Cancelled,
    #[error("Keychain error: {0}")]
    KeychainError(String),
    #[error("{0}")]
    Other(String),
}

impl From<rusqlite::Error> for AppError {
    fn from(e: rusqlite::Error) -> Self {
        AppError::DbError(e.to_string())
    }
}

impl From<git2::Error> for AppError {
    fn from(e: git2::Error) -> Self {
        AppError::GitError(e.to_string())
    }
}

impl From<reqwest::Error> for AppError {
    fn from(e: reqwest::Error) -> Self {
        AppError::ApiError(e.to_string())
    }
}
```

`src-tauri/src/models.rs`:
```rust
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RepoStatus {
    Pending,
    Active,
    Archived,
    Deleted,
    Error,
}

impl RepoStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            RepoStatus::Pending => "pending",
            RepoStatus::Active => "active",
            RepoStatus::Archived => "archived",
            RepoStatus::Deleted => "deleted",
            RepoStatus::Error => "error",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "pending" => Some(RepoStatus::Pending),
            "active" => Some(RepoStatus::Active),
            "archived" => Some(RepoStatus::Archived),
            "deleted" => Some(RepoStatus::Deleted),
            "error" => Some(RepoStatus::Error),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Repository {
    pub id: i64,
    pub owner: String,
    pub name: String,
    pub url: String,
    pub description: Option<String>,
    pub status: RepoStatus,
    pub is_private: bool,
    pub local_path: Option<String>,
    pub last_cloned: Option<DateTime<Utc>>,
    pub last_updated: Option<DateTime<Utc>>,
    pub last_checked: Option<DateTime<Utc>>,
    pub error_message: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Archive {
    pub id: i64,
    pub repo_id: i64,
    pub filename: String,
    pub file_path: String,
    pub size_bytes: u64,
    pub file_count: u32,
    pub is_incremental: bool,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TaskStage {
    Cloning,
    Fetching,
    Archiving,
    Done,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskProgress {
    pub repo_id: i64,
    pub repo_url: String,
    pub stage: TaskStage,
    pub progress_pct: Option<f32>,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    pub max_concurrent_operations: u32,
    pub auto_update_enabled: bool,
    pub auto_update_interval_hours: u32,
    pub data_path: String,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            max_concurrent_operations: 4,
            auto_update_enabled: true,
            auto_update_interval_hours: 24,
            data_path: "data".to_string(),
        }
    }
}
```

`src-tauri/src/db/mod.rs`:
```rust
pub mod migrations;
```

`src-tauri/src/db/migrations.rs`:
```rust
// Will be implemented in Milestone 2
```

`src-tauri/src/core/mod.rs`:
```rust
// Will be implemented in Milestones 3-6
```

`src-tauri/src/commands/mod.rs`:
```rust
// Will be implemented in Milestone 7
```

Update `src-tauri/src/main.rs` (or `lib.rs`) to declare modules:

```rust
mod commands;
mod core;
mod db;
mod error;
mod models;
```

**Step 3: Verify it compiles**

```bash
cd git-archiver-v2/src-tauri
cargo build
```

Expected: Successful compilation with possible warnings about unused code.

**Step 4: Commit**

```bash
git add -A
git commit -m "scaffold: add Rust dependencies and module skeleton"
```

### Task 1.3: Configure React Frontend with shadcn/ui and Dark Mode

**Files:**
- Modify: `git-archiver-v2/package.json`
- Modify: `git-archiver-v2/src/App.tsx`
- Create: `git-archiver-v2/src/styles/globals.css`
- Create: `git-archiver-v2/components.json`
- Modify: `git-archiver-v2/tailwind.config.ts`

**Step 1: Install frontend dependencies**

```bash
cd git-archiver-v2
pnpm add @tanstack/react-table zustand @tauri-apps/api next-themes lucide-react sonner
pnpm add -D tailwindcss postcss autoprefixer @types/node
pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

**Step 2: Initialize Tailwind**

```bash
pnpm dlx tailwindcss init -p
```

**Step 3: Initialize shadcn/ui**

```bash
pnpm dlx shadcn@latest init
```

Select: TypeScript, Default style, CSS variables for colors, `src/styles/globals.css` for global CSS.

**Step 4: Add shadcn components we need**

```bash
pnpm dlx shadcn@latest add button input badge dialog dropdown-menu slider toast table sheet
```

**Step 5: Set up next-themes for dark mode**

Update `src/App.tsx` to wrap with ThemeProvider:

```tsx
import { ThemeProvider } from "next-themes";

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="min-h-screen bg-background text-foreground">
        <h1 className="text-2xl font-bold p-4">Git Archiver</h1>
        <p className="px-4 text-muted-foreground">Ready to build.</p>
      </div>
    </ThemeProvider>
  );
}

export default App;
```

**Step 6: Add a vitest config and placeholder test**

Create `git-archiver-v2/vitest.config.ts`:

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test-setup.ts",
  },
});
```

Create `git-archiver-v2/src/test-setup.ts`:

```typescript
import "@testing-library/jest-dom";
```

Create `git-archiver-v2/src/__tests__/app.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "../App";

describe("App", () => {
  it("renders the app title", () => {
    render(<App />);
    expect(screen.getByText("Git Archiver")).toBeInTheDocument();
  });
});
```

Add to `package.json` scripts:

```json
"test": "vitest run",
"test:watch": "vitest"
```

**Step 7: Verify both test suites pass**

```bash
cd git-archiver-v2
pnpm test                          # Frontend tests
cd src-tauri && cargo test         # Rust tests (just compilation check for now)
```

**Step 8: Verify dev mode opens with themed UI**

```bash
cd git-archiver-v2
pnpm tauri dev
```

Expected: Window shows "Git Archiver" heading with proper theming.

**Step 9: Commit**

```bash
git add -A
git commit -m "scaffold: configure shadcn/ui, dark mode, and test infrastructure"
```

---

## Milestone 2: Database Layer

**Goal:** A fully tested SQLite database layer with migrations, repo CRUD, archive CRUD, and settings CRUD. All operations tested against in-memory SQLite.

### Task 2.1: Database Migrations

**Files:**
- Create: `git-archiver-v2/src-tauri/migrations/001_initial.sql`
- Modify: `git-archiver-v2/src-tauri/src/db/migrations.rs`

**Step 1: Write the failing test**

In `db/migrations.rs`:

```rust
#[cfg(test)]
mod tests {
    use rusqlite::Connection;
    use super::*;

    #[test]
    fn test_run_migrations_creates_tables() {
        let conn = Connection::open_in_memory().unwrap();
        run_migrations(&conn).unwrap();

        // Verify repositories table exists
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM repositories", [], |row| row.get(0))
            .unwrap();
        assert_eq!(count, 0);
    }

    #[test]
    fn test_run_migrations_idempotent() {
        let conn = Connection::open_in_memory().unwrap();
        run_migrations(&conn).unwrap();
        run_migrations(&conn).unwrap(); // Should not error
    }
}
```

**Step 2: Run test to verify it fails**

```bash
cd git-archiver-v2/src-tauri
cargo test db::migrations::tests
```

Expected: FAIL — `run_migrations` not defined.

**Step 3: Implement migrations**

Create `migrations/001_initial.sql` with the full schema from the design doc.

Implement `run_migrations()` in `db/migrations.rs`:
- Read `schema_version` table (create if not exists)
- Check current version
- Apply each migration SQL that hasn't been applied
- Update schema_version

```rust
use rusqlite::Connection;
use crate::error::AppError;

const MIGRATION_001: &str = include_str!("../../migrations/001_initial.sql");

pub fn run_migrations(conn: &Connection) -> Result<(), AppError> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);"
    )?;

    let current_version: i64 = conn
        .query_row(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version",
            [],
            |row| row.get(0),
        )
        .unwrap_or(0);

    if current_version < 1 {
        conn.execute_batch(MIGRATION_001)?;
        conn.execute("INSERT INTO schema_version (version) VALUES (1)", [])?;
    }

    // Enable WAL mode for concurrent reads
    conn.pragma_update(None, "journal_mode", "WAL")?;

    Ok(())
}
```

**Step 4: Run tests to verify they pass**

```bash
cargo test db::migrations::tests -- --nocapture
```

Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add SQLite database migrations"
```

### Task 2.2: Repository CRUD Database Operations

**Files:**
- Create: `git-archiver-v2/src-tauri/src/db/repos.rs`
- Modify: `git-archiver-v2/src-tauri/src/db/mod.rs`

**Step 1: Write failing tests**

Test cases needed:
- `test_insert_repo` — insert a repo, verify it's retrievable
- `test_insert_duplicate_url_fails` — inserting same URL twice returns `DuplicateRepo`
- `test_list_repos_empty` — empty DB returns empty vec
- `test_list_repos_with_filter` — filter by status works
- `test_update_repo_status` — change status from pending to active
- `test_delete_repo` — delete removes from DB
- `test_get_repo_by_id` — fetch by primary key

Each test creates an in-memory DB, runs migrations, then exercises one function.

**Step 2: Run tests, verify they fail**

```bash
cargo test db::repos::tests
```

**Step 3: Implement repo CRUD**

Functions to implement in `db/repos.rs`:

```rust
pub fn insert_repo(conn: &Connection, owner: &str, name: &str, url: &str) -> Result<Repository, AppError>
pub fn get_repo_by_id(conn: &Connection, id: i64) -> Result<Option<Repository>, AppError>
pub fn list_repos(conn: &Connection, status_filter: Option<&RepoStatus>) -> Result<Vec<Repository>, AppError>
pub fn update_repo_status(conn: &Connection, id: i64, status: &RepoStatus, error_msg: Option<&str>) -> Result<(), AppError>
pub fn update_repo_metadata(conn: &Connection, id: i64, description: Option<&str>, is_private: bool) -> Result<(), AppError>
pub fn update_repo_timestamps(conn: &Connection, id: i64, cloned: Option<DateTime<Utc>>, updated: Option<DateTime<Utc>>, checked: Option<DateTime<Utc>>) -> Result<(), AppError>
pub fn delete_repo(conn: &Connection, id: i64) -> Result<(), AppError>
pub fn get_repo_by_url(conn: &Connection, url: &str) -> Result<Option<Repository>, AppError>
```

Map SQLite rows to `Repository` struct using a helper `fn row_to_repo(row: &Row) -> Result<Repository, rusqlite::Error>`.

**Step 4: Run tests, verify they pass**

```bash
cargo test db::repos::tests -- --nocapture
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add repository CRUD database operations"
```

### Task 2.3: Archive CRUD Database Operations

**Files:**
- Create: `git-archiver-v2/src-tauri/src/db/archives.rs`
- Modify: `git-archiver-v2/src-tauri/src/db/mod.rs`

**Step 1: Write failing tests**

Test cases:
- `test_insert_archive` — insert archive record, verify retrievable
- `test_list_archives_for_repo` — returns only archives for given repo_id
- `test_delete_archive` — removes archive record
- `test_cascade_delete` — deleting a repo cascades to its archives

**Step 2: Implement archive CRUD**

```rust
pub fn insert_archive(conn: &Connection, repo_id: i64, filename: &str, file_path: &str, size_bytes: u64, file_count: u32, is_incremental: bool) -> Result<Archive, AppError>
pub fn list_archives(conn: &Connection, repo_id: i64) -> Result<Vec<Archive>, AppError>
pub fn get_archive_by_id(conn: &Connection, id: i64) -> Result<Option<Archive>, AppError>
pub fn delete_archive(conn: &Connection, id: i64) -> Result<(), AppError>
```

**Step 3: Run tests, verify pass**

**Step 4: Commit**

```bash
git commit -m "feat: add archive CRUD database operations"
```

### Task 2.4: Settings and File Hash Database Operations

**Files:**
- Create: `git-archiver-v2/src-tauri/src/db/settings.rs`
- Create: `git-archiver-v2/src-tauri/src/db/file_hashes.rs`
- Modify: `git-archiver-v2/src-tauri/src/db/mod.rs`

**Step 1: Write failing tests**

Settings tests:
- `test_get_setting_missing_returns_none`
- `test_set_and_get_setting`
- `test_set_overwrites_existing`

File hash tests:
- `test_upsert_file_hash`
- `test_get_hashes_for_repo`
- `test_clear_hashes_on_repo_delete` (cascade)

**Step 2: Implement**

Settings:
```rust
pub fn get_setting(conn: &Connection, key: &str) -> Result<Option<String>, AppError>
pub fn set_setting(conn: &Connection, key: &str, value: &str) -> Result<(), AppError>
pub fn get_all_settings(conn: &Connection) -> Result<AppSettings, AppError>
pub fn save_all_settings(conn: &Connection, settings: &AppSettings) -> Result<(), AppError>
```

File hashes:
```rust
pub fn upsert_file_hash(conn: &Connection, repo_id: i64, file_path: &str, md5_hash: &str) -> Result<(), AppError>
pub fn get_file_hashes(conn: &Connection, repo_id: i64) -> Result<HashMap<String, String>, AppError>
pub fn clear_file_hashes(conn: &Connection, repo_id: i64) -> Result<(), AppError>
```

**Step 3: Run all DB tests**

```bash
cargo test db:: -- --nocapture
```

Expected: All pass.

**Step 4: Commit**

```bash
git commit -m "feat: add settings and file hash database operations"
```

---

## Milestone 3: URL Validation & Core Utilities

**Goal:** URL parsing and validation that matches the Python version's behavior, with comprehensive tests.

### Task 3.1: URL Validation Module

**Files:**
- Create: `git-archiver-v2/src-tauri/src/core/url.rs`
- Modify: `git-archiver-v2/src-tauri/src/core/mod.rs`

**Step 1: Write failing tests**

Port and expand from the Python `test_utils.py`:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_github_urls() {
        assert!(validate_repo_url("https://github.com/owner/repo").is_ok());
        assert!(validate_repo_url("https://github.com/owner/repo.git").is_ok());
        assert!(validate_repo_url("https://github.com/owner/repo/").is_ok());
        assert!(validate_repo_url("http://github.com/owner/repo").is_ok());
    }

    #[test]
    fn test_invalid_urls() {
        assert!(validate_repo_url("").is_err());
        assert!(validate_repo_url("not-a-url").is_err());
        assert!(validate_repo_url("https://gitlab.com/owner/repo").is_err());
        assert!(validate_repo_url("https://github.com/owner").is_err());
        assert!(validate_repo_url("https://github.com/owner/").is_err());
    }

    #[test]
    fn test_normalize_url() {
        assert_eq!(normalize_repo_url("https://github.com/Owner/Repo.git"), "https://github.com/owner/repo");
        assert_eq!(normalize_repo_url("https://github.com/owner/repo/"), "https://github.com/owner/repo");
        assert_eq!(normalize_repo_url("http://github.com/owner/repo"), "https://github.com/owner/repo");
    }

    #[test]
    fn test_extract_owner_repo() {
        let (owner, repo) = extract_owner_repo("https://github.com/torvalds/linux").unwrap();
        assert_eq!(owner, "torvalds");
        assert_eq!(repo, "linux");
    }
}
```

**Step 2: Implement**

```rust
pub fn validate_repo_url(url: &str) -> Result<(), AppError>
pub fn normalize_repo_url(url: &str) -> String
pub fn extract_owner_repo(url: &str) -> Result<(String, String), AppError>
```

**Step 3: Run tests, verify pass. Commit.**

```bash
git commit -m "feat: add URL validation and normalization"
```

---

## Milestone 4: Git Operations

**Goal:** Clone and pull repositories using git2, with progress callbacks and cancellation support.

### Task 4.1: Git Clone with Progress

**Files:**
- Create: `git-archiver-v2/src-tauri/src/core/git.rs`
- Modify: `git-archiver-v2/src-tauri/src/core/mod.rs`

**Step 1: Write failing test**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_clone_small_repo() {
        let tmp = TempDir::new().unwrap();
        let dest = tmp.path().join("test-repo");

        // Clone a tiny known-good public repo
        let result = clone_repo(
            "https://github.com/octocat/Hello-World",
            &dest,
            None, // no progress callback for test
        );

        assert!(result.is_ok());
        assert!(dest.join(".git").exists());
    }

    #[test]
    fn test_clone_invalid_url_fails() {
        let tmp = TempDir::new().unwrap();
        let dest = tmp.path().join("bad-repo");

        let result = clone_repo("https://github.com/nonexistent/repo-that-does-not-exist-12345", &dest, None);
        assert!(result.is_err());
    }
}
```

Note: These are integration tests that hit the network. Mark them with `#[ignore]` for CI and run with `cargo test -- --ignored` locally.

**Step 2: Implement git clone**

```rust
use git2::{build::RepoBuilder, FetchOptions, RemoteCallbacks, Progress};
use std::path::Path;
use tokio_util::sync::CancellationToken;

pub fn clone_repo<F>(
    url: &str,
    dest: &Path,
    progress_callback: Option<F>,
) -> Result<(), AppError>
where
    F: Fn(f32, &str) + Send + 'static,
{
    let mut callbacks = RemoteCallbacks::new();

    if let Some(cb) = progress_callback {
        callbacks.transfer_progress(move |progress: Progress| {
            let pct = if progress.total_objects() > 0 {
                progress.received_objects() as f32 / progress.total_objects() as f32
            } else {
                0.0
            };
            let msg = format!(
                "{}/{} objects, {} bytes",
                progress.received_objects(),
                progress.total_objects(),
                progress.received_bytes()
            );
            cb(pct, &msg);
            true // return false to cancel
        });
    }

    let mut fo = FetchOptions::new();
    fo.remote_callbacks(callbacks);
    fo.depth(1); // shallow clone

    RepoBuilder::new()
        .fetch_options(fo)
        .clone(url, dest)?;

    Ok(())
}
```

**Step 3: Run tests (including ignored)**

```bash
cargo test core::git::tests -- --ignored --nocapture
```

**Step 4: Commit**

```bash
git commit -m "feat: add git clone with progress callbacks via git2"
```

### Task 4.2: Git Fetch and Pull

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/core/git.rs`

**Step 1: Write failing tests**

```rust
#[test]
#[ignore] // network test
fn test_fetch_and_check_updates() {
    let tmp = TempDir::new().unwrap();
    let dest = tmp.path().join("test-repo");
    clone_repo("https://github.com/octocat/Hello-World", &dest, None::<fn(f32, &str)>).unwrap();

    let has_updates = fetch_and_check_updates(&dest).unwrap();
    // Freshly cloned, should be up to date
    assert!(!has_updates);
}
```

**Step 2: Implement**

```rust
pub fn fetch_and_check_updates(repo_path: &Path) -> Result<bool, AppError>
pub fn pull_repo(repo_path: &Path) -> Result<bool, AppError>
```

`fetch_and_check_updates`: Open repo, fetch origin, compare local HEAD to remote HEAD.
`pull_repo`: Fetch + fast-forward merge. Return true if files changed.

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add git fetch and pull operations"
```

---

## Milestone 5: Archive Operations

**Goal:** Create and extract `.tar.xz` archives in pure Rust, with incremental support via file hashing.

### Task 5.1: File Hashing

**Files:**
- Create: `git-archiver-v2/src-tauri/src/core/hasher.rs`
- Modify: `git-archiver-v2/src-tauri/src/core/mod.rs`

**Step 1: Write failing tests**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use std::fs;

    #[test]
    fn test_hash_directory() {
        let tmp = TempDir::new().unwrap();
        fs::write(tmp.path().join("file1.txt"), "hello").unwrap();
        fs::write(tmp.path().join("file2.txt"), "world").unwrap();
        fs::create_dir(tmp.path().join("subdir")).unwrap();
        fs::write(tmp.path().join("subdir/file3.txt"), "nested").unwrap();

        let hashes = hash_directory(tmp.path()).unwrap();

        assert_eq!(hashes.len(), 3);
        assert!(hashes.contains_key("file1.txt"));
        assert!(hashes.contains_key("subdir/file3.txt"));
    }

    #[test]
    fn test_detect_changed_files() {
        let old: HashMap<String, String> = [
            ("a.txt".into(), "hash1".into()),
            ("b.txt".into(), "hash2".into()),
            ("c.txt".into(), "hash3".into()),
        ].into();
        let new: HashMap<String, String> = [
            ("a.txt".into(), "hash1".into()),  // unchanged
            ("b.txt".into(), "hash_new".into()), // changed
            ("d.txt".into(), "hash4".into()),   // new file
        ].into();

        let changed = detect_changed_files(&old, &new);
        assert_eq!(changed.len(), 2);
        assert!(changed.contains(&"b.txt".to_string()));
        assert!(changed.contains(&"d.txt".to_string()));
    }
}
```

**Step 2: Implement**

```rust
pub fn hash_directory(dir: &Path) -> Result<HashMap<String, String>, AppError>
pub fn detect_changed_files(old_hashes: &HashMap<String, String>, new_hashes: &HashMap<String, String>) -> Vec<String>
```

Walk directory, compute MD5 of each file, store as `relative_path -> hex_hash`. Exclude `.git` and `versions` directories.

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add file hashing for incremental archive detection"
```

### Task 5.2: Archive Creation and Extraction

**Files:**
- Create: `git-archiver-v2/src-tauri/src/core/archive.rs`
- Modify: `git-archiver-v2/src-tauri/src/core/mod.rs`

**Step 1: Write failing tests**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use std::fs;

    #[test]
    fn test_create_full_archive() {
        let tmp = TempDir::new().unwrap();
        let src = tmp.path().join("repo");
        fs::create_dir(&src).unwrap();
        fs::write(src.join("file1.txt"), "hello").unwrap();
        fs::write(src.join("file2.txt"), "world").unwrap();

        let archive_path = tmp.path().join("test.tar.xz");
        let info = create_archive(&src, &archive_path, None).unwrap();

        assert!(archive_path.exists());
        assert_eq!(info.file_count, 2);
        assert!(info.size_bytes > 0);
    }

    #[test]
    fn test_create_incremental_archive() {
        let tmp = TempDir::new().unwrap();
        let src = tmp.path().join("repo");
        fs::create_dir(&src).unwrap();
        fs::write(src.join("changed.txt"), "new content").unwrap();
        fs::write(src.join("unchanged.txt"), "same").unwrap();

        let changed_files = vec!["changed.txt".to_string()];
        let archive_path = tmp.path().join("incremental.tar.xz");
        let info = create_archive(&src, &archive_path, Some(&changed_files)).unwrap();

        assert!(archive_path.exists());
        assert_eq!(info.file_count, 1); // only the changed file
    }

    #[test]
    fn test_extract_archive() {
        let tmp = TempDir::new().unwrap();
        let src = tmp.path().join("repo");
        fs::create_dir(&src).unwrap();
        fs::write(src.join("file1.txt"), "hello").unwrap();

        let archive_path = tmp.path().join("test.tar.xz");
        create_archive(&src, &archive_path, None).unwrap();

        let extract_dir = tmp.path().join("extracted");
        extract_archive(&archive_path, &extract_dir).unwrap();

        assert_eq!(fs::read_to_string(extract_dir.join("file1.txt")).unwrap(), "hello");
    }
}
```

**Step 2: Implement**

```rust
pub struct ArchiveInfo {
    pub size_bytes: u64,
    pub file_count: u32,
}

pub fn create_archive(
    source_dir: &Path,
    archive_path: &Path,
    changed_files_only: Option<&[String]>,
) -> Result<ArchiveInfo, AppError>

pub fn extract_archive(archive_path: &Path, dest_dir: &Path) -> Result<(), AppError>

pub fn delete_archive_file(archive_path: &Path) -> Result<(), AppError>
```

Use `tar::Builder` writing into `xz2::write::XzEncoder`. For extraction, `xz2::read::XzDecoder` into `tar::Archive`.

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add tar.xz archive creation and extraction"
```

---

## Milestone 6: GitHub API Client

**Goal:** A tested GitHub API client with token auth, rate limiting, REST + GraphQL support.

### Task 6.1: REST API Client

**Files:**
- Create: `git-archiver-v2/src-tauri/src/core/github_api.rs`
- Modify: `git-archiver-v2/src-tauri/src/core/mod.rs`

**Step 1: Write failing tests using mockito**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use mockito::{Server, Mock};

    #[tokio::test]
    async fn test_get_repo_info_success() {
        let mut server = Server::new_async().await;
        let mock = server.mock("GET", "/repos/owner/repo")
            .with_status(200)
            .with_body(r#"{"description": "A test repo", "archived": false, "private": false}"#)
            .create_async().await;

        let client = GitHubClient::new(Some("test-token".into()), Some(server.url()));
        let info = client.get_repo_info("owner", "repo").await.unwrap();

        assert_eq!(info.description, Some("A test repo".into()));
        assert!(!info.archived);
        mock.assert();
    }

    #[tokio::test]
    async fn test_get_repo_info_404() {
        let mut server = Server::new_async().await;
        server.mock("GET", "/repos/owner/gone")
            .with_status(404)
            .create_async().await;

        let client = GitHubClient::new(Some("test-token".into()), Some(server.url()));
        let info = client.get_repo_info("owner", "gone").await.unwrap();

        assert!(info.not_found);
    }

    #[tokio::test]
    async fn test_rate_limit_check() {
        let mut server = Server::new_async().await;
        server.mock("GET", "/rate_limit")
            .with_status(200)
            .with_body(r#"{"resources":{"core":{"limit":5000,"remaining":4999,"reset":1700000000}}}"#)
            .create_async().await;

        let client = GitHubClient::new(Some("test-token".into()), Some(server.url()));
        let rl = client.get_rate_limit().await.unwrap();

        assert_eq!(rl.remaining, 4999);
    }

    #[tokio::test]
    async fn test_auth_header_included() {
        let mut server = Server::new_async().await;
        let mock = server.mock("GET", "/repos/owner/repo")
            .match_header("Authorization", "token my-token")
            .with_status(200)
            .with_body(r#"{"description": null, "archived": false, "private": false}"#)
            .create_async().await;

        let client = GitHubClient::new(Some("my-token".into()), Some(server.url()));
        client.get_repo_info("owner", "repo").await.unwrap();
        mock.assert();
    }
}
```

**Step 2: Implement GitHubClient**

```rust
pub struct GitHubClient {
    client: reqwest::Client,
    token: Option<String>,
    base_url: String,
}

pub struct RepoInfo {
    pub description: Option<String>,
    pub archived: bool,
    pub is_private: bool,
    pub not_found: bool,
}

pub struct RateLimitInfo {
    pub limit: u32,
    pub remaining: u32,
    pub reset: i64,
}

impl GitHubClient {
    pub fn new(token: Option<String>, base_url: Option<String>) -> Self
    pub async fn get_repo_info(&self, owner: &str, repo: &str) -> Result<RepoInfo, AppError>
    pub async fn get_rate_limit(&self) -> Result<RateLimitInfo, AppError>
}
```

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add GitHub REST API client with auth and rate limiting"
```

### Task 6.2: GraphQL Batch Queries

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/core/github_api.rs`

**Step 1: Write failing test**

```rust
#[tokio::test]
async fn test_batch_get_repo_info() {
    let mut server = Server::new_async().await;
    server.mock("POST", "/graphql")
        .with_status(200)
        .with_body(r#"{"data":{"repo0":{"description":"Desc A","isArchived":false,"isPrivate":false},"repo1":{"description":"Desc B","isArchived":true,"isPrivate":false}}}"#)
        .create_async().await;

    let client = GitHubClient::new(Some("test-token".into()), Some(server.url()));
    let repos = vec![("owner1", "repo1"), ("owner2", "repo2")];
    let results = client.batch_get_repo_info(&repos).await.unwrap();

    assert_eq!(results.len(), 2);
    assert_eq!(results[0].description, Some("Desc A".into()));
    assert!(results[1].archived);
}
```

**Step 2: Implement**

```rust
impl GitHubClient {
    pub async fn batch_get_repo_info(&self, repos: &[(&str, &str)]) -> Result<Vec<RepoInfo>, AppError>
}
```

Build GraphQL query with aliased fields (`repo0`, `repo1`, ...), send POST to `/graphql`, parse response. Fall back to individual REST calls if no token or if GraphQL fails.

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add GraphQL batch repo info queries"
```

### Task 6.3: Status Detection (Archived/Deleted)

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/core/github_api.rs`

**Step 1: Write failing test**

```rust
#[tokio::test]
async fn test_detect_repo_statuses() {
    // Mock: repo1 is active, repo2 is archived, repo3 returns 404
    // ...
    let statuses = client.detect_repo_statuses(&repos).await.unwrap();
    assert_eq!(statuses[0], RepoStatus::Active);
    assert_eq!(statuses[1], RepoStatus::Archived);
    assert_eq!(statuses[2], RepoStatus::Deleted);
}
```

**Step 2: Implement**

```rust
impl GitHubClient {
    pub async fn detect_repo_statuses(
        &self,
        repos: &[(String, String)], // (owner, name)
    ) -> Result<Vec<(String, String, RepoStatus)>, AppError>
}
```

Use batch GraphQL if token available, fall back to individual REST.

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add batch repository status detection"
```

---

## Milestone 7: Task Manager

**Goal:** An async task queue with configurable concurrency, deduplication, and cancellation.

### Task 7.1: Task Manager Core

**Files:**
- Create: `git-archiver-v2/src-tauri/src/core/task_manager.rs`
- Modify: `git-archiver-v2/src-tauri/src/core/mod.rs`

**Step 1: Write failing tests**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use tokio::sync::mpsc;

    #[tokio::test]
    async fn test_enqueue_and_dedup() {
        let (manager, mut rx) = TaskManager::new(4);

        manager.enqueue(Task::Clone(1)).await.unwrap();
        assert!(manager.enqueue(Task::Clone(1)).await.is_err()); // duplicate

        let task = rx.recv().await.unwrap();
        assert!(matches!(task, Task::Clone(1)));
    }

    #[tokio::test]
    async fn test_cancel_task() {
        let (manager, _rx) = TaskManager::new(4);
        manager.enqueue(Task::Clone(42)).await.unwrap();

        manager.cancel(42).await;
        assert!(!manager.is_active(42));
    }

    #[tokio::test]
    async fn test_cancel_all() {
        let (manager, _rx) = TaskManager::new(4);
        manager.enqueue(Task::Clone(1)).await.unwrap();
        manager.enqueue(Task::Clone(2)).await.unwrap();

        manager.cancel_all().await;
        assert_eq!(manager.active_count(), 0);
    }
}
```

**Step 2: Implement TaskManager**

```rust
pub struct TaskManager {
    tx: mpsc::Sender<Task>,
    active_tasks: DashMap<i64, CancellationToken>,
    semaphore: Arc<Semaphore>,
}

impl TaskManager {
    pub fn new(max_concurrent: u32) -> (Arc<Self>, mpsc::Receiver<Task>)
    pub async fn enqueue(&self, task: Task) -> Result<(), AppError>
    pub async fn cancel(&self, repo_id: i64)
    pub async fn cancel_all(&self)
    pub fn is_active(&self, repo_id: i64) -> bool
    pub fn active_count(&self) -> usize
    pub fn mark_complete(&self, repo_id: i64)
    pub fn get_cancellation_token(&self, repo_id: i64) -> Option<CancellationToken>
}
```

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add async task manager with deduplication and cancellation"
```

---

## Milestone 8: Tauri Commands — Wire Backend to Frontend

**Goal:** All Tauri `#[tauri::command]` functions implemented and the worker loop spawned at startup. The app compiles and runs with the full backend wired up.

### Task 8.1: App State and Command Registration

**Files:**
- Modify: `git-archiver-v2/src-tauri/src/main.rs` (or `lib.rs`)
- Create: `git-archiver-v2/src-tauri/src/state.rs`

**Step 1: Create AppState**

```rust
// state.rs
use std::sync::Arc;
use tokio::sync::Mutex;
use rusqlite::Connection;

pub struct AppState {
    pub db: Arc<Mutex<Connection>>,
    pub task_manager: Arc<TaskManager>,
    pub github_client: Arc<GitHubClient>,
}
```

**Step 2: Update main.rs to initialize state and register commands**

```rust
fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // Initialize SQLite
            let db_path = app.path().app_data_dir()?.join("git-archiver.db");
            let conn = Connection::open(&db_path)?;
            run_migrations(&conn)?;

            // Initialize GitHub client
            let token = get_token_from_keychain().ok();
            let github_client = Arc::new(GitHubClient::new(token, None));

            // Initialize task manager
            let (task_manager, rx) = TaskManager::new(4);

            let state = AppState {
                db: Arc::new(Mutex::new(conn)),
                task_manager,
                github_client,
            };

            app.manage(state);

            // Spawn worker loop
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(worker_loop(rx, app_handle));

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::repos::add_repo,
            commands::repos::list_repos,
            commands::repos::delete_repo,
            commands::repos::import_from_file,
            commands::tasks::clone_repo,
            commands::tasks::update_repo,
            commands::tasks::update_all,
            commands::tasks::stop_all_tasks,
            commands::archives::list_archives,
            commands::archives::extract_archive,
            commands::archives::delete_archive,
            commands::settings::get_settings,
            commands::settings::save_settings,
            commands::settings::check_rate_limit,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

**Step 3: Verify it compiles**

```bash
cargo build
```

**Step 4: Commit**

```bash
git commit -m "feat: wire app state and register Tauri commands"
```

### Task 8.2: Repository Commands

**Files:**
- Create: `git-archiver-v2/src-tauri/src/commands/repos.rs`
- Modify: `git-archiver-v2/src-tauri/src/commands/mod.rs`

**Step 1: Implement Tauri commands for repo CRUD**

```rust
#[tauri::command]
pub async fn add_repo(
    url: String,
    state: tauri::State<'_, AppState>,
) -> Result<Repository, AppError> {
    let url = normalize_repo_url(&url);
    validate_repo_url(&url)?;
    let (owner, name) = extract_owner_repo(&url)?;
    let db = state.db.lock().await;
    insert_repo(&db, &owner, &name, &url)
}

#[tauri::command]
pub async fn list_repos(
    status_filter: Option<String>,
    state: tauri::State<'_, AppState>,
) -> Result<Vec<Repository>, AppError> { ... }

#[tauri::command]
pub async fn delete_repo(
    id: i64,
    remove_files: bool,
    state: tauri::State<'_, AppState>,
) -> Result<(), AppError> { ... }

#[tauri::command]
pub async fn import_from_file(
    path: String,
    state: tauri::State<'_, AppState>,
) -> Result<BulkAddResult, AppError> { ... }
```

**Step 2: Verify compiles, commit.**

```bash
git commit -m "feat: add repository Tauri commands"
```

### Task 8.3: Task Commands and Worker Loop

**Files:**
- Create: `git-archiver-v2/src-tauri/src/commands/tasks.rs`
- Create: `git-archiver-v2/src-tauri/src/core/worker.rs`

**Step 1: Implement the worker loop**

```rust
// core/worker.rs
pub async fn worker_loop(
    mut rx: mpsc::Receiver<Task>,
    app_handle: AppHandle,
    db: Arc<Mutex<Connection>>,
    github_client: Arc<GitHubClient>,
    task_manager: Arc<TaskManager>,
    semaphore: Arc<Semaphore>,
) {
    while let Some(task) = rx.recv().await {
        let permit = semaphore.clone().acquire_owned().await.unwrap();
        let handle = app_handle.clone();
        let db = db.clone();
        let gh = github_client.clone();
        let tm = task_manager.clone();

        tokio::spawn(async move {
            match task {
                Task::Clone(repo_id) => {
                    handle_clone(repo_id, &handle, &db, &gh, &tm).await;
                }
                Task::Update(repo_id) => {
                    handle_update(repo_id, &handle, &db, &gh, &tm).await;
                }
                Task::UpdateAll { include_archived } => {
                    handle_update_all(include_archived, &handle, &db, &gh, &tm).await;
                }
                Task::RefreshStatuses => {
                    handle_refresh(&handle, &db, &gh).await;
                }
                Task::Stop => return,
            }
            drop(permit); // release semaphore
        });
    }
}
```

**Step 2: Implement task commands**

```rust
#[tauri::command]
pub async fn clone_repo(id: i64, state: State<'_, AppState>) -> Result<(), AppError> {
    state.task_manager.enqueue(Task::Clone(id)).await
}

#[tauri::command]
pub async fn update_all(include_archived: bool, state: State<'_, AppState>) -> Result<(), AppError> {
    state.task_manager.enqueue(Task::UpdateAll { include_archived }).await
}

#[tauri::command]
pub async fn stop_all_tasks(state: State<'_, AppState>) -> Result<(), AppError> {
    state.task_manager.cancel_all().await;
    Ok(())
}
```

**Step 3: Verify compiles, commit.**

```bash
git commit -m "feat: add task commands and async worker loop"
```

### Task 8.4: Archive and Settings Commands

**Files:**
- Create: `git-archiver-v2/src-tauri/src/commands/archives.rs`
- Create: `git-archiver-v2/src-tauri/src/commands/settings.rs`

**Step 1: Implement remaining commands**

Archives: `list_archives`, `extract_archive`, `delete_archive` — thin wrappers around DB + filesystem operations.

Settings: `get_settings`, `save_settings` — read/write from SQLite settings table. `check_rate_limit` — delegates to `GitHubClient::get_rate_limit()`.

**Step 2: Implement keychain integration for token**

```rust
// In settings commands
#[tauri::command]
pub async fn save_settings(
    settings: AppSettings,
    token: Option<String>,
    state: State<'_, AppState>,
) -> Result<(), AppError> {
    let db = state.db.lock().await;
    save_all_settings(&db, &settings)?;

    if let Some(token) = token {
        let entry = keyring::Entry::new("git-archiver", "github-token")
            .map_err(|e| AppError::KeychainError(e.to_string()))?;
        entry.set_password(&token)
            .map_err(|e| AppError::KeychainError(e.to_string()))?;
    }

    Ok(())
}
```

**Step 3: Verify full backend compiles and `cargo test` passes.**

```bash
cargo build && cargo test
```

**Step 4: Commit**

```bash
git commit -m "feat: add archive and settings Tauri commands with keychain"
```

---

## Milestone 9: Frontend — Core Layout

**Goal:** The main application layout with repo table, add bar, and theme toggle rendered in the Tauri window. Data flows from backend to frontend via invoke().

### Task 9.1: Typed Command Wrappers

**Files:**
- Create: `git-archiver-v2/src/lib/commands.ts`
- Create: `git-archiver-v2/src/lib/types.ts`

**Step 1: Write failing test**

```typescript
// src/lib/__tests__/commands.test.ts
import { describe, it, expect, vi } from "vitest";
import { normalizeRepoUrl, isValidGithubUrl } from "../utils";

describe("URL utilities", () => {
  it("normalizes GitHub URLs", () => {
    expect(normalizeRepoUrl("https://github.com/Owner/Repo.git")).toBe(
      "https://github.com/owner/repo"
    );
  });

  it("validates GitHub URLs", () => {
    expect(isValidGithubUrl("https://github.com/owner/repo")).toBe(true);
    expect(isValidGithubUrl("not-a-url")).toBe(false);
    expect(isValidGithubUrl("https://gitlab.com/owner/repo")).toBe(false);
  });
});
```

**Step 2: Create types and command wrappers**

`src/lib/types.ts` — TypeScript equivalents of Rust models:

```typescript
export type RepoStatus = "pending" | "active" | "archived" | "deleted" | "error";

export interface Repository {
  id: number;
  owner: string;
  name: string;
  url: string;
  description: string | null;
  status: RepoStatus;
  is_private: boolean;
  local_path: string | null;
  last_cloned: string | null;
  last_updated: string | null;
  last_checked: string | null;
  error_message: string | null;
  created_at: string;
}

export interface Archive { ... }
export interface TaskProgress { ... }
export interface AppSettings { ... }
export interface RateLimitInfo { ... }
```

`src/lib/commands.ts` — typed `invoke()` wrappers:

```typescript
import { invoke } from "@tauri-apps/api/core";
import type { Repository, Archive, AppSettings, RateLimitInfo } from "./types";

export async function addRepo(url: string): Promise<Repository> {
  return invoke("add_repo", { url });
}

export async function listRepos(statusFilter?: string): Promise<Repository[]> {
  return invoke("list_repos", { statusFilter });
}

// ... all other commands
```

`src/lib/utils.ts`:

```typescript
export function normalizeRepoUrl(url: string): string { ... }
export function isValidGithubUrl(url: string): boolean { ... }
export function formatRelativeTime(dateStr: string): string { ... }
```

**Step 3: Run tests**

```bash
pnpm test
```

**Step 4: Commit**

```bash
git commit -m "feat: add TypeScript types and typed Tauri command wrappers"
```

### Task 9.2: Zustand Stores

**Files:**
- Create: `git-archiver-v2/src/stores/repo-store.ts`
- Create: `git-archiver-v2/src/stores/task-store.ts`
- Create: `git-archiver-v2/src/stores/settings-store.ts`

**Step 1: Write failing tests**

```typescript
// src/stores/__tests__/repo-store.test.ts
import { describe, it, expect, vi } from "vitest";

// Mock invoke
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

describe("repo store", () => {
  it("loads repos from backend", async () => { ... });
  it("adds a repo optimistically", async () => { ... });
  it("filters repos by status", () => { ... });
  it("searches repos by name", () => { ... });
});
```

**Step 2: Implement stores**

```typescript
// stores/repo-store.ts
import { create } from "zustand";

interface RepoStore {
  repos: Repository[];
  loading: boolean;
  searchQuery: string;
  statusFilter: RepoStatus | null;
  fetchRepos: () => Promise<void>;
  addRepo: (url: string) => Promise<void>;
  deleteRepo: (id: number, removeFiles: boolean) => Promise<void>;
  setSearchQuery: (q: string) => void;
  setStatusFilter: (s: RepoStatus | null) => void;
  filteredRepos: () => Repository[];
}
```

Similar patterns for `task-store` (tracks active tasks + progress events) and `settings-store`.

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add zustand stores for repos, tasks, and settings"
```

### Task 9.3: App Shell with Theme Toggle

**Files:**
- Modify: `git-archiver-v2/src/App.tsx`
- Create: `git-archiver-v2/src/components/theme-toggle.tsx`
- Create: `git-archiver-v2/src/components/app-header.tsx`

**Step 1: Build the app shell**

```tsx
// App.tsx
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { AppHeader } from "./components/app-header";

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="flex flex-col h-screen bg-background text-foreground">
        <AppHeader />
        <main className="flex-1 overflow-hidden p-4">
          {/* Repo table goes here in next task */}
          <p className="text-muted-foreground">Loading...</p>
        </main>
      </div>
      <Toaster />
    </ThemeProvider>
  );
}
```

`AppHeader`: title + theme toggle (sun/moon icon) + settings gear button.

**Step 2: Verify with `pnpm tauri dev`**

Expected: Window shows header with "Git Archiver" title, theme toggle works (switches light/dark), settings button present.

**Step 3: Commit**

```bash
git commit -m "feat: add app shell with header and dark mode toggle"
```

### Task 9.4: Repository Data Table

**Files:**
- Create: `git-archiver-v2/src/components/repo-table/columns.tsx`
- Create: `git-archiver-v2/src/components/repo-table/data-table.tsx`
- Create: `git-archiver-v2/src/components/repo-table/row-actions.tsx`
- Create: `git-archiver-v2/src/components/repo-table/status-badge.tsx`

**Step 1: Write component test**

```typescript
// src/components/repo-table/__tests__/data-table.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DataTable } from "../data-table";
import { columns } from "../columns";

const mockRepos = [
  { id: 1, owner: "torvalds", name: "linux", url: "...", status: "active", ... },
  { id: 2, owner: "rust-lang", name: "rust", url: "...", status: "pending", ... },
];

describe("DataTable", () => {
  it("renders rows for each repo", () => {
    render(<DataTable columns={columns} data={mockRepos} />);
    expect(screen.getByText("torvalds/linux")).toBeInTheDocument();
    expect(screen.getByText("rust-lang/rust")).toBeInTheDocument();
  });

  it("shows status badges", () => {
    render(<DataTable columns={columns} data={mockRepos} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });
});
```

**Step 2: Implement the table**

Build using shadcn/ui's DataTable pattern (wraps @tanstack/react-table):
- Columns: Repository (owner/name), Description, Status (badge), Last Updated (relative time), Actions (dropdown)
- Sortable columns
- Search filtering via the store's `searchQuery`
- Status filter via the store's `statusFilter`
- Pagination (50 per page)

`status-badge.tsx`: Colored badges using shadcn Badge component with variant based on status:
- Active: green
- Pending: yellow
- Archived: blue
- Deleted: red
- Error: destructive

`row-actions.tsx`: shadcn DropdownMenu with: Update Now, Open Local Folder, View Archives, Copy URL, Delete.

**Step 3: Run tests, verify with `pnpm tauri dev`, commit.**

```bash
git commit -m "feat: add repository data table with sorting, filtering, and status badges"
```

### Task 9.5: Add Repo Bar

**Files:**
- Create: `git-archiver-v2/src/components/add-repo-bar.tsx`

**Step 1: Write test**

```typescript
describe("AddRepoBar", () => {
  it("validates URL before submitting", async () => { ... });
  it("clears input after successful add", async () => { ... });
  it("shows error toast on invalid URL", async () => { ... });
});
```

**Step 2: Implement**

URL input + "Add" button + "Import File" button (opens native file dialog via Tauri) + "Paste Multiple" button (opens a Sheet with textarea for bulk URLs).

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add repo input bar with bulk paste and file import"
```

---

## Milestone 10: Frontend — Remaining Features

### Task 10.1: Activity Log

**Files:**
- Create: `git-archiver-v2/src/components/activity-log.tsx`

Collapsible panel showing task events. Subscribes to `task-progress` and `task-error` Tauri events. Stores recent entries (last 100) in the task store.

**Commit:** `git commit -m "feat: add collapsible activity log panel"`

### Task 10.2: Status Bar

**Files:**
- Create: `git-archiver-v2/src/components/status-bar.tsx`

Fixed bottom bar showing: total repo count, active task count, next auto-update time. Reads from stores.

**Commit:** `git commit -m "feat: add status bar with repo count and task status"`

### Task 10.3: Progress Indicators

**Files:**
- Modify: `git-archiver-v2/src/components/repo-table/columns.tsx`
- Modify: `git-archiver-v2/src/stores/task-store.ts`

Subscribe to `task-progress` events. When a repo has an active task, show a progress bar row beneath its table row (expanding row pattern). Display percentage + bytes/objects from git2 callbacks.

**Commit:** `git commit -m "feat: add per-repo progress bars during git operations"`

### Task 10.4: Settings Dialog

**Files:**
- Create: `git-archiver-v2/src/components/dialogs/settings-dialog.tsx`

shadcn Dialog with:
- GitHub token input (password field + show/hide toggle + "Test" button that calls `check_rate_limit`)
- Rate limit display (remaining/limit)
- Max parallel operations slider (1-16)
- Auto-update toggle + interval dropdown
- Data path selector (uses Tauri's `dialog.open` for folder picker)
- "Migrate from JSON" button

**Commit:** `git commit -m "feat: add settings dialog with token, concurrency, and auto-update config"`

### Task 10.5: Archive Viewer Dialog

**Files:**
- Create: `git-archiver-v2/src/components/dialogs/archive-viewer.tsx`

shadcn Dialog (or Sheet) listing archives for a specific repo. Table columns: date, size, file count, type (full/incremental). Buttons: Extract Selected (opens folder dialog for destination), Delete Selected.

**Commit:** `git commit -m "feat: add archive viewer dialog with extract and delete"`

### Task 10.6: Tauri Event Subscriptions

**Files:**
- Modify: `git-archiver-v2/src/App.tsx`
- Modify: `git-archiver-v2/src/stores/task-store.ts`
- Modify: `git-archiver-v2/src/stores/repo-store.ts`

Wire up `listen()` calls in App.tsx's useEffect:
- `task-progress` → updates task store
- `repo-updated` → updates repo in repo store
- `task-error` → shows error toast

**Commit:** `git commit -m "feat: wire Tauri event subscriptions for real-time updates"`

---

## Milestone 11: Migration from Python Version

### Task 11.1: JSON Migration Command

**Files:**
- Create: `git-archiver-v2/src-tauri/src/commands/migrate.rs`
- Modify: `git-archiver-v2/src-tauri/src/commands/mod.rs`

**Step 1: Write failing test**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use std::fs;

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

        let repos = parse_legacy_json(json).unwrap();
        assert_eq!(repos.len(), 1);
        assert_eq!(repos[0].owner, "owner");
        assert_eq!(repos[0].name, "repo");
        assert_eq!(repos[0].status, "active");
    }
}
```

**Step 2: Implement**

Parse the Python version's `cloned_repos.json` format, insert into SQLite, scan `data/*/versions/*.tar.xz` to populate archives table.

```rust
#[tauri::command]
pub async fn migrate_from_json(
    json_path: String,
    state: State<'_, AppState>,
) -> Result<MigrateResult, AppError>

pub struct MigrateResult {
    pub repos_imported: u32,
    pub archives_found: u32,
    pub errors: Vec<String>,
}
```

**Step 3: Run tests, commit.**

```bash
git commit -m "feat: add migration from Python JSON format to SQLite"
```

---

## Milestone 12: Distribution & CI/CD

### Task 12.1: GitHub Actions Release Workflow

**Files:**
- Create: `git-archiver-v2/.github/workflows/release.yml`

Create the workflow from the design doc: builds on push of `v*` tags, uses `tauri-apps/tauri-action`, produces `.dmg`, `.msi`, `.deb`, `.AppImage`, creates draft GitHub release.

**Commit:** `git commit -m "ci: add GitHub Actions release workflow for all platforms"`

### Task 12.2: PR Test Workflow

**Files:**
- Create: `git-archiver-v2/.github/workflows/test.yml`

Runs on every push/PR:
- `cargo test` (Rust unit tests)
- `cargo clippy` (linting)
- `pnpm test` (frontend tests)
- `pnpm build` (TypeScript compilation check)

**Commit:** `git commit -m "ci: add PR test workflow with Rust and frontend checks"`

### Task 12.3: Tauri Auto-Updater Configuration

**Files:**
- Modify: `git-archiver-v2/src-tauri/tauri.conf.json`

Add the updater plugin config pointing to GitHub releases endpoint.

**Commit:** `git commit -m "feat: configure Tauri auto-updater with GitHub releases"`

### Task 12.4: App Metadata and Icons

**Files:**
- Modify: `git-archiver-v2/src-tauri/tauri.conf.json`
- Create: app icons (use `cargo tauri icon` to generate from a source PNG)

Set app name, version, bundle identifier, window title, default size (1200x700).

**Commit:** `git commit -m "chore: add app metadata, icons, and window configuration"`

---

## Summary: Build Order

```
Milestone 1: Scaffolding          [4 tasks]   ← Start here
    |
Milestone 2: Database Layer       [4 tasks]
    |
Milestone 3: URL Validation       [1 task]
    |
    +------ Milestone 4: Git Ops  [2 tasks]   ← Can parallelize 4, 5, 6
    |       Milestone 5: Archives [2 tasks]
    |       Milestone 6: API      [3 tasks]
    |
Milestone 7: Task Manager         [1 task]    ← Needs 4, 5, 6
    |
Milestone 8: Tauri Commands       [4 tasks]   ← Needs 2-7
    |
    +------ Milestone 9: Frontend Core [5 tasks]  ← Can parallelize 9, 10
    |       Milestone 10: Frontend Features [6 tasks]
    |
Milestone 11: Migration           [1 task]
    |
Milestone 12: Distribution        [4 tasks]
```

**Total: ~37 tasks across 12 milestones**
