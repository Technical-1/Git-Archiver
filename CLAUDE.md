# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Git-Archiver is a PyQt5 desktop application that clones GitHub repositories, tracks their status via the GitHub API, and creates versioned `.tar.xz` archives when updates are detected. Supports GUI and headless CLI modes.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run GUI
python run.py
python -m src

# Headless mode (for cron/automation)
python run.py --headless                          # Process pending only
python run.py --headless --update-all             # Update all repos
python run.py --headless --update-all --include-archived  # Include archived/deleted
python run.py --headless --import-file urls.txt   # Import URLs first

# Run tests
pytest
pytest tests/test_utils.py -v                     # Single test file
pytest tests/test_utils.py::TestValidateRepoUrl -v  # Single test class

# Utility scripts
python scripts/sync_repos.py --add-missing        # Sync JSON with disk
python scripts/repair_json.py                     # Recover corrupted JSON
python scripts/create_fresh_json.py               # Create fresh JSON database
```

## Architecture

### Core Module: `src/repo_manager.py`

This is the main backend module containing most business logic. Key components:

- **Thread safety**: Uses `_json_write_lock` for atomic JSON operations
- **API caching**: 5-minute TTL cache (`_github_api_cache`) reduces GitHub API calls
- **GraphQL batching**: `batch_get_repo_descriptions()` fetches up to 100 repos per query
- **Incremental archives**: Only archives changed files using MD5 file hashes stored in `.json` metadata files

Key functions:
- `clone_or_update_repo()` - Orchestrates clone/pull/archive workflow
- `create_versioned_archive()` - Creates `.tar.xz` archives, supports async mode
- `detect_deleted_or_archived()` - Batch checks repository status via GitHub API

### GUI Threading Model (`src/gui/workers.py`)

PyQt5 QThread workers keep UI responsive:
- `CloneWorker` - Single repo clone/update
- `BulkCloneWorker` - Multiple repos with stop support
- `RefreshWorker` - Status refresh

All emit signals (`finished_signal`, `progress_signal`) to update UI.

### Data Flow

```
URLs → cloned_repos.json → data/<repo>.git/ → versions/<timestamp>.tar.xz
       (tracking DB)       (shallow clone)    (compressed archives + .json metadata)
```

### Status Values

- `pending`: Not yet cloned
- `active`: Live repository
- `archived`: Archived on GitHub
- `deleted`: Not found (404)
- `error`: Clone/pull failed

### File Locations

- `cloned_repos.json` - Repository database (root)
- `settings.json` - User settings (GitHub token, window size)
- `data/<repo>.git/` - Cloned repositories
- `data/<repo>.git/versions/` - Archive files

### External Dependencies

Requires `git` and `tar` CLI tools available in PATH.
