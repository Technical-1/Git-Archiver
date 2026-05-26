# Project Q&A

## Overview

Git Archiver is a cross-platform desktop application I built to preserve GitHub repositories before they disappear. It clones repositories, tracks their status via the GitHub API, and creates versioned compressed archives whenever updates are detected. The v2.0.0 release is a complete rewrite from Python/PyQt5 to Rust/Tauri/React, producing ~5-7MB native binaries instead of a ~150MB+ packaged Python interpreter.

## Problem Solved

GitHub repositories disappear all the time — owners delete them, accounts get suspended, organizations go private, or projects are archived and eventually lost. If you depend on a repo (a fork you reference, a dependency you vendor, an old tutorial you keep coming back to), you need a local copy that updates itself and keeps history. Git Archiver tracks a list of repos, fetches them on a schedule, and saves a compressed `.tar.xz` snapshot of every change so you have a versioned local archive instead of a single mutable clone.

## Target Users

- **Developers preserving dependencies** — anyone who pulls in code from GitHub and wants insurance against repos vanishing
- **Researchers and archivists** — people studying open-source projects who need stable, versioned snapshots
- **Self-hosters** — users who want a local backup of their own repos and starred projects without relying on GitHub's availability

## Key Features

### Concurrent task engine
Semaphore-controlled worker pool with per-task cancellation, deduplication, and configurable concurrency (1-10 parallel operations). Implemented in `git-archiver-v2/src-tauri/src/core/task_manager.rs` and `worker.rs`.

### Incremental archives
MD5-based file change detection creates archives containing only modified files, achieving 70-90% space savings on actively developed repos. Hashes are stored in the `file_hashes` table; see `core/hasher.rs` and `core/archive.rs`.

### Batch status detection
GraphQL queries check up to 100 repositories per API call, detecting archived/deleted repos without burning through REST rate limits. See `core/github_api.rs`.

### OS keychain integration
GitHub tokens are stored in the platform credential store (macOS Keychain, Windows Credential Manager, Linux Secret Service) via the `keyring` crate — never on disk in plaintext.

### Legacy migration
One-click import from the v1.x Python JSON database, including a scan of the data directory to register any pre-existing archives.

### Auto-updater
Tauri's updater plugin checks GitHub Releases for new versions and verifies Ed25519 signatures before installing.

## Technical Highlights

### Async task queue with cancellation
The worker is a channel-based queue where IPC commands enqueue tasks and a long-running `tokio::spawn`'d loop consumes them. A tokio semaphore caps concurrency; each task carries a `CancellationToken` so a single "stop all" call propagates to every in-flight operation. A `DashMap` of in-flight repo IDs handles deduplication so the same clone can't be enqueued twice. Progress flows back to the frontend through Tauri events, keeping the React activity log live without polling.

### Incremental tar.xz archives
Each archive run hashes every file in the repo (excluding `.git/`) and compares against hashes stored in SQLite from the prior run. Only changed files are added to the new `.tar.xz`. This is what produces the 70-90% storage savings on repos that update frequently with small diffs. See `core/hasher.rs` and `db/file_hashes.rs`.

### Cross-compilation without system OpenSSL
The original build broke when CI tried to cross-compile from ARM64 macOS to x86_64 — `openssl-sys` doesn't cross-compile cleanly. The fix was to drop system TLS entirely: `reqwest` uses `rustls-tls`, and `git2` enables `vendored-openssl` so libgit2 builds its own copy. The crate set now has zero system OpenSSL linkage on any target.

### Security hardening on untrusted inputs
URL validation rejects percent-encoded path traversal attempts (`core/url.rs`). The GraphQL client sanitizes owner/name fields before interpolating them into queries (`core/github_api.rs`). Archive extraction validates each tar entry's path to prevent tar-slip attacks (`core/archive.rs`). All three have dedicated unit tests.

## Engineering Decisions

### Rust/Tauri instead of staying on Python/PyQt5
- **Constraint**: Distribution size and cross-platform builds. The v1.x PyQt5 app shipped at ~150MB+ once the interpreter and Qt were bundled, and packaging for Windows/Linux from a Mac dev box was painful.
- **Options**: Stay on Python and ship via PyInstaller; switch to Electron; switch to Tauri.
- **Choice**: Tauri v2 with a Rust backend and React frontend.
- **Why**: Binary size dropped to ~5-7MB. Tauri provides the auto-updater, OS keychain, and cross-platform packaging out of the box, which would have been third-party glue in Python or Electron. Rust also gave proper error types and structured concurrency for the task queue.

