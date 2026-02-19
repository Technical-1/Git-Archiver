# Git Archiver: Rust/Tauri Rewrite Design

**Date:** 2026-02-18
**Status:** Approved
**Decision:** Full rewrite from Python/PyQt5 to Rust/Tauri with React+TypeScript frontend

## Context

Git-Archiver is a desktop application that clones GitHub repositories, tracks their status via the GitHub API, and creates versioned `.tar.xz` archives when updates are detected. The current implementation is Python/PyQt5.

### Why Rewrite

A deep analysis of the existing codebase revealed structural issues that make incremental improvement impractical:

- **Three parallel implementations** (refactored GUI, legacy monolith with more features, Flask web server) creating a maintenance nightmare
- **Path inconsistency** between modules (`config.py` vs `repo_manager.py` disagree on JSON location)
- **Two save functions with different locking** (`data_store.py` vs `repo_manager.py`) creating race conditions
- **GitHub token not applied** in `repo_manager.py` actual API calls (only in separate `github_api.py`)
- **Dormant deadlock** in `update_repo_record()` using non-reentrant lock
- **Shell injection vulnerability** via user-controlled paths passed to shell commands
- **Token stored in plaintext** JSON on disk
- **No packaging infrastructure** (no `pyproject.toml`, no PyInstaller, no CI)
- **Feature regression** from refactor (legacy GUI has features the refactored version dropped)
- **PyQt5 bundles** are 80-100MB, trigger antivirus false positives, and macOS notarization is painful

### Alternatives Considered

1. **Tauri shell + Python sidecar** -- rejected because it still ships Python's problems (bundled runtime, structural bugs) and adds IPC complexity across three languages
2. **Fix Python + package with PyInstaller** -- rejected because fixing all structural issues is nearly as much work as a rewrite, with worse distribution outcomes

## Target

- Public open-source desktop application
- Platforms: macOS + Windows + Linux
- Desktop-only (web interface dropped from scope)
- Tech: Rust backend, Tauri v2, React + TypeScript + shadcn/ui frontend
- Dark mode + light mode with system detection

---

## Architecture Overview

```
+-----------------------------------------------------------+
|                     Tauri Window                           |
|  +-----------------------------------------------------+  |
|  |           React + TypeScript Frontend                |  |
|  |                                                      |  |
|  |  shadcn/ui + @tanstack/react-table + zustand         |  |
|  |  next-themes (dark/light/system)                     |  |
|  +------------------------+-----------------------------+  |
|                           | invoke() / listen()            |
|  +------------------------+-----------------------------+  |
|  |              Tauri Command Layer                     |  |
|  |         #[tauri::command] functions                  |  |
|  +------------------------+-----------------------------+  |
|                           |                                |
|  +------------------------+-----------------------------+  |
|  |              Rust Backend Core                       |  |
|  |                                                      |  |
|  |  git2       reqwest       rusqlite                   |  |
|  |  (clone/    (GitHub       (repo DB +                 |  |
|  |   pull)      API)          settings)                 |  |
|  |                                                      |  |
|  |  tar+xz2              tokio                          |  |
|  |  (archive)            (async runtime + channels)     |  |
|  +------------------------------------------------------+  |
+-----------------------------------------------------------+
```

### Key Crates

| Crate | Replaces | Purpose |
|-------|----------|---------|
| `git2` | subprocess git calls | Clone, fetch, pull with progress callbacks and credential handling |
| `reqwest` | `requests` | GitHub REST + GraphQL API with proper auth |
| `rusqlite` | `cloned_repos.json` | Concurrent-safe persistence with migrations |
| `tar` + `xz2` | subprocess tar calls | Pure Rust archive creation -- no `tar` on PATH needed |
| `tokio` | `QThread` + `threading.Thread` | Async task orchestration via channels |
| `serde` / `serde_json` | `json` | Typed serialization for API responses and config |
| `keyring` | plaintext `settings.json` | OS keychain for GitHub token |
| `thiserror` | bare `except` blocks | Typed error hierarchy |
| `dashmap` | `threading.Lock` + `dict` | Lock-free concurrent map for active tasks |
| `tauri` | `PyQt5` | Window management, IPC, bundling, auto-updater |

### Data Flow

