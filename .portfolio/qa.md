# Project Q&A Knowledge Base

## Overview

Git Archiver is a cross-platform desktop application I built to preserve GitHub repositories before they disappear. It clones repositories, tracks their status via the GitHub API, and creates versioned compressed archives whenever updates are detected. The v2.0.0 release is a complete rewrite from Python/PyQt5 to Rust/Tauri/React, delivering native performance, cross-platform binaries, and a modern UI.

## Key Features

- **Concurrent Task Engine**: Semaphore-controlled worker pool with per-task cancellation, deduplication, and configurable concurrency (1-10 parallel operations)
- **Incremental Archives**: MD5-based file change detection creates archives containing only modified files, achieving 70-90% space savings
- **Batch Status Detection**: GraphQL queries check up to 100 repositories per API call, detecting archived/deleted repos efficiently
- **OS Keychain Integration**: GitHub tokens stored securely in macOS Keychain, Windows Credential Manager, or Linux Secret Service
- **Legacy Migration**: One-click import from the v1.x Python JSON database with automatic archive scanning
- **Auto-Updater**: Built-in update mechanism checks GitHub Releases for new versions with Ed25519 signature verification

## Technical Highlights

### Complete Rewrite: Python to Rust
The original application was a PyQt5 desktop app with a JSON file database. I rewrote the entire application in Rust with a Tauri v2 shell and React frontend. The Rust backend handles all business logic — git operations via libgit2, GitHub API calls, archive creation, and SQLite persistence. The React frontend uses shadcn/ui components with Zustand for state management. This produced ~5-7MB cross-platform binaries compared to Python's ~150MB+ when packaged.

### Async Task Queue Architecture
I designed a channel-based task queue where frontend actions enqueue tasks through Tauri IPC commands, and a long-running worker loop consumes them with semaphore-controlled concurrency. Each task gets a cancellation token for graceful stop-all support. The deduplication system prevents duplicate clone/update operations from being enqueued for the same repository. The worker emits Tauri events that the frontend listens to for real-time progress updates in the activity log.

### Cross-Compilation Challenges
Building for 4 platforms (macOS ARM64, macOS x86_64, Windows, Linux) revealed interesting dependency issues. The `openssl-sys` crate couldn't cross-compile from ARM64 to x86_64 on macOS CI runners. I solved this by switching `reqwest` to `rustls-tls` (pure Rust TLS) and enabling `vendored-openssl` for `git2`'s libgit2 dependency. These changes eliminated all system OpenSSL dependencies.

### Security-Conscious Design
Several security measures are built into the codebase: GitHub tokens use OS keychain storage instead of plaintext files. URL validation rejects percent-encoded path traversal attempts. The GraphQL API client sanitizes repository owner/name inputs against injection. Archive extraction validates paths to prevent tar-slip attacks. All of these have dedicated test coverage.

## Development Story

- **Timeline**: The v1.x Python version was built incrementally over several months. The v2.0.0 Rust/Tauri rewrite was planned as 12 milestones with 37 tasks and executed systematically.
- **Hardest Part**: Getting the async task queue right — coordinating Tauri's async runtime, tokio channels, semaphore permits, and cancellation tokens while keeping the frontend responsive via event streaming.
- **Lessons Learned**: Vendoring native dependencies (OpenSSL, SQLite, libgit2) is essential for cross-platform CI builds. Also, rustls is almost always preferable to native TLS for cross-compilation.
- **Future Plans**: Apple code signing and notarization for macOS distribution, GitLab/Bitbucket support, archive deduplication with content-addressable storage.

## Frequently Asked Questions

### How does the concurrent task system work?
Tasks (clone, update, refresh) are enqueued into an MPSC channel via Tauri IPC commands. A background worker loop receives tasks and acquires a tokio semaphore permit before executing each one. The semaphore limits concurrency to a configurable maximum (1-10). Each task gets a `CancellationToken` that can be triggered for graceful stop-all. The deduplication layer prevents the same repository from being cloned/updated multiple times simultaneously.

### Why did you rewrite from Python to Rust?
Three main reasons: (1) Distribution — Python desktop apps require bundling the interpreter (~150MB+), while Tauri produces ~5-7MB native binaries. (2) Performance — Rust's async runtime with libgit2 is significantly faster than Python subprocess calls to git CLI. (3) Features — Tauri v2 provides built-in auto-updater, OS keychain access, and proper cross-platform packaging that would require many third-party libraries in Python.

### How does the incremental archive feature work?
When creating an archive, the system computes MD5 hashes of all files in the repository and stores them in the SQLite database. On subsequent archives, it compares current hashes against stored ones and only includes files whose hashes have changed. For actively developed projects with frequent small changes, this reduces archive storage by 70-90%.

### Why SQLite instead of the original JSON database?
The v1.x JSON database required manual locking, atomic write patterns, and recovery scripts for corrupted files. SQLite provides ACID transactions, proper schema migrations, foreign key cascade deletes, and concurrent-safe access out of the box. The migration from JSON to SQLite is handled by a dedicated command in the app.

### How does the GitHub API integration handle rate limits?
The app uses GraphQL batch queries to check up to 100 repositories in a single API call (vs one per REST call). The status bar displays current rate limit usage. With a personal access token (stored in OS keychain), the limit is 5,000 requests/hour vs 60/hour unauthenticated.

### What was the most challenging part of the rewrite?
Getting cross-platform CI builds working. The `macos-latest` GitHub Actions runner is ARM64, but building the x86_64 macOS target requires cross-compilation. Dependencies like `openssl-sys` and `libgit2-sys` don't cross-compile cleanly, so I had to switch to pure-Rust TLS (rustls) and vendor OpenSSL for libgit2.

### How does the auto-updater work?
Tauri's updater plugin checks GitHub Releases for new versions. Release artifacts are signed with Ed25519 minisign keys — the public key is embedded in the app, and the private key is a GitHub Actions secret. When an update is found, the app downloads and verifies the signature before installing.

### Can I migrate from the old Python version?
Yes. The Settings dialog includes a migration tool that reads the v1.x `cloned_repos.json` file, parses all repository entries with their metadata, and imports them into the SQLite database. It also scans the data directory for existing archives and creates records for them.

### What platforms are supported?
macOS (Apple Silicon and Intel), Windows (64-bit), and Linux (x86_64). Pre-built binaries are available as `.dmg`, `.exe`/`.msi`, `.deb`, `.rpm`, and `.AppImage` on the GitHub Releases page.

### What would you improve next?
Apple code signing and notarization to eliminate macOS Gatekeeper warnings. Support for GitLab and Bitbucket repositories. Content-addressable archive storage to deduplicate identical files across different repository versions.
