# Technology Stack

## Overview

Git Archiver v2.0.0 is a complete rewrite from Python/PyQt5 to Rust/Tauri/React. The Rust backend handles all business logic, git operations, and data persistence, while the React frontend provides a modern, responsive UI. Tauri v2 bridges the two with a lightweight native shell and IPC layer.

## Core Technologies

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| Backend Language | Rust | 2021 edition | Core business logic, performance, safety |
| App Framework | Tauri | v2 | Native shell, IPC, auto-updater, cross-platform builds |
| Frontend Language | TypeScript | ~5.8 | Type-safe frontend development |
| Frontend Framework | React | 19 | Component-based UI |
| Database | SQLite | via rusqlite 0.31 | Local data persistence with ACID transactions |
| Build Tool (Frontend) | Vite | 7 | Fast HMR dev server and production bundler |
| Build Tool (Backend) | Cargo | stable | Rust package manager and build system |

## Backend (Rust)

### Runtime & Framework
- **Tauri v2**: Native application shell with IPC command system, event emitter, auto-updater plugin, and OS opener plugin
- **Tokio**: Async runtime with multi-threaded executor, semaphores, MPSC channels, and timers

### Key Dependencies

| Crate | Purpose |
|-------|---------|
| `git2` (0.19) | libgit2 bindings for clone/fetch operations (vendored OpenSSL for cross-compilation) |
| `reqwest` (0.12) | HTTP client for GitHub API with rustls TLS |
| `rusqlite` (0.31) | SQLite bindings with bundled SQLite |
| `tar` (0.4) | Archive creation and extraction |
| `xz2` (0.1) | XZ/LZMA compression for `.tar.xz` archives |
| `serde` / `serde_json` | Serialization for IPC and API responses |
| `thiserror` (2) | Ergonomic error type derivation |
| `keyring` (3) | OS keychain access (macOS Keychain, Windows Credential Manager, Linux Secret Service) |
| `dashmap` (6) | Concurrent hash map for task tracking |
| `tokio-util` (0.7) | Cancellation tokens for task management |
| `chrono` (0.4) | Date/time handling with serde support |
| `md-5` (0.10) | MD5 hashing for incremental archive detection |

### Testing

| Crate | Purpose |
|-------|---------|
| `tempfile` (3) | Temporary directories for test isolation |
| `mockito` (1) | HTTP request mocking for GitHub API tests |

## Frontend (React + TypeScript)

### UI Framework
- **React 19**: Latest React with concurrent features
- **Tailwind CSS 3**: Utility-first CSS framework
- **shadcn/ui**: Radix-based component primitives (dialog, dropdown, toast, table, badge, slider, sheet)
- **Lucide React**: Icon library

### State Management
- **Zustand 5**: Lightweight store with async actions that call Tauri IPC commands

### Data Display
- **TanStack Table 8**: Headless table with sorting, filtering, and column management

### Theming
- **next-themes**: System-aware dark/light theme toggle with persistence

### Notifications
- **Sonner 2**: Toast notification system

### Testing

| Tool | Purpose |
|------|---------|
| Vitest 4 | Test runner (Vite-native, jest-compatible) |
| Testing Library (React 16) | Component rendering and interaction testing |
| jsdom 28 | Browser environment for tests |

## Infrastructure

### CI/CD
- **GitHub Actions**: Two workflows
  - `test.yml` — Runs `cargo test`, `cargo clippy`, `pnpm test`, `pnpm build` on every push/PR to main
  - `release.yml` — Builds cross-platform binaries on tag push (`v*`), creates GitHub draft release

### Release Targets
| Platform | Target | Format |
|----------|--------|--------|
| macOS (Apple Silicon) | `aarch64-apple-darwin` | `.dmg`, `.app.tar.gz` |
| macOS (Intel) | `x86_64-apple-darwin` | `.dmg`, `.app.tar.gz` |
| Windows | `x86_64-pc-windows-msvc` | `.exe` (NSIS), `.msi` |
| Linux | `x86_64-unknown-linux-gnu` | `.deb`, `.rpm`, `.AppImage` |

### Auto-Updater
- **Tauri Updater Plugin**: Checks for updates from GitHub Releases
- **Signing**: Ed25519 minisign keys for update verification

### Security
- **GitHub Token**: Stored in OS keychain via `keyring` crate (not plaintext files)
- **TLS**: rustls (pure Rust, no system OpenSSL dependency)
- **Input Validation**: URL normalization, GraphQL injection prevention, tar-slip protection on extraction

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Binary size | ~5-7 MB | Stripped + LTO release builds |
| Concurrent tasks | 1-10 (configurable) | Tokio semaphore-controlled |
| Archive space savings | 70-90% | Incremental MD5-based diffing |
| API calls per batch | Up to 100 repos | GraphQL batching |
| Rust test count | 105 | Unit tests across all modules |
| Frontend test count | 130 | Component + store + hook tests |

## Why This Stack?

### Why Rust + Tauri over Electron?
Tauri produces ~5-7MB binaries vs Electron's ~150MB+. Rust provides memory safety, native performance, and no garbage collector pauses. Tauri v2 includes built-in auto-updater, OS keychain access, and cross-platform builds out of the box.

### Why SQLite over JSON?
The v1.x app used JSON files which were prone to corruption. SQLite provides ACID transactions, proper schema migrations, cascade deletes, and concurrent-safe access without any manual recovery tooling.

### Why libgit2 over Git CLI?
Eliminates the external `git` dependency, provides structured error handling, and enables credential callbacks for authenticated cloning without environment variable manipulation.

### Why rustls over OpenSSL?
Pure Rust TLS implementation eliminates system OpenSSL dependency, which was causing cross-compilation failures (ARM64 → x86_64 on macOS). No runtime linking issues across platforms.
