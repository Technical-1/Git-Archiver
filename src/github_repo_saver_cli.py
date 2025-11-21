#!/usr/bin/env python3
"""
GitHub Repo Saver - Command Line Interface

Usage:
    python src/github_repo_saver_cli.py add <repo_url>
    python src/github_repo_saver_cli.py add-bulk <file_path>
    python src/github_repo_saver_cli.py update [<repo_url>]
    python src/github_repo_saver_cli.py list [--status STATUS]
    python src/github_repo_saver_cli.py delete <repo_url>
    python src/github_repo_saver_cli.py refresh-statuses
    python src/github_repo_saver_cli.py stats
"""

import sys
import argparse
import json
from typing import Optional

# Import backend module
from repo_manager import (
    setup_logging,
    validate_repo_url,
    load_cloned_info,
    clone_or_update_repo,
    detect_deleted_or_archived,
    add_repo_to_database,
    delete_repo_from_database,
    delete_multiple_repos_from_database,
    list_archives,
    get_archive_info,
    delete_archive,
    DATA_FOLDER,
)


def format_size(size_bytes):
    """Format bytes to human-readable size"""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes/1024**2:.1f} MB"
    else:
        return f"{size_bytes/1024**3:.1f} GB"


def cmd_add(repo_url: str):
    """Add a single repository"""
    if not validate_repo_url(repo_url):
        print(f"Error: Invalid repository URL: {repo_url}")
        return 1
    
    if not repo_url.endswith(".git"):
        repo_url += ".git"
    
    print(f"Adding repository: {repo_url}")
    
    if add_repo_to_database(repo_url):
        print(f"Repository added to database: {repo_url}")
        print("Cloning/updating repository...")
        success, error_msg = clone_or_update_repo(repo_url)
        if success:
            print(f"✓ Successfully processed: {repo_url}")
            return 0
        else:
            print(f"✗ Error processing {repo_url}: {error_msg}")
            return 1
    else:
        print(f"Error: Failed to add repository: {repo_url}")
        return 1


