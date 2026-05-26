# Technology Stack

## Overview

Git Archiver v2.0.0 is a complete rewrite from Python/PyQt5 to Rust/Tauri/React. The Rust backend handles all business logic, git operations, and data persistence, while the React frontend provides a modern, responsive UI. Tauri v2 bridges the two with a lightweight native shell and IPC layer.

## Core Technologies

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| Backend Language | Rust | 2021 edition | Core business logic, performance, safety |
| App Framework | Tauri | v2 (with `tray-icon`) | Native shell, IPC, updater, system tray, cross-platform builds |
| Frontend Language | TypeScript | ~5.8 | Type-safe frontend development |
| Frontend Framework | React | 19 | Component-based UI |
| Database | SQLite | via rusqlite 0.31 (bundled) | Local data persistence with ACID transactions |
| Build Tool (Frontend) | Vite | 7 | Fast HMR dev server and production bundler |
| Build Tool (Backend) | Cargo | stable | Rust package manager and build system |

## Backend (Rust)

### Runtime & Framework
- **Tauri v2**: Native application shell with IPC commands, event emitter, system tray, updater plugin, notification plugin, dialog plugin, and OS opener plugin
- **Tokio**: Async runtime with multi-threaded executor, semaphores, MPSC channels, watch channels, and timers

### Key Dependencies

| Crate | Purpose |
|-------|---------|
| `git2` (0.19) | libgit2 bindings for clone/fetch operations (vendored OpenSSL — libgit2 is the only crate that still pulls OpenSSL, and it's statically linked into the binary) |
| `reqwest` (0.12) | HTTP client for GitHub API with rustls TLS, no system OpenSSL |
| `rusqlite` (0.31) | SQLite bindings with bundled SQLite |
| `tar` (0.4) | Archive creation and extraction |
| `xz2` (0.1, `static`) | XZ/LZMA compression for `.tar.xz` archives — `static` feature compiles liblzma in so notarized macOS builds with Hardened Runtime can't fail at dyld load |
| `serde` / `serde_json` | Serialization for IPC and API responses |
| `thiserror` (2) | Ergonomic error type derivation |
| `keyring` (3) | OS keychain access (macOS Keychain, Windows Credential Manager, Linux Secret Service) |
| `dashmap` (6) | Concurrent hash map for task deduplication |
| `tokio-util` (0.7) | Cancellation tokens for task management |
| `chrono` (0.4) | DST-aware local-time handling for the daily scheduler |
| `md-5` (0.10) | MD5 hashing for incremental archive detection |
| `dirs` (6) | Resolve OS-standard data and home directories |
| `log` + `env_logger` | Structured logging with env-controlled levels |

### Testing

| Crate | Purpose |
|-------|---------|
| `tempfile` (3) | Temporary directories for test isolation |
| `mockito` (1) | HTTP request mocking for GitHub API tests |

## Frontend (React + TypeScript)

### UI Framework
- **React 19**: Latest React with concurrent features
- **Tailwind CSS 3** + `@tailwindcss/typography`: Utility-first CSS framework, plus prose styles for the in-app README viewer
- **shadcn/ui**: Radix-based component primitives (dialog, dropdown, slider, slot, toast)
- **Lucide React**: Icon library

### State Management
- **Zustand 5**: Lightweight stores with async actions that call Tauri IPC commands. Separate stores for repos, settings, tasks, and the onboarding tour.

### Data Display
- **TanStack Table 8**: Headless table with sorting, filtering, and column management
- **react-markdown 10**: Markdown rendering for README content extracted from clones and archives

### Onboarding
- **react-joyride 3**: Spotlight tour that walks first-time users through the add bar, settings cog, and row-action menu using `data-tour-id` anchors

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
  - `test.yml` — Runs `cargo test`, `cargo clippy -- -D warnings`, `pnpm test`, `pnpm build`, plus `cargo audit` checks on every push/PR to main
  - `release.yml` — Builds cross-platform binaries on tag push (`v*`), signs and notarizes the macOS bundles, generates Tauri updater manifests with checksums, and creates a GitHub draft release

### Release Targets
| Platform | Target | Format |
|----------|--------|--------|
| macOS (Apple Silicon) | `aarch64-apple-darwin` | `.dmg`, `.app.tar.gz` (signed + notarized) |
| macOS (Intel) | `x86_64-apple-darwin` | `.dmg`, `.app.tar.gz` (signed + notarized) |
| Windows | `x86_64-pc-windows-msvc` | `.exe` (NSIS), `.msi` |
| Linux | `x86_64-unknown-linux-gnu` | `.deb`, `.rpm`, `.AppImage` |

### Auto-Updater
- **Tauri Updater Plugin**: Checks for updates from GitHub Releases
- **Signing**: Ed25519 minisign keys for update payload verification (passwordless signing key in CI; public key embedded in the binary at build time)
- **macOS code signing**: Developer ID Application certificate + notarytool submission via `APPLE_*` GitHub Actions secrets

### Security
- **GitHub Token**: Stored in OS keychain via `keyring` crate (not plaintext files)
- **TLS**: rustls (pure Rust, no system OpenSSL dependency)
- **Input Validation**: URL normalization, GraphQL injection prevention, tar-slip protection on extraction

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Binary size | ~5–7 MB | Stripped + LTO release builds (statically linked liblzma adds a few hundred KB on macOS) |
| Concurrent tasks | 1–10 (configurable) | Tokio semaphore-controlled |
| Archive space savings | 70–90% | Incremental MD5-based diffing on actively updated repos |
| API calls per batch | Up to 100 repos | GraphQL batching |
| Rust test count | 110 | 104 unit + 6 integration tests across all modules |
| Frontend test count | 144 | Component + store + hook tests across 15 files |

## Why This Stack?

### Why Rust + Tauri over Electron?
Tauri produces ~5-7MB binaries vs Electron's ~150MB+. Rust provides memory safety, native performance, and no garbage collector pauses. Tauri v2 includes built-in auto-updater, OS keychain access, and cross-platform builds out of the box.

### Why SQLite over JSON?
The v1.x app used JSON files which were prone to corruption. SQLite provides ACID transactions, proper schema migrations, cascade deletes, and concurrent-safe access without any manual recovery tooling.

### Why libgit2 over Git CLI?
Eliminates the external `git` dependency, provides structured error handling, and enables credential callbacks for authenticated cloning without environment variable manipulation.

### Why rustls over OpenSSL?
Pure Rust TLS implementation eliminates system OpenSSL dependency, which was causing cross-compilation failures (ARM64 → x86_64 on macOS). No runtime linking issues across platforms. libgit2 still uses OpenSSL because there's no production-ready rustls backend for it, but it's vendored and statically linked so the binary has no system OpenSSL dependency on any target.

### Why a tray app instead of "just close to quit"?
The point of Git Archiver is to fetch and snapshot repos on a schedule, which requires the process to stay running even when the user closes the window. The window-close handler hides instead of closes, and on macOS the dock icon is toggled via `ActivationPolicy::Accessory`. The tray menu becomes the persistent surface, with a live "Last sync" indicator updated by the scheduler. The cost is a slightly trickier exit path — the tray's Quit item bypasses the `ExitRequested` handler that otherwise blocks all exits — but the alternative (forcing the user to keep the window open all day) is incompatible with the product.