### SQLite instead of the v1.x JSON file
- **Constraint**: The v1.x JSON store needed hand-rolled atomic writes and corruption recovery scripts.
- **Options**: Keep JSON with better locking; move to SQLite; move to an embedded KV store like sled.
- **Choice**: SQLite via `rusqlite` with the bundled feature so there's no system dependency.
- **Why**: ACID transactions, schema migrations, and cascade deletes for free. The migration command in `commands/migrate.rs` reads the old JSON and imports it cleanly.

### libgit2 instead of shelling out to git
- **Constraint**: A bundled desktop app shouldn't require users to have `git` on their PATH.
- **Options**: Subprocess `git` CLI; libgit2 via `git2` crate; raw HTTP smart-protocol implementation.
- **Choice**: `git2` with vendored OpenSSL.
- **Why**: No external dependency, structured `git2::Error` instead of parsing stderr, and credential callbacks let token auth flow through without polluting environment variables.

### rustls instead of native TLS
- **Constraint**: Cross-compiling from ARM64 macOS runners to x86_64 kept failing on `openssl-sys`.
- **Options**: Install OpenSSL for each target in CI; use native-tls (Schannel/SecureTransport/OpenSSL); use rustls.
- **Choice**: rustls for `reqwest`, vendored OpenSSL only for libgit2.
- **Why**: One pure-Rust TLS stack works identically on every target with no system linking. CI builds went from flaky to deterministic.

## Frequently Asked Questions

### How does the concurrent task system work?
Tasks (clone, update, refresh) are enqueued into an MPSC channel from Tauri IPC commands. A background worker loop receives tasks and acquires a tokio semaphore permit before executing each one — the semaphore caps concurrency at a user-configurable 1-10. Each task holds a `CancellationToken` so the "stop all" button can interrupt every in-flight operation. A `DashMap` of active repo IDs prevents the same repo from being queued twice at once.

### How does the incremental archive feature work?
On each archive run, the app walks the repo (excluding `.git/`), computes MD5 hashes per file, and compares them against the hashes stored in SQLite from the previous run. Only files whose hashes changed are added to the new `.tar.xz`. For repos with frequent small changes, archives end up 70-90% smaller than full snapshots.

### How does the GitHub API integration handle rate limits?
The app uses GraphQL batch queries to check up to 100 repositories in a single call, instead of one REST request per repo. The status bar shows the current rate limit budget. With a personal access token stored in the OS keychain, the budget is 5,000 requests/hour; unauthenticated it's 60/hour, which is why setting a token is the first thing the settings dialog asks for.

### How does the auto-updater verify downloads?
Tauri's updater plugin checks GitHub Releases for newer versions. Release artifacts are signed with Ed25519 minisign keys — the public key is embedded in the app at build time, and the private key lives in a GitHub Actions secret used only by the release workflow. Updates that fail signature verification are rejected before install.

### Can I migrate from the v1.x Python version?
Yes. The settings dialog has a migration tool that reads `cloned_repos.json`, imports all entries with their metadata into SQLite, and scans the data directory so any existing `.tar.xz` archives become first-class archive records.

### Where are tokens and data stored?
GitHub tokens go into the OS keychain (`keyring` crate). Repo metadata, archive records, and file hashes live in SQLite under the platform's standard data directory. Cloned repos are bare clones (`data/<owner>_<repo>.git/`) and archives are timestamped `.tar.xz` files under `versions/`.

### What platforms have prebuilt binaries?
macOS (Apple Silicon and Intel), Windows x86_64, and Linux x86_64. Release artifacts include `.dmg` and `.app.tar.gz` for macOS, `.exe` (NSIS) and `.msi` for Windows, and `.deb`, `.rpm`, and `.AppImage` for Linux — published on the GitHub Releases page.

### Why bare clones instead of full working trees?
The point is archival, not active development. Bare clones skip the working directory entirely, halving disk usage and making fetch-only updates faster. If you need the working tree, extract the archive or `git clone` from the bare repo locally.
