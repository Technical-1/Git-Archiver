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

### Daily auto-sync with a tray-resident background process
A configurable daily time triggers `update_all` automatically. Closing the window hides the app to the system tray instead of quitting; the tray menu shows the last sync time and is the persistent surface for an app that's meant to run quietly in the background. Implemented across `core/scheduler.rs` and `tray.rs`.

### Signed and notarized releases
Tauri's updater plugin checks GitHub Releases for new versions and verifies Ed25519 signatures before installing. macOS builds are code-signed with a Developer ID Application certificate and notarized via Apple's `notarytool` so they install without Gatekeeper warnings.

## Technical Highlights

### Async task queue with cancellation
The worker is a channel-based queue where IPC commands enqueue tasks and a long-running `tokio::spawn`'d loop consumes them. A tokio semaphore caps concurrency; each task carries a `CancellationToken` so a single "stop all" call propagates to every in-flight operation. A `DashMap` of in-flight repo IDs handles deduplication so the same clone can't be enqueued twice. Progress flows back to the frontend through Tauri events, keeping the React activity log live without polling.

### Incremental tar.xz archives
Each archive run hashes every file in the repo (excluding `.git/`) and compares against hashes stored in SQLite from the prior run. Only changed files are added to the new `.tar.xz`. This is what produces the 70-90% storage savings on repos that update frequently with small diffs. See `core/hasher.rs` and `db/file_hashes.rs`.

### Cross-compilation without system OpenSSL
The original build broke when CI tried to cross-compile from ARM64 macOS to x86_64 — `openssl-sys` doesn't cross-compile cleanly. The fix was to drop system TLS entirely: `reqwest` uses `rustls-tls`, and `git2` enables `vendored-openssl` so libgit2 builds its own copy. The crate set now has zero system OpenSSL linkage on any target.

### Security hardening on untrusted inputs
URL validation rejects percent-encoded path traversal attempts (`core/url.rs`). The GraphQL client sanitizes owner/name fields before interpolating them into queries (`core/github_api.rs`). Archive extraction validates each tar entry's path to prevent tar-slip attacks (`core/archive.rs`). Bulk-import paths are canonicalized, constrained to the user's home directory, and restricted to an extension allowlist to block renderer-coerced reads of arbitrary files (`commands/repos.rs::validate_import_path`). All four have dedicated unit tests.

### DST-aware daily scheduler
The daily auto-sync uses `tokio::select!` to race a sleep timer against a `watch::Receiver<Option<NaiveTime>>`, so changing the sync time in settings preempts the current sleep and reschedules instantly — no restart, no missed window. DST is handled explicitly in `local_naive_to_instant`: ambiguous fall-back times pick the earlier instant (a 1:30 sync fires once across the rewind), nonexistent spring-forward times shift forward one hour into the post-gap zone. The scheduler updates the system tray's "Last sync" item after every run.

### Statically linked liblzma for notarized macOS builds
Notarized macOS builds with Hardened Runtime can't load the dynamic `liblzma.dylib` shipped by Homebrew — the OS dyld resolver rejects the unsigned dylib at runtime, which manifested as a crash whenever the app tried to create a `.tar.xz` archive. The fix was the `static` feature on `xz2`, which compiles liblzma into the binary. Builds got a few hundred KB heavier; archives now actually work on distributed signed builds.

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
- **Choice**: rustls for `reqwest`, vendored + statically linked OpenSSL only for libgit2.
- **Why**: One pure-Rust TLS stack works identically on every target with no system linking. CI builds went from flaky to deterministic.

### Tray-resident background process instead of quit-on-close
- **Constraint**: A daily auto-sync is useless if the user has to leave the window open. The app needs to keep running after the window closes.
- **Options**: Quit-on-close like a typical desktop app; spin off a separate background daemon process; keep one process alive and hide the window.
- **Choice**: Single process, window-close hides instead of quits, system tray menu as the persistent surface. On macOS the dock icon is toggled via `ActivationPolicy::Accessory`.
- **Why**: A separate daemon would have meant duplicating the SQLite/scheduler/keychain plumbing and inventing IPC between processes. Keeping one process is simpler, lets the scheduler and worker share state directly, and matches user expectation for tray-resident utilities like Dropbox or 1Password's helper.