def cmd_add_bulk(file_path: str):
    """Add repositories from a file (one URL per line)"""
    try:
        with open(file_path, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        return 1
    except Exception as e:
        print(f"Error reading file: {e}")
        return 1
    
    valid_urls = []
    invalid_urls = []
    
    for url in urls:
        if validate_repo_url(url):
            if not url.endswith(".git"):
                url += ".git"
            valid_urls.append(url)
        else:
            invalid_urls.append(url)
    
    if invalid_urls:
        print(f"Warning: {len(invalid_urls)} invalid URLs skipped:")
        for url in invalid_urls:
            print(f"  - {url}")
    
    if not valid_urls:
        print("Error: No valid URLs found in file")
        return 1
    
    print(f"Adding {len(valid_urls)} repositories...")
    added_count = 0
    error_count = 0
    
    for url in valid_urls:
        if add_repo_to_database(url):
            added_count += 1
            print(f"  Added: {url}")
            success, error_msg = clone_or_update_repo(url)
            if success:
                print(f"    ✓ Processed successfully")
            else:
                print(f"    ✗ Error: {error_msg}")
                error_count += 1
        else:
            print(f"  ✗ Failed to add: {url}")
            error_count += 1
    
    print(f"\nSummary: {added_count} added, {error_count} errors")
    return 0 if error_count == 0 else 1


def cmd_update(repo_url: Optional[str] = None):
    """Update repository/repositories"""
    if repo_url:
        # Update single repository
        if not validate_repo_url(repo_url):
            print(f"Error: Invalid repository URL: {repo_url}")
            return 1
        
        if not repo_url.endswith(".git"):
            repo_url += ".git"
        
        print(f"Updating repository: {repo_url}")
        success, error_msg = clone_or_update_repo(repo_url)
        if success:
            print(f"✓ Successfully updated: {repo_url}")
            return 0
        else:
            print(f"✗ Error updating {repo_url}: {error_msg}")
            return 1
    else:
        # Update all repositories
        repos_data = load_cloned_info()
        if not repos_data:
            print("No repositories found")
            return 0
        
        print(f"Updating {len(repos_data)} repositories...")
        success_count = 0
        error_count = 0
        
        for url in repos_data.keys():
            print(f"  Updating: {url}")
            success, error_msg = clone_or_update_repo(url)
            if success:
                print(f"    ✓ Success")
                success_count += 1
            else:
                print(f"    ✗ Error: {error_msg}")
                error_count += 1
        
        print(f"\nSummary: {success_count} succeeded, {error_count} errors")
        return 0 if error_count == 0 else 1


def cmd_list(status_filter: Optional[str] = None):
    """List all repositories"""
    repos_data = load_cloned_info()
    
    if not repos_data:
        print("No repositories found")
        return 0
    
    filtered_repos = repos_data
    if status_filter:
        filtered_repos = {url: info for url, info in repos_data.items() 
                         if info.get("status", "") == status_filter}
    
    if not filtered_repos:
        print(f"No repositories found with status: {status_filter}")
        return 0
    
    print(f"\nFound {len(filtered_repos)} repository/repositories:\n")
    
    for url, info in sorted(filtered_repos.items()):
        status = info.get("status", "unknown")
        desc = info.get("online_description", "") or "No description"
        last_updated = info.get("last_updated", "Never")
        
        print(f"URL: {url}")
        print(f"  Status: {status}")
        print(f"  Description: {desc[:80]}{'...' if len(desc) > 80 else ''}")
        print(f"  Last Updated: {last_updated}")
        print()
    
    return 0


def cmd_delete(repo_url: str):
    """Delete a repository from the database"""
    if not validate_repo_url(repo_url):
        print(f"Error: Invalid repository URL: {repo_url}")
        return 1
    
    if not repo_url.endswith(".git"):
        repo_url += ".git"
    
    if delete_repo_from_database(repo_url):
        print(f"✓ Deleted repository from database: {repo_url}")
        print("Note: Local files and archives remain intact")
        return 0
    else:
        print(f"Error: Repository not found: {repo_url}")
        return 1


def cmd_refresh_statuses():
    """Refresh repository statuses"""
    print("Refreshing repository statuses...")
    updated_count = detect_deleted_or_archived(use_cache=True)
    print(f"✓ Updated {updated_count} repository/repositories")
    return 0


def cmd_stats():
    """Show statistics"""
    repos_data = load_cloned_info()
    
    if not repos_data:
        print("No repositories found")
        return 0
    
    total_repos = len(repos_data)
    active_count = sum(1 for r in repos_data.values() if r.get("status") == "active")
    archived_count = sum(1 for r in repos_data.values() if r.get("status") == "archived")
    deleted_count = sum(1 for r in repos_data.values() if r.get("status") == "deleted")
    error_count = sum(1 for r in repos_data.values() if r.get("status") == "error")
    
    # Calculate total archives
    total_archives = 0
    total_size = 0
    
    import os
    for repo_url, info in repos_data.items():
        repo_path = info.get("local_path", "")
        if os.path.exists(repo_path):
            archives = list_archives(repo_path)
            total_archives += len(archives)
            for archive_name in archives:
                archive_info = get_archive_info(repo_path, archive_name)
                if archive_info:
                    total_size += archive_info["size"]
    
    print("\n=== Repository Statistics ===\n")
    print(f"Total Repositories: {total_repos}")
    print(f"  Active: {active_count}")
    print(f"  Archived: {archived_count}")
    print(f"  Deleted: {deleted_count}")
    print(f"  Error: {error_count}")
    print(f"\nTotal Archives: {total_archives}")
    print(f"Total Size: {format_size(total_size)}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Repo Saver - Command Line Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s add https://github.com/user/repo
  %(prog)s add-bulk repos.txt
  %(prog)s update
  %(prog)s update https://github.com/user/repo
  %(prog)s list
  %(prog)s list --status archived
  %(prog)s delete https://github.com/user/repo
  %(prog)s refresh-statuses
  %(prog)s stats
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Add command
    parser_add = subparsers.add_parser('add', help='Add a single repository')
    parser_add.add_argument('repo_url', help='GitHub repository URL')
    
    # Add bulk command
    parser_add_bulk = subparsers.add_parser('add-bulk', help='Add repositories from file')
    parser_add_bulk.add_argument('file_path', help='Path to file with URLs (one per line)')
    
    # Update command
    parser_update = subparsers.add_parser('update', help='Update repository/repositories')
    parser_update.add_argument('repo_url', nargs='?', help='Repository URL (optional, updates all if omitted)')
    
    # List command
    parser_list = subparsers.add_parser('list', help='List repositories')
    parser_list.add_argument('--status', choices=['active', 'archived', 'deleted', 'error'],
                            help='Filter by status')
    
    # Delete command
    parser_delete = subparsers.add_parser('delete', help='Delete a repository')
    parser_delete.add_argument('repo_url', help='Repository URL to delete')
    
    # Refresh statuses command
    subparsers.add_parser('refresh-statuses', help='Refresh repository statuses')
    
    # Stats command
    subparsers.add_parser('stats', help='Show statistics')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Setup logging
    setup_logging()
    
    # Execute command
    if args.command == 'add':
        return cmd_add(args.repo_url)
    elif args.command == 'add-bulk':
        return cmd_add_bulk(args.file_path)
    elif args.command == 'update':
        return cmd_update(args.repo_url)
    elif args.command == 'list':
        return cmd_list(args.status)
    elif args.command == 'delete':
        return cmd_delete(args.repo_url)
    elif args.command == 'refresh-statuses':
        return cmd_refresh_statuses()
    elif args.command == 'stats':
        return cmd_stats()
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())

