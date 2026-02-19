# Git Archiver

A cross-platform desktop application for cloning, tracking, and archiving GitHub repositories with versioned compressed backups and incremental updates.

Built with Rust and Tauri v2 for native performance, with a React + TypeScript frontend. Supports macOS (ARM64 & Intel), Windows, and Linux.

## Features

- **Repository Management** - Add, bulk import, update, and delete tracked GitHub repositories
- **Concurrent Task Engine** - Semaphore-controlled worker pool processes clone/update tasks in parallel
- **Versioned Archives** - Creates compressed `.tar.xz` archives for each update
- **Incremental Archives** - Only archives changed files using MD5 hashing (70-90% space savings)
- **Status Detection** - Detects archived/deleted repositories via GitHub API with batch GraphQL queries
- **Activity Log** - Real-time streaming log of all operations
- **Dark/Light Theme** - System-aware theme toggle with persistent preference
- **Auto-Updater** - Built-in update mechanism via Tauri's updater plugin
- **Legacy Migration** - Import repositories from the v1.x Python JSON database
- **Secure Token Storage** - GitHub token stored in OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)

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
# Rust tests (105 tests)
cargo test

# Frontend tests (130 tests)
pnpm test
```

## Project Structure

```
git-archiver-v2/
├── src/                          # React frontend
│   ├── components/               # UI components
│   │   ├── repo-table/           # Repository table with sorting/filtering
│   │   ├── dialogs/              # Settings, archives, migration dialogs
│   │   ├── ui/                   # shadcn/ui primitives
│   │   ├── add-repo-bar.tsx      # URL input with bulk import
│   │   ├── activity-log.tsx      # Streaming operation log
│   │   └── status-bar.tsx        # Task count and rate limit display
│   ├── stores/                   # Zustand state management
│   ├── hooks/                    # Custom React hooks
│   └── lib/                      # Tauri command bindings
├── src-tauri/                    # Rust backend
│   └── src/
│       ├── commands/             # Tauri IPC command handlers
│       │   ├── repos.rs          # add, list, delete, import
│       │   ├── tasks.rs          # clone, update, update_all, stop
│       │   ├── archives.rs       # list, extract, delete
│       │   ├── settings.rs       # get, save, rate_limit
│       │   └── migrate.rs        # v1.x JSON migration
│       ├── core/                 # Business logic
│       │   ├── git.rs            # Clone/fetch via libgit2
│       │   ├── github_api.rs     # REST + GraphQL API client
│       │   ├── archive.rs        # tar.xz creation/extraction
│       │   ├── hasher.rs         # MD5 incremental diff
│       │   ├── task_manager.rs   # Concurrent task queue
│       │   ├── worker.rs         # Background worker loop
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
│       └── lib.rs                # Tauri app setup
└── src-tauri/tauri.conf.json     # Tauri configuration
```

## Tech Stack

- **Backend**: Rust, Tauri v2, SQLite (rusqlite), libgit2, tokio
- **Frontend**: React 19, TypeScript, Tailwind CSS, shadcn/ui, Zustand
- **Build**: Vite, Cargo
- **Testing**: Rust unit tests (105), Vitest + Testing Library (130)
- **CI/CD**: GitHub Actions (test + release workflows)

## How It Works

1. **Add Repositories** - Provide GitHub URLs via the input bar or bulk import from a text file
2. **Clone** - Repositories are cloned via libgit2 as bare `.git` directories
3. **Track** - Repository metadata is stored in SQLite with status, timestamps, and descriptions
4. **Monitor** - GitHub API batch queries detect archived/deleted repositories
5. **Archive** - When updates are detected, incremental `.tar.xz` archives are created
6. **Version** - Archives are timestamped and tracked in the database

## License

MIT License

## Author

Jacob Kanfer - [GitHub](https://github.com/Technical-1)
