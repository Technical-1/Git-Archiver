"""
Command-line interface for Git-Archiver headless mode.
"""

import os

from .config import DATA_FOLDER
from .utils import validate_repo_url
from .data_store import load_cloned_info, save_cloned_info
from .repo_manager import clone_or_update_repo


def run_headless_update(update_all=False, active_only=True, import_file=None):
    """
    Run updates in headless mode (no GUI).

    Args:
        update_all: If True, process all repos. If False, only pending ones.
        active_only: If True, skip deleted/archived repos.
        import_file: Path to a file with URLs to import first.
    """
    print("=" * 60)
    print("Git-Archiver - Headless Mode")
    print("=" * 60)

    # Import from file if specified
    if import_file:
        print(f"\nImporting URLs from {import_file}...")
        if os.path.exists(import_file):
            repos_data = load_cloned_info()
            added = 0
            with open(import_file, "r", encoding="utf-8") as f:
                for line in f:
                    url = line.strip()
                    if not url or url.startswith("#"):
                        continue
                    if not validate_repo_url(url):
                        continue
                    if not url.endswith(".git"):
                        url += ".git"
                    if url not in repos_data:
                        repo_name = url.rstrip("/").split("/")[-1]
                        repos_data[url] = {
                            "last_cloned": "",
                            "last_updated": "",
                            "local_path": os.path.join(DATA_FOLDER, repo_name),
                            "online_description": "",
                            "status": "pending"
                        }
                        added += 1
            save_cloned_info(repos_data)
            print(f"  Added {added} new URLs")
        else:
            print(f"  ERROR: File not found: {import_file}")

    # Load repos to process
    repos_data = load_cloned_info()
    print(f"\nLoaded {len(repos_data)} repositories")

    # Count by status
    status_counts = {}
    for info in repos_data.values():
        status = info.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    print("Status breakdown:", status_counts)

    # Determine which repos to update
    urls_to_process = []
    for url, info in repos_data.items():
        status = info.get("status", "")
        if active_only and status in ["deleted", "archived"]:
            continue
        if not update_all and status not in ["pending", "error"]:
            continue
        urls_to_process.append(url)

    print(f"\nProcessing {len(urls_to_process)} repositories...")

    # Process each repo
    success_count = 0
    error_count = 0
    for i, url in enumerate(urls_to_process, 1):
        print(f"\n[{i}/{len(urls_to_process)}] {url}")
        try:
            result = clone_or_update_repo(url)
            if result:
                success_count += 1
                print("  OK")
            else:
                error_count += 1
                print("  FAILED")
        except Exception as e:
            error_count += 1
            print(f"  ERROR: {e}")

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"  Processed: {len(urls_to_process)}")
    print(f"  Success: {success_count}")
    print(f"  Errors: {error_count}")
