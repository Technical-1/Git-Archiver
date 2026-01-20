# Git-Archiver Technology Stack

## Overview

Git-Archiver is a desktop application built with Python and PyQt5 that provides both GUI and CLI interfaces for archiving GitHub repositories.

## Frontend

### PyQt5 (v5.15.0+)
- **Role**: Desktop GUI framework
- **Why I chose it**: PyQt5 provides native-looking widgets across platforms (macOS, Windows, Linux) with a mature, well-documented API. I considered alternatives like Tkinter (too basic), Electron (too heavy for a Python backend), and wxPython (less modern styling). PyQt5 struck the right balance between capability and development speed.

### Key GUI Components
| Component | Purpose |
|-----------|---------|
| `QTableWidget` | Repository list with sortable columns |
| `QThread` | Background workers for non-blocking operations |
| `QTimer` | Scheduled auto-updates (hourly checks) |
| `QMenu` | Context menus for row actions |
| `QDialog` | Settings and archive viewer modals |
| `QProgressBar` | Visual feedback during bulk operations |

## Backend

### Python 3.8+
- **Role**: Core language
- **Why I chose it**: Python's extensive standard library, excellent subprocess handling for Git operations, and native JSON support made it ideal. The async potential with `concurrent.futures.ThreadPoolExecutor` handles concurrent operations well.

### Core Libraries

| Library | Version | Purpose | Why I Chose It |
|---------|---------|---------|----------------|
| `requests` | 2.25.0+ | HTTP client for GitHub API | Simple, synchronous API that's easy to debug. I considered `httpx` but didn't need async HTTP. |
| `subprocess` | stdlib | Git and tar command execution | Standard library, reliable process management with timeouts |
| `threading` | stdlib | Thread safety primitives | Locks for JSON file access, thread-safe caching |
| `json` | stdlib | Data serialization | Native Python, no external dependencies needed |
| `hashlib` | stdlib | MD5 file hashing for incremental archives | Built-in, performant for file comparison |

### Testing

| Tool | Version | Purpose |
|------|---------|---------|
| `pytest` | 7.0.0+ | Unit testing framework |

## Database / Storage

### JSON File Storage
- **Primary Database**: `cloned_repos.json`
- **Why not SQLite?**: For this use case with ~400-500 repositories, JSON provides:
  - Human-readable format for debugging
  - Easy backup (just copy the file)
  - No database driver dependencies
  - Simple atomic writes via temp file + rename

### Data Schema
```json
{
  "https://github.com/user/repo.git": {
    "last_cloned": "2025-01-14 12:00:00",
    "last_updated": "2025-01-14 13:30:00",
    "local_path": "data/repo.git",
    "online_description": "Repository description from GitHub",
    "status": "active",
    "last_error": ""
  }
}
```

### File Storage
- **Repository Data**: `data/<repo-name>.git/` - Shallow git clones
- **Archives**: `data/<repo-name>.git/versions/*.tar.xz` - XZ compressed tarballs
- **Archive Metadata**: `data/<repo-name>.git/versions/*.json` - File hashes for incremental archiving

## External Dependencies

### System Requirements

| Tool | Purpose | Notes |
|------|---------|-------|
| `git` | Clone and pull repositories | Must be in PATH |
| `tar` | Archive creation | With XZ compression support |

### GitHub APIs

| API | Purpose | Rate Limit |
|-----|---------|------------|
| REST API v3 | Individual repo metadata | 60/hr (unauth), 5000/hr (auth) |
| GraphQL API | Batch status checks (up to 100 repos) | 5000 points/hr (auth) |

## Infrastructure

### Local Deployment
This is a desktop application with no server infrastructure. All data is stored locally:

```
~/Git-Archiver/
├── src/                    # Application code
├── data/                   # Cloned repos and archives
├── cloned_repos.json       # Repository database
├── settings.json           # User settings (token, window size)
└── auto_update_config.json # Last update timestamp
```

### Automation Support
The headless CLI mode enables cron-based automation:

```bash
# Example cron job (daily at 2 AM)
0 2 * * * cd ~/Git-Archiver && python run.py --headless --update-all
```

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Initial clone speed | ~5-10x faster | Using `--depth 1` shallow clones |
| Archive space savings | 70-90% | Incremental archives with MD5 diff |
| API calls per batch | Up to 100 repos | GraphQL batching |
| API cache TTL | 5 minutes | Reduces redundant calls |
| UI responsiveness | Non-blocking | QThread workers for all I/O |

## Security Considerations

### GitHub Token Storage
- Token stored in `settings.json` (local file)
- File is gitignored to prevent accidental commits
- Token provides authenticated API access (5000 req/hr vs 60 req/hr)

### Data Integrity
- Atomic JSON writes prevent corruption
- Automatic backup creation before writes
- Recovery function can extract valid entries from corrupted JSON

## Development Dependencies

```
# requirements.txt
PyQt5>=5.15.0      # GUI framework
requests>=2.25.0   # HTTP client
pytest>=7.0.0      # Testing (optional)
```

## Why Not...?

### Why not a web app?
A desktop application made more sense because:
- Large file operations (Git clones, archive creation) are local
- No need for multi-user access
- Simpler deployment (just run Python)
- Works offline once repos are cloned

### Why not async/await?
I considered `asyncio` but:
- PyQt5 has its own event loop (QThread works better)
- `subprocess` calls are inherently blocking
- Threading with locks was simpler to reason about

### Why not a proper database?
SQLite or PostgreSQL would be overkill:
- Only ~400-500 records max
- No complex queries needed
- JSON is human-readable for debugging
- Easy to backup and version control

### Why XZ compression?
- Better compression ratio than gzip (typically 30-50% smaller)
- Slower compression but faster decompression
- For archival purposes, compression ratio matters more than speed
