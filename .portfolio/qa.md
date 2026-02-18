# Git-Archiver Q&A

## Project Overview

Git-Archiver is a PyQt5 desktop application I built to solve a personal need: preserving GitHub repositories before they disappear. It clones repositories, tracks their status via the GitHub API, and creates versioned compressed archives whenever updates are detected. The application supports both an interactive GUI for manual management and a headless CLI mode for automated scheduled updates.

### Problem Solved

Open source projects on GitHub can be deleted, made private, or archived without warning. I wanted a way to maintain local copies of repositories I depend on or find valuable, with automatic updates and compressed snapshots for historical reference.

### Target Users

- Developers who want to preserve copies of dependencies or interesting projects
- Researchers archiving open source codebases for study
- Organizations maintaining mirrors of critical external repositories
- Anyone concerned about link rot and project disappearance

## Key Features

### Repository Management
Add repositories individually via URL input or bulk import from text files. The table view displays all tracked repositories with their status, description, and timestamps. Real-time search and status filtering help navigate large collections.

### Automatic Updates
An hourly timer checks if 24 hours have passed since the last update. When triggered, all active repositories are pulled for changes. This runs in the background without blocking the UI.

### Versioned Archives
Each time a repository is updated with new commits, a timestamped `.tar.xz` archive is created. Archives use XZ compression for optimal size reduction.

### Incremental Archives
I implemented MD5-based file change detection. Only files that have changed since the last archive are included in subsequent archives. This achieves 70-90% space savings compared to full archives.

### Status Detection
The GitHub API is queried to detect if repositories have been archived or deleted. Status is color-coded in the UI: green for active, yellow for archived, red for deleted, blue for pending.

### Dual Interface
The same core logic powers both a PyQt5 desktop GUI and a headless CLI mode. The CLI supports flags like `--headless`, `--update-all`, `--import-file`, and `--include-archived` for automation via cron jobs.

### Context Menu Actions
Right-clicking any repository row provides quick actions: copy URL, open on GitHub, update immediately, remove from tracking, or delete local copy.

### GitHub Token Support
Configure a personal access token via the Settings dialog to increase API rate limits from 60 to 5,000 requests per hour.

## Technical Highlights

### Challenge: Keeping UI Responsive During Long Operations
Git clone and pull operations can take minutes for large repositories. I solved this by running all I/O operations in QThread workers that communicate with the main thread via Qt signals. The UI remains fully interactive while operations run in the background.

### Challenge: JSON Corruption from Crashes
During development, power outages and crashes occasionally corrupted the JSON database. I implemented atomic writes (write to temp file, then rename) and a recovery function that uses regex to extract valid repository entries from corrupted files. This has saved data multiple times.

### Challenge: GitHub API Rate Limits
With 400+ tracked repositories, hitting rate limits was inevitable. I implemented:
- GraphQL batch queries to check up to 100 repos in one request
- A 5-minute TTL cache to avoid redundant API calls
- Automatic backoff when rate limits are approached
- Token authentication for 83x higher limits (5000 vs 60/hr)

### Innovative Approach: Incremental Archives
Rather than storing full archives on every update (wasteful for repos that change frequently), I store MD5 hashes of all files in metadata JSON files alongside each archive. On subsequent archives, only changed files are included. For actively developed projects, this reduces archive storage by 70-90%.

### Innovative Approach: Smart Update Checks
Before pulling, I run `git fetch` followed by `git rev-list --count HEAD..@{upstream}` to check if updates actually exist. This avoids unnecessary network traffic and processing for unchanged repositories.

## Frequently Asked Questions

### Q1: Why did you build this instead of using an existing tool?

Existing solutions like `git-mirror` or GitHub's own archive feature didn't meet my specific needs. I wanted: (1) incremental archives to save space, (2) status tracking for archived/deleted repos, (3) a GUI for manual management, and (4) headless mode for automation. Building a custom solution let me optimize for my exact workflow.

### Q2: How much disk space does this use?

It depends on the repositories you track. The application itself is tiny (~200KB of Python code). Repository clones use disk space proportional to their content (not history, since I use shallow clones). Archives vary but XZ compression typically achieves 3-5x reduction. With incremental archives, subsequent versions are often 70-90% smaller than full archives.

### Q3: Can this archive private repositories?

Yes, if you configure a GitHub personal access token with appropriate permissions. The token is stored locally in `settings.json` (which is gitignored for security). Without a token, only public repositories can be accessed.

### Q4: What happens if a repository is deleted from GitHub?

The application detects this via the GitHub API (404 response) and marks the repository status as "deleted" in red. Your local clone and archives are preserved. You can still access the content locally even though the GitHub original is gone.

### Q5: How do I automate updates?

Use headless CLI mode with cron:
```bash
# Update all repos daily at 2 AM
0 2 * * * cd ~/Git-Archiver && python run.py --headless --update-all

# Process only pending repos hourly
0 * * * * cd ~/Git-Archiver && python run.py --headless
```

### Q6: Why PyQt5 instead of a web interface?

This application deals with large file operations (Git clones, archive creation) that are inherently local. A desktop app provides: direct file system access, no server deployment overhead, works offline once repos are cloned, and simpler security (no network exposure).

### Q7: How does the incremental archive feature work?

Each archive has a companion `.json` metadata file containing MD5 hashes of all archived files. When creating a new archive:
1. Compute current MD5 hashes for all files
2. Compare against the previous archive's metadata
3. Only include files whose hashes have changed
4. Save new metadata with current hashes

This means a 100MB repository that changes 5 files might produce a 500KB incremental archive instead of another 100MB.

### Q8: What if the JSON database gets corrupted?

I implemented a recovery function that:
1. Creates a backup of the corrupted file
2. Uses regex to extract valid repository entry patterns
3. Rebuilds a clean JSON with recovered data
4. Logs how many repositories were recovered

Additionally, all writes use an atomic pattern (write to `.tmp`, then rename) to prevent partial writes from corrupting the file.

### Q9: Why shallow clones instead of full history?

Shallow clones (`--depth 1`) are 5-10x faster and use significantly less disk space. For archiving purposes, I primarily care about the current state of the code, not the full commit history. If historical commits are needed, the original GitHub repo (if still available) or a full clone could be created separately.

### Q10: Why did you refactor from a monolithic to modular architecture?

The original v1.x codebase was a single 2,064-line GUI file that mixed UI, business logic, and data access. As features grew, it became difficult to test and maintain. In v2.0.0, I split the codebase into focused modules: `repo_manager.py` for business logic, `data_store.py` for persistence, `github_api.py` for API calls, and a `gui/` package with separated window, workers, dialogs, and widgets. This made the code testable (5 test modules with 60+ tests) and easier to extend.

### Q11: How do I contribute or report issues?

The repository includes comprehensive documentation in `README.md` and `CLAUDE.md` (development notes). The codebase is organized into clear modules with docstrings. Key areas for contribution include:
- Adding support for GitLab/Bitbucket
- Implementing archive deduplication
- Adding export/import for repository lists
- Removing legacy monolithic files once migration is fully verified