```
URLs -> SQLite DB -> git2 clone to data/<repo>/ -> tar+xz2 archives in data/<repo>/versions/
          ^                    ^                            ^
     rusqlite              git2 with                   Pure Rust,
     (WAL mode,            progress events             no PATH dep
      migrations)          + credentials
```

---

## Data Model

### SQLite Schema

```sql
CREATE TABLE repositories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner         TEXT NOT NULL,
    name          TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    description   TEXT,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','active','archived','deleted','error')),
    is_private    BOOLEAN NOT NULL DEFAULT 0,
    local_path    TEXT,
    last_cloned   DATETIME,
    last_updated  DATETIME,
    last_checked  DATETIME,
    error_message TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner, name)
);

CREATE TABLE archives (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id       INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    file_count    INTEGER NOT NULL,
    is_incremental BOOLEAN NOT NULL DEFAULT 0,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE file_hashes (
    repo_id       INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_path     TEXT NOT NULL,
    md5_hash      TEXT NOT NULL,
    last_seen     DATETIME NOT NULL,
    PRIMARY KEY (repo_id, file_path)
);

CREATE TABLE settings (
    key           TEXT PRIMARY KEY,
    value         TEXT NOT NULL
);

CREATE TABLE schema_version (
    version       INTEGER PRIMARY KEY
);
```

