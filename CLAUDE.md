# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Git Archiver is a cross-platform desktop application built with Rust/Tauri v2 and React/TypeScript. It clones GitHub repositories, tracks their status via the GitHub API, and creates versioned `.tar.xz` archives when updates are detected. The v2.0.0 release is a complete rewrite from the original Python/PyQt5 version (legacy code remains in `src/` and `scripts/` at root).

## Commands

All commands run from `git-archiver-v2/`:

```bash
# Install frontend dependencies
pnpm install

# Development
pnpm tauri dev                    # Run app with hot reload

# Build
pnpm tauri build                  # Production build

# Rust tests (105 tests)
cargo test                        # Run all backend tests
cargo test core::git              # Single module
cargo test -- --test-threads=1    # Sequential execution

# Frontend tests (130 tests)
pnpm test                         # Run all frontend tests
pnpm test -- src/__tests__/App    # Single test file

# Rust linting
cargo clippy -- -D warnings       # Lint (CI uses -D warnings)
cargo fmt -- --check               # Format check
cargo fmt                          # Auto-format
```

## Architecture

### Rust Backend (`src-tauri/src/`)

The backend is organized into three layers:

**Commands** (`commands/`) — Tauri IPC handlers invoked from the frontend via `invoke()`:
- `repos.rs` — add_repo, list_repos, delete_repo, import_from_file
- `tasks.rs` — clone_repo, update_repo, update_all, stop_all_tasks
- `archives.rs` — list_archives, extract_archive, delete_archive
- `settings.rs` — get_settings, save_settings, check_rate_limit
- `migrate.rs` — migrate_from_json (v1.x import)

**Core** (`core/`) — Business logic:
- `git.rs` — Clone/fetch via libgit2 (bare repos, credential callbacks)
- `github_api.rs` — REST + GraphQL client with batch queries (100 repos/call)
- `archive.rs` — tar.xz creation/extraction with tar-slip protection
- `hasher.rs` — MD5 directory hashing for incremental archives
- `task_manager.rs` — MPSC channel + tokio semaphore queue with cancellation tokens
- `worker.rs` — Background loop consuming tasks, emitting Tauri events
- `url.rs` — URL validation, normalization, owner/repo extraction

**Database** (`db/`) — SQLite via rusqlite:
- `migrations.rs` — Schema versioning (repos, archives, file_hashes, settings tables)
- `repos.rs` — Repository CRUD with status filtering
- `archives.rs` — Archive records with cascade delete
- `file_hashes.rs` — MD5 hashes for incremental diffing
- `settings.rs` — Key-value settings with allowlist

### React Frontend (`src/`)

- `stores/` — Zustand stores for repos, archives, settings, UI state
- `lib/commands.ts` — Type-safe Tauri IPC bindings
- `components/repo-table/` — TanStack Table with sorting, filtering, context menus
- `components/dialogs/` — Settings, archives, migration dialogs
- `components/ui/` — shadcn/ui primitives (Radix-based)
- `hooks/` — Custom React hooks

### Concurrency Model

Tasks flow: Frontend `invoke()` → Command handler → TaskManager `enqueue()` → MPSC channel → Worker loop `recv()` → Semaphore permit → Execute → Emit Tauri event → Frontend listener.

Concurrency is controlled by a tokio semaphore (configurable 1-10). Each task gets a `CancellationToken` for stop-all support. Deduplication prevents duplicate operations on the same repo.

### Data Flow

```
URLs → SQLite (repos table) → data/<repo>.git/ → archives table + versions/*.tar.xz
       (tracking DB)          (bare clone)       (compressed archives with MD5 hashes)
```

### Status Values

- `pending`: Not yet cloned
- `active`: Live repository
- `archived`: Archived on GitHub
- `deleted`: Not found (404)
- `error`: Clone/fetch failed

### Key Files

- `src-tauri/tauri.conf.json` — App config (window, plugins, updater public key)
- `src-tauri/Cargo.toml` — Rust dependencies
- `package.json` — Frontend dependencies
- `.github/workflows/test.yml` — CI: cargo test + clippy + pnpm test + build
- `.github/workflows/release.yml` — Release: cross-platform builds on tag push

### External Dependencies

No CLI tools required at runtime. Git operations use libgit2 (via `git2` crate). Archive operations use Rust `tar` + `xz2` crates. SQLite is bundled. TLS is rustls (pure Rust).

### Security Notes

- GitHub tokens stored in OS keychain via `keyring` crate
- URL validation rejects percent-encoded path traversal
- GraphQL inputs sanitized against injection
- Archive extraction validates paths against tar-slip
- rustls TLS (no system OpenSSL dependency)
