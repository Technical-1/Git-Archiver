# GitHub Repo Saver

GitHub Repo Saver is a tool to automatically clone or update repositories from a list of URLs (the "git tools" list). It checks daily for updates, archives each version, and applies heavy compression to save space. If a repository becomes archived or deleted, existing local copies remain intact.

## Project Structure

- **src/**
  Contains the main Python source code for checking, cloning, compressing, and saving repositories.

- **scripts/**
  You can place any helper or utility scripts here (e.g., for daily scheduling).

- **docs/**
  Documentation files, usage instructions, architecture notes, etc.

## Usage

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Prepare a text file containing valid GitHub repo URLs, one per line (e.g. `repos.txt`).

3. Run the main script:
   ```
   python src/github_repo_saver.py --repo-list repos.txt
   ```

4. Configure a daily schedule (e.g., via cron or a scheduler library) to run the script automatically.

## Features

- Reads a list of GitHub repository URLs and clones them if not present locally.
- Checks daily for updates.
- Creates versioned archives with heavy compression for each updated repository.
- Detects if a repository is deleted or archived, preserving the last known version.
- Logs and notifies about updates or issues.

## Roadmap / Tasks

- [ ] Validate repo URLs and store them in an internal data structure.
- [ ] Clone or download each repository to a designated folder.
- [ ] Implement daily checks for updates (via cron/scheduler).
- [ ] Archive new versions with compression.
- [ ] Detect and handle deleted/archived repositories.
- [ ] Add logging and notifications.
- [ ] Write tests for each component.
- [ ] Keep documentation updated.

Feel free to contribute additional features!