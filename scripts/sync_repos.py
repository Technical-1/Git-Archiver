#!/usr/bin/env python3
"""
Sync Repos - Synchronize cloned_repos.json with actual data on disk.

This script:
1. Scans the data/ folder for all cloned repositories
2. Updates cloned_repos.json with correct timestamps from git log
3. Fetches current status from GitHub API
4. Reports discrepancies between JSON and actual files
5. Optionally adds missing repos from links.txt

Usage:
    python scripts/sync_repos.py [--fetch-status] [--add-missing] [--dry-run]
"""

import os
import sys
import json
import subprocess
import argparse
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration
DATA_FOLDER = "data"
JSON_PATH = "cloned_repos.json"
LINKS_FILE = "links.txt"

def load_json():
    """Load the current cloned_repos.json file."""
    if not os.path.exists(JSON_PATH):
        return {}
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error loading JSON: {e}")
        return {}

def save_json(data):
    """Save data to cloned_repos.json with backup."""
    # Create backup
    if os.path.exists(JSON_PATH):
        backup_path = f"{JSON_PATH}.backup"
        try:
            import shutil
            shutil.copy2(JSON_PATH, backup_path)
            print(f"Created backup at {backup_path}")
        except Exception as e:
            print(f"Warning: Could not create backup: {e}")

    # Write new data
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(data)} repos to {JSON_PATH}")

def get_git_last_commit_date(repo_path):
    """Get the date of the last commit in a git repository."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%ci"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse git date format: "2025-03-16 08:56:21 -0400"
            date_str = result.stdout.strip()
            # Take just the date and time part
            date_part = " ".join(date_str.split()[:2])
            return date_part
    except Exception as e:
        print(f"  Warning: Could not get git date for {repo_path}: {e}")
    return ""

def get_git_remote_url(repo_path):
    """Get the remote URL of a git repository."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Normalize URL
            if not url.endswith(".git"):
                url += ".git"
            return url
    except Exception as e:
        print(f"  Warning: Could not get remote URL for {repo_path}: {e}")
    return None

def scan_data_folder():
    """Scan the data folder for all cloned repositories."""
    repos = {}
    if not os.path.exists(DATA_FOLDER):
        print(f"Data folder '{DATA_FOLDER}' does not exist!")
        return repos

    for item in os.listdir(DATA_FOLDER):
        item_path = os.path.join(DATA_FOLDER, item)
        if not os.path.isdir(item_path):
            continue

        # Check if it's a git repository
        git_dir = os.path.join(item_path, ".git")
        if not os.path.exists(git_dir):
            continue

        # Get remote URL
        remote_url = get_git_remote_url(item_path)
        if not remote_url:
            print(f"  Skipping {item} - no remote URL found")
            continue

        # Get last commit date
        last_commit = get_git_last_commit_date(item_path)

        # Check for versions folder
        versions_path = os.path.join(item_path, "versions")
        has_archives = os.path.exists(versions_path) and len(os.listdir(versions_path)) > 0

        repos[remote_url] = {
            "local_path": item_path,
            "last_commit": last_commit,
            "has_archives": has_archives,
            "folder_name": item
        }

    return repos

def load_links_file():
    """Load URLs from links.txt file."""
    urls = []
    if not os.path.exists(LINKS_FILE):
        return urls

    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                # Normalize URL
                if line.startswith("https://github.com/") or line.startswith("http://github.com/"):
                    if not line.endswith(".git"):
                        line += ".git"
                    urls.append(line)
    return urls