## Frequently Asked Questions

### How does the concurrent task system work?
Tasks (clone, update, refresh) are enqueued into an MPSC channel from Tauri IPC commands. A background worker loop receives tasks and acquires a tokio semaphore permit before executing each one — the semaphore caps concurrency at a user-configurable 1-10. Each task holds a `CancellationToken` so the "stop all" button can interrupt every in-flight operation. A `DashMap` of active repo IDs prevents the same repo from being queued twice at once.

### How does the incremental archive feature work?
On each archive run, the app walks the repo (excluding `.git/`), computes MD5 hashes per file, and compares them against the hashes stored in SQLite from the previous run. Only files whose hashes changed are added to the new `.tar.xz`. For repos with frequent small changes, archives end up 70-90% smaller than full snapshots.

### How does the GitHub API integration handle rate limits?
The app uses GraphQL batch queries to check up to 100 repositories in a single call, instead of one REST request per repo. The status bar shows the current rate limit budget. With a personal access token stored in the OS keychain, the budget is 5,000 requests/hour; unauthenticated it's 60/hour, which is why setting a token is the first thing the settings dialog asks for.

### How does the auto-updater verify downloads?
Tauri's updater plugin checks GitHub Releases for newer versions. Release artifacts are signed with Ed25519 minisign keys — the public key is embedded in the app at build time, and the (passwordless) private key lives in a GitHub Actions secret used only by the release workflow. macOS binaries are additionally code-signed with a Developer ID Application certificate and notarized via `notarytool`. Updates that fail signature verification are rejected before install.

### Does the app keep running after I close the window?
Yes — that's the whole point of the daily sync feature. Closing the window hides the app to the system tray instead of quitting. The tray menu has "Open Git Archiver", a live "Last sync: …" line that the scheduler updates after each run, and an explicit Quit. On macOS the dock icon hides while the window is closed and reappears when you reopen it.

### How does the daily auto-sync handle daylight saving?
The scheduler uses `tokio::select!` to race a sleep against a `watch::Receiver`, so editing the sync time in settings preempts the sleep immediately. For DST, `chrono::Local::from_local_datetime` returns `Ambiguous` on fall-back days and `None` for spring-forward gaps. The scheduler picks the earlier instant for ambiguous times (so a 1:30 sync fires once across the rewind) and shifts forward one hour for nonexistent times.

### Where are tokens and data stored?
GitHub tokens go into the OS keychain (`keyring` crate). Repo metadata, archive records, file hashes, and settings live in SQLite under the platform's standard data directory. Cloned repos are bare clones (`data/<owner>_<repo>.git/`) and archives are timestamped `.tar.xz` files under `versions/`.

### What platforms have prebuilt binaries?
macOS (Apple Silicon and Intel, signed + notarized), Windows x86_64, and Linux x86_64. Release artifacts include `.dmg` and `.app.tar.gz` for macOS, `.exe` (NSIS) and `.msi` for Windows, and `.deb`, `.rpm`, and `.AppImage` for Linux — published on the GitHub Releases page.

### Why bare clones instead of full working trees?
The point is archival, not active development. Bare clones skip the working directory entirely, halving disk usage and making fetch-only updates faster. If you need the working tree, extract the archive or `git clone` from the bare repo locally.

### What happens if a local clone gets corrupted between runs?
The worker health-checks the existing `.git` directory before reusing it. If `libgit2` can't open it as a valid bare repo, the worker falls back to a fresh clone rather than failing the fetch — a deleted-by-user, partially-written, or otherwise broken directory recovers automatically on the next update.
