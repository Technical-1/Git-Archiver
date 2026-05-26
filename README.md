# Git Archiver

A cross-platform desktop application for cloning, tracking, and archiving GitHub repositories with versioned compressed backups and incremental updates.

Built with Rust and Tauri v2 for native performance, with a React + TypeScript frontend. Supports macOS (ARM64 & Intel), Windows, and Linux.

## Features

- **Repository management** — Add, bulk import (from `.txt` / `.csv` / `.md`), update, and delete tracked GitHub repositories
- **Concurrent task engine** — Semaphore-controlled worker pool processes clone/update tasks in parallel
- **Versioned archives** — Creates compressed `.tar.xz` archives whenever a fetch detects new commits
- **Incremental archives** — Only archives changed files using MD5 hashing (typically 70–90% space savings on actively updated repos)
- **Daily auto-sync** — Optional DST-aware scheduler that triggers update-all at a configurable local time
- **Background tray app** — Closing the window hides to the system tray instead of quitting; tray menu shows the last sync time
- **Status detection** — Detects archived/deleted repositories via GitHub GraphQL batch queries (up to 100 repos per call)
- **Activity log** — Real-time streaming log of every clone, fetch, and archive operation
- **Onboarding tour** — Joyride-powered spotlight walkthrough on first launch
- **Dark/Light theme** — System-aware theme toggle with persistent preference
- **Signed auto-updater** — Code-signed and notarized on macOS; Ed25519-signed updater payloads verified by Tauri's updater plugin
- **Secure token storage** — GitHub token stored in the OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)

## Download

Pre-built binaries for all platforms are available on the [Releases](https://github.com/Technical-1/Git-Archiver/releases) page:

| Platform | Formats |
|----------|---------|
| macOS (Apple Silicon) | `.dmg`, `.app.tar.gz` |
| macOS (Intel) | `.dmg`, `.app.tar.gz` |
| Windows | `.exe` (NSIS), `.msi` |
| Linux | `.deb`, `.rpm`, `.AppImage` |

## Development

### Prerequisites

- [Rust](https://rustup.rs/) (stable)
- [Node.js](https://nodejs.org/) 20+
- [pnpm](https://pnpm.io/) 9+
- System dependencies (Linux only): `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf`

### Setup

```bash
cd git-archiver-v2
pnpm install
```

### Run (Development)

```bash
pnpm tauri dev
```

### Build (Production)

```bash
pnpm tauri build
```

### Testing

```bash
# Rust tests (104 unit + 6 integration)
cargo test

# Frontend tests (144 tests)
pnpm test
```

## Project Structure

```
git-archiver-v2/
├── src/                          # React frontend
│   ├── components/               # UI components
│   │   ├── repo-table/           # Repository table with sorting/filtering
│   │   ├── dialogs/              # Settings, archive viewer, README viewer
│   │   ├── ui/                   # shadcn/ui primitives
│   │   ├── add-repo-bar.tsx      # URL input with bulk import
│   │   ├── activity-log.tsx     # Streaming operation log
│   │   ├── onboarding-tour.tsx   # First-launch Joyride spotlight tour
│   │   ├── safe-markdown.tsx     # Sandboxed markdown renderer for READMEs
│   │   └── status-bar.tsx        # Task count and rate limit display
│   └── stores/                   # Zustand stores (repos, settings, tasks, tour)
├── src-tauri/                    # Rust backend
│   └── src/
│       ├── commands/             # Tauri IPC command handlers
│       │   ├── repos.rs          # add, list, delete, import_from_file
│       │   ├── tasks.rs          # clone, update, update_all, stop
│       │   ├── archives.rs       # list, extract, delete, get_*_readme
│       │   └── settings.rs       # get, save, rate_limit
│       ├── core/                 # Business logic
│       │   ├── git.rs            # Clone/fetch via libgit2
│       │   ├── github_api.rs     # REST + GraphQL API client
│       │   ├── archive.rs        # tar.xz creation/extraction
│       │   ├── hasher.rs         # MD5 incremental diff
│       │   ├── task_manager.rs   # Concurrent task queue
│       │   ├── worker.rs         # Background worker loop
│       │   ├── scheduler.rs      # DST-aware daily update-all scheduler
│       │   └── url.rs            # URL validation/normalization
│       ├── db/                   # SQLite data layer
│       │   ├── migrations.rs     # Schema migrations
│       │   ├── repos.rs          # Repository CRUD
│       │   ├── archives.rs       # Archive records
│       │   ├── file_hashes.rs    # MD5 hash storage
│       │   └── settings.rs       # App settings
│       ├── models.rs             # Shared data types
│       ├── error.rs              # Error types
│       ├── state.rs              # App state (DB, TaskManager, GitHub client)
│       ├── tray.rs               # System tray icon + "Last sync" menu
│       └── lib.rs                # Tauri app setup, tray + scheduler spawn
└── src-tauri/tauri.conf.json     # Tauri configuration
```

## Tech Stack

- **Backend**: Rust 2021, Tauri v2 (with `tray-icon`), SQLite (rusqlite), libgit2, tokio
- **Frontend**: React 19, TypeScript ~5.8, Tailwind CSS 3, shadcn/ui, Zustand 5, react-joyride
- **Build**: Vite 7, Cargo
- **Testing**: Rust (110 tests: 104 unit + 6 integration), Vitest 4 + Testing Library (144 tests)
- **CI/CD**: GitHub Actions (test + release workflows with macOS code signing & notarization)

## How It Works

1. **Add repositories** — Provide GitHub URLs via the input bar or bulk import from a `.txt` / `.csv` / `.md` file
2. **Clone** — Repositories are cloned via libgit2 as bare `.git` directories
3. **Track** — Repository metadata is stored in SQLite with status, timestamps, and descriptions
4. **Monitor** — GitHub GraphQL batch queries detect archived/deleted repositories without burning REST rate limits
5. **Archive** — When fetches detect new commits, incremental `.tar.xz` archives are created
6. **Schedule** — Optional daily scheduler triggers update-all at a configurable time; tray menu shows last sync
7. **Version** — Archives are timestamped and tracked in the database with cascading deletes

## License

MIT License

## Author

Jacob Kanfer - [GitHub](https://github.com/Technical-1)