def main():
    parser = argparse.ArgumentParser(description="Sync cloned_repos.json with actual data")
    parser.add_argument("--fetch-status", action="store_true",
                        help="Fetch current status from GitHub API (slow)")
    parser.add_argument("--add-missing", action="store_true",
                        help="Add missing URLs from links.txt to JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write changes, just show what would happen")
    args = parser.parse_args()

    print("=" * 60)
    print("Git-Archiver Sync Tool")
    print("=" * 60)

    # Load current JSON
    print("\n[1/4] Loading current JSON data...")
    json_data = load_json()
    print(f"  Found {len(json_data)} repos in JSON")

    # Scan data folder
    print("\n[2/4] Scanning data folder...")
    disk_repos = scan_data_folder()
    print(f"  Found {len(disk_repos)} repos on disk")

    # Compare and report
    print("\n[3/4] Comparing JSON vs Disk...")

    json_urls = set(json_data.keys())
    disk_urls = set(disk_repos.keys())

    # Repos on disk but not in JSON
    only_on_disk = disk_urls - json_urls
    if only_on_disk:
        print(f"\n  Repos on disk but NOT in JSON ({len(only_on_disk)}):")
        for url in sorted(only_on_disk)[:10]:
            print(f"    - {url}")
        if len(only_on_disk) > 10:
            print(f"    ... and {len(only_on_disk) - 10} more")

    # Repos in JSON but not on disk
    only_in_json = json_urls - disk_urls
    if only_in_json:
        print(f"\n  Repos in JSON but NOT on disk ({len(only_in_json)}):")
        for url in sorted(only_in_json)[:10]:
            print(f"    - {url}")
        if len(only_in_json) > 10:
            print(f"    ... and {len(only_in_json) - 10} more")

    # Repos with missing timestamps
    missing_timestamps = []
    for url, info in json_data.items():
        if url in disk_urls and not info.get("last_cloned"):
            missing_timestamps.append(url)

    if missing_timestamps:
        print(f"\n  Repos with missing timestamps ({len(missing_timestamps)}):")
        for url in missing_timestamps[:5]:
            print(f"    - {url}")
        if len(missing_timestamps) > 5:
            print(f"    ... and {len(missing_timestamps) - 5} more")

    # Update JSON data
    print("\n[4/4] Updating JSON data...")
    updated_count = 0
    added_count = 0

    # Update existing repos with disk data
    for url, disk_info in disk_repos.items():
        if url in json_data:
            # Update timestamps if missing
            if not json_data[url].get("last_cloned") and disk_info["last_commit"]:
                json_data[url]["last_cloned"] = disk_info["last_commit"]
                json_data[url]["last_updated"] = disk_info["last_commit"]
                updated_count += 1
            # Ensure local_path is correct
            json_data[url]["local_path"] = disk_info["local_path"]
        else:
            # Add new repo from disk
            json_data[url] = {
                "last_cloned": disk_info["last_commit"],
                "last_updated": disk_info["last_commit"],
                "local_path": disk_info["local_path"],
                "online_description": "",
                "status": "active"
            }
            added_count += 1

        # Clear any previous errors for repos that exist on disk
        if "last_error" in json_data[url]:
            del json_data[url]["last_error"]

    print(f"  Updated {updated_count} repos with missing timestamps")
    print(f"  Added {added_count} repos found on disk but not in JSON")

    # Add missing URLs from links.txt if requested
    if args.add_missing:
        print("\n  Loading URLs from links.txt...")
        all_links = load_links_file()
        links_not_in_json = [url for url in all_links if url not in json_data]
        print(f"  Found {len(links_not_in_json)} URLs not yet in JSON")

        for url in links_not_in_json:
            repo_name = url.rstrip("/").split("/")[-1]
            json_data[url] = {
                "last_cloned": "",
                "last_updated": "",
                "local_path": os.path.join(DATA_FOLDER, repo_name),
                "online_description": "",
                "status": "pending"
            }
            added_count += 1

        print(f"  Added {len(links_not_in_json)} pending repos from links.txt")

    # Save if not dry run
    if args.dry_run:
        print("\n[DRY RUN] No changes written to disk")
    else:
        print("\nSaving updated JSON...")
        save_json(json_data)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total repos in JSON: {len(json_data)}")
    print(f"  Repos on disk: {len(disk_repos)}")
    print(f"  Updated: {updated_count}")
    print(f"  Added: {added_count}")

    # Count by status
    status_counts = {}
    for info in json_data.values():
        status = info.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\n  Status breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"    {status}: {count}")

    print("\nDone!")

if __name__ == "__main__":
    main()
