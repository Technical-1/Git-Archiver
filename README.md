# Git-Archiver

A PyQt5 desktop application for cloning, tracking, and archiving GitHub repositories with version control and compression.

## Features

- **Repository Management** - Add, update, delete, and track GitHub repositories
- **Automatic Updates** - Hourly checks with 24-hour update intervals
- **Versioned Archives** - Creates compressed `.tar.xz` archives for each update
- **Incremental Archives** - Only archives changed files to save disk space (70-90% reduction)
- **Status Detection** - Detects archived/deleted repositories via GitHub API
- **Multiple Interfaces** - Desktop GUI and headless CLI for automation
- **Search & Filter** - Real-time search and status filtering
- **Context Menus** - Right-click actions (Copy URL, Open on GitHub, Update, Delete)
- **GitHub Token Support** - Configurable token for higher API rate limits

## Installation

```bash
# Clone the repository
git clone https://github.com/Technical-1/Git-Archiver.git
cd Git-Archiver

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Desktop GUI

```bash
python run.py
```

Or run as a module:
```bash
python -m src
```

### Headless CLI (for automation/cron)

```bash
# Process only pending repositories
python run.py --headless

# Update all repositories
python run.py --headless --update-all

# Include archived/deleted repos in processing
python run.py --headless --update-all --include-archived

# Import URLs from file before processing
python run.py --headless --import-file urls.txt
```

## Project Structure

```
Git-Archiver/
├── run.py                    # Convenience entry point
├── requirements.txt          # Python dependencies
├── src/
│   ├── __init__.py           # Package init (v2.0.0)
│   ├── __main__.py           # Module entry point
│   ├── main.py               # Application entry point
│   ├── cli.py                # Headless CLI mode
│   ├── config.py             # Settings and constants
│   ├── utils.py              # Utility functions
│   ├── data_store.py         # JSON persistence with recovery
│   ├── github_api.py         # GitHub API with rate limiting
│   ├── repo_manager.py       # Core repository operations
│   └── gui/
│       ├── __init__.py
│       ├── main_window.py    # Main GUI window
│       ├── widgets.py        # Enhanced table widget
│       ├── dialogs.py        # Settings and archive dialogs
│       └── workers.py        # Background QThread workers
├── scripts/
│   ├── sync_repos.py         # Sync JSON with disk state
│   ├── repair_json.py        # Recover corrupted JSON
│   └── create_fresh_json.py  # Create new JSON database
├── tests/
│   ├── test_config.py        # Config and settings tests
│   ├── test_data_store.py    # JSON persistence tests
│   ├── test_github_api.py    # GitHub API tests
│   ├── test_repo_manager.py  # Core operations tests
│   └── test_utils.py         # Utility function tests
├── data/                     # Cloned repositories (gitignored)
│   └── <repo>.git/
│       └── versions/         # Archived versions
│           ├── <timestamp>.tar.xz
│           └── <timestamp>.json  # Archive metadata
├── cloned_repos.json         # Repository database (gitignored)
├── settings.json             # User settings (gitignored)
└── CLAUDE.md                 # Development documentation
```

## How It Works

1. **Add Repositories** - Provide GitHub repository URLs via GUI or text file
2. **Clone** - Repositories are cloned as bare `.git` directories to `data/`
3. **Track** - Repository metadata is stored in `cloned_repos.json`
4. **Monitor** - GitHub API checks repository status (active/archived/deleted)
5. **Archive** - When updates are detected, compressed archives are created
6. **Version** - Archives are timestamped and stored in `versions/` subdirectory

## Data Flow

```
URLs → cloned_repos.json → data/<repo>.git/ → versions/<timestamp>.tar.xz
       (tracking DB)       (git clone)        (compressed archives)
```

## Repository Status Values

| Status | Description |
|--------|-------------|
| `pending` | Not yet cloned |
| `active` | Live repository on GitHub |
| `archived` | Archived on GitHub (read-only) |
| `deleted` | Not found (404) or private |
| `error` | Clone/pull failed |

## Configuration

### GitHub Token (Optional but Recommended)

Without a token: 60 API requests/hour
With a token: 5,000 API requests/hour

Configure via GUI Settings dialog or add to `settings.json`:
```json
{
  "github_token": "ghp_your_token_here"
}
```

## Utility Scripts

```bash
# Sync JSON database with actual disk data
python scripts/sync_repos.py --add-missing

# Recover data from corrupted JSON
python scripts/repair_json.py

# Create fresh JSON database
python scripts/create_fresh_json.py
```

## Performance

- **Shallow Clones** - Uses `--depth 1` for 5-10x faster initial clones
- **Smart Updates** - Checks for changes before pulling
- **Incremental Archives** - Only archives modified files
- **Async Archives** - Background threads keep UI responsive
- **API Caching** - 5-minute cache reduces redundant API calls

## Requirements

- Python 3.8+
- PyQt5 >= 5.15.0
- requests >= 2.25.0
- Git (command line)
- tar (with XZ compression support)
- pytest >= 7.0.0 (for running tests)

## License

MIT License

## Author

Jacob Kanfer - [GitHub](https://github.com/Technical-1)