### Rust Domain Types

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RepoStatus {
    Pending,
    Active,
    Archived,
    Deleted,
    Error,
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
pub struct TaskProgress {
    pub repo_url: String,
    pub stage: TaskStage,
    pub progress_pct: Option<f32>,
    pub message: String,
}
```

### Migration from Python Version

One-time CLI command to import existing data:

```
git-archiver migrate --from-json cloned_repos.json
```

Reads old JSON, inserts rows into SQLite, scans existing `data/*/versions/*.tar.xz` to populate the `archives` table. Non-destructive -- old JSON left untouched.

---

## Tauri Command Layer

```rust
// Repository CRUD
async fn add_repo(url, state) -> Result<Repository, AppError>;
async fn add_repos_bulk(urls, state) -> Result<BulkAddResult, AppError>;
async fn delete_repo(id, remove_files, state) -> Result<(), AppError>;
async fn list_repos(filter, state) -> Result<Vec<Repository>, AppError>;
async fn import_from_file(path, state) -> Result<BulkAddResult, AppError>;

// Git operations (trigger async tasks)
async fn clone_repo(id, state) -> Result<(), AppError>;
async fn update_repo(id, state) -> Result<(), AppError>;
async fn update_all(include_archived, state) -> Result<(), AppError>;
async fn stop_all_tasks(state) -> Result<(), AppError>;

// Status and archives
async fn refresh_statuses(state) -> Result<(), AppError>;
async fn list_archives(repo_id, state) -> Result<Vec<Archive>, AppError>;
async fn extract_archive(archive_id, dest, state) -> Result<String, AppError>;
async fn delete_archive(archive_id, state) -> Result<(), AppError>;

// Settings
async fn get_settings(state) -> Result<AppSettings, AppError>;
async fn save_settings(settings, state) -> Result<(), AppError>;
async fn check_rate_limit(state) -> Result<RateLimitInfo, AppError>;

// Migration
async fn migrate_from_json(json_path, state) -> Result<MigrateResult, AppError>;
```

---

## Async Architecture

### Core Components

```rust
pub struct AppState {
    pub db: Arc<Mutex<Connection>>,
    pub task_manager: Arc<TaskManager>,
    pub github_client: Arc<GitHubClient>,
    pub app_handle: AppHandle,
}

pub struct TaskManager {
    tx: mpsc::Sender<Task>,
    active_tasks: DashMap<i64, CancellationToken>,
    semaphore: Arc<Semaphore>,  // user-configurable permit count (1-16, default 4)
}

pub enum Task {
    Clone(i64),
    Update(i64),
    UpdateAll { include_archived: bool },
    RefreshStatuses,
    Stop,
}
```

### Task Processing Flow

```
invoke("clone_repo", {id})
  -> #[tauri::command] clone_repo()
    -> TaskManager::enqueue(Task::Clone(id))
      -> dedup check via active_tasks DashMap
      -> tx.send(task)

Task Worker Loop (spawned once at startup):
  loop {
    task = rx.recv().await
    semaphore.acquire().await      // limits concurrent ops
    tokio::spawn(async {
      emit("task-progress", {id, Cloning, 0%})
      git2::clone_with_callbacks(|pct| emit("task-progress", ...))
      emit("task-progress", {id, Archiving})
      create_archive(id)
      emit("task-progress", {id, Done})
      emit("repo-updated", repo)
    })
  }
```

### Concurrency Controls

- **Semaphore** limits concurrent git operations (user-configurable: 1-16, default 4)
- **DashMap** for lock-free task deduplication
- **CancellationToken** per task for individual or bulk cancellation
- `git2` progress callbacks check cancellation to abort mid-clone

### Event Flow (Backend to Frontend)

```typescript
listen<TaskProgress>("task-progress", (event) => { /* update progress bar */ });
listen<Repository>("repo-updated", (event) => { /* update table row */ });
listen<string>("task-error", (event) => { /* show toast */ });
```

---

## Frontend UI

### Layout

```
+-------------------------------------------------------------+
|  Git Archiver                              [gear] Settings   |
|-------------------------------------------------------------|
|                                                              |
|  +- Add Repos ------------------------------------------+   |
|  |  [https://github.com/owner/repo          ] [+ Add]   |   |
|  |  [Import File...] [Paste Multiple]                    |   |
|  +-------------------------------------------------------+   |
|                                                              |
|  +- Toolbar ---------------------------------------------+   |
|  |  [Update All] [Stop] | Search: [________]             |   |
|  |  Filter: [All v]  Sort: [Last Updated v]              |   |
|  +-------------------------------------------------------+   |
|                                                              |
|  +- Repository Table ------------------------------------+   |
|  |  Repository      Description    Status   Last Updated  |  |
|  |  ---------------------------------------------------- |  |
|  |  torvalds/linux   ...           Active    2h ago    :  |  |
|  |    +- Cloning [========--] 72%                        |  |
|  |  rust-lang/rust   ...           Active    1d ago    :  |  |
|  |  old/gone-repo    ...           Deleted  30d ago    :  |  |
|  |                                                        |  |
|  |                    1-50 of 423  [< 1 2 3 ... 9 >]    |  |
|  +-------------------------------------------------------+   |
|                                                              |
|  +- Activity Log ----------------------------- [collapse]+   |
|  |  14:30 Cloning torvalds/linux... 72% (48MB/67MB)      |  |
|  |  14:29 Updated rust-lang/rust -- no changes, skipped  |  |
|  |  14:28 Archived facebook/react (v3, 2.1MB, 847 files)|  |
|  +-------------------------------------------------------+   |
|                                                              |
|  +- Status Bar ------------------------------------------+   |
|  |  423 repos | 2 active tasks | Next auto-update: 22:00 |  |
|  +-------------------------------------------------------+   |
+-------------------------------------------------------------+
```

### Frontend Stack

```
react + typescript
@tanstack/react-table          -- headless table (shadcn/ui DataTable wraps this)
zustand                         -- state management
@tauri-apps/api                 -- Tauri IPC
tailwindcss                     -- utility styling (shadcn/ui dependency)
shadcn/ui                       -- component library (Dialog, DropdownMenu, Badge,
                                   Slider, Input, Button, Toast, Sheet, DataTable)
lucide-react                    -- icons (shadcn/ui default icon set)
next-themes                     -- dark/light/system toggle
```

### Key UI Improvements Over Python Version

| Current (PyQt5) | New (React/Tauri) |
|---|---|
| No progress indication during clone | Per-repo progress bar with bytes/objects from git2 |
| Status as plain text | Color-coded status badges with icons |
| Raw timestamps | Relative time ("2h ago") with tooltip for full date |
| Button-per-row for Folder/Archives/README | Row context menu (right-click or overflow button) |
| Fixed column layout | Resizable, reorderable, hideable columns |
| No pagination | Virtual scrolling or pagination for 400+ repos |
| Log is always visible | Collapsible activity log panel |
| No bulk paste | "Paste Multiple" textarea for batch URL input |
| Light mode only | Dark/light/system theme |

### Dialogs

**Settings:** GitHub token (stored in OS keychain), rate limit display, max parallel operations slider (1-16), auto-update toggle and interval, storage path selector, migration from JSON button.

**Archive Viewer:** Table of archives per repo (date, size, file count, full/incremental), extract and delete actions.

---

## Error Handling

```rust
#[derive(Debug, thiserror::Error, Serialize)]
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
```

Automatic `From` impls for `git2::Error`, `rusqlite::Error`, `reqwest::Error`. Frontend displays errors as toast notifications with severity-aware styling.

---

## Testing Strategy

### Rust Backend

| Layer | Tool | Scope |
|-------|------|-------|
| Unit | `#[cfg(test)]` + `cargo test` | URL validation, status transitions, hash comparison, SQL queries (in-memory SQLite) |
| Integration | `cargo test` with fixtures | Full clone-archive-detect cycle using a local test git repo |
| GitHub API | `mockito` crate | REST + GraphQL responses, rate limiting, 404/403, token auth |

### React Frontend

| Tool | Scope |
|------|-------|
| `vitest` | Store logic, URL parsing, date formatting |
| `@testing-library/react` | Component rendering, table interactions, dialog flows |
| Mock `invoke()` | Simulate backend responses without Rust |

---

## Distribution

### CI/CD

GitHub Actions workflow triggered by version tags (`v*`):

- **macOS:** `.dmg` (universal binary: Apple Silicon + Intel)
- **Windows:** `.msi` installer + portable `.exe`
- **Linux:** `.deb` package + `.AppImage`

Uses `tauri-apps/tauri-action` for cross-platform builds.

### Auto-Update

Tauri built-in updater plugin checks GitHub releases for new versions and prompts users with a native dialog.

### Bundle Size

Expected ~5-10MB per platform (vs 80-100MB for PyInstaller+PyQt5).

---

## Project Structure

```
git-archiver/
+-- src-tauri/
|   +-- Cargo.toml
|   +-- tauri.conf.json
|   +-- src/
|   |   +-- main.rs                -- Tauri bootstrap, register commands
|   |   +-- commands/
|   |   |   +-- mod.rs
|   |   |   +-- repos.rs           -- add/delete/list/import commands
|   |   |   +-- tasks.rs           -- clone/update/stop commands
|   |   |   +-- archives.rs        -- list/extract/delete archive commands
|   |   |   +-- settings.rs        -- get/save settings, rate limit
|   |   +-- core/
|   |   |   +-- mod.rs
|   |   |   +-- git.rs             -- git2 clone/fetch/pull with progress
|   |   |   +-- archive.rs         -- tar+xz2 creation and extraction
|   |   |   +-- github_api.rs      -- REST + GraphQL client
|   |   |   +-- task_manager.rs    -- channel, semaphore, cancellation
|   |   +-- db/
|   |   |   +-- mod.rs
|   |   |   +-- migrations.rs      -- schema creation + versioned migrations
|   |   |   +-- repos.rs           -- repository CRUD queries
|   |   |   +-- archives.rs        -- archive CRUD queries
|   |   |   +-- settings.rs        -- settings key-value queries
|   |   +-- models.rs              -- Repository, Archive, TaskProgress, etc.
|   |   +-- error.rs               -- AppError enum + From impls
|   +-- migrations/
|       +-- 001_initial.sql
+-- src/                            -- React frontend
|   +-- App.tsx
|   +-- components/
|   |   +-- repo-table/
|   |   |   +-- columns.tsx        -- column definitions
|   |   |   +-- data-table.tsx     -- shadcn DataTable wrapper
|   |   |   +-- row-actions.tsx    -- context menu
|   |   +-- add-repo-bar.tsx
|   |   +-- activity-log.tsx
|   |   +-- status-bar.tsx
|   |   +-- dialogs/
|   |       +-- settings-dialog.tsx
|   |       +-- archive-viewer.tsx
|   +-- stores/
|   |   +-- repo-store.ts
|   |   +-- task-store.ts
|   |   +-- settings-store.ts
|   +-- lib/
|   |   +-- commands.ts            -- typed invoke() wrappers
|   |   +-- utils.ts
|   +-- styles/
|       +-- globals.css            -- Tailwind + shadcn theme variables
+-- package.json
+-- tsconfig.json
+-- tailwind.config.ts
+-- components.json                -- shadcn/ui config
+-- .github/
    +-- workflows/
        +-- release.yml
```
