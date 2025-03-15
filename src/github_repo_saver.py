#!/usr/bin/env python3
"""
github_repo_saver.py

Main logic for GitHub Repo Saver:
1. Read a list of GitHub repository URLs from a text file.
2. Validate each URL.
3. Clone or update each repository locally.
4. Check daily for changes and archive new versions with compression.
5. Detect if a repository is deleted/archived, preserve existing local copies.
6. Provide logging and optional notifications.

Usage:
    python github_repo_saver.py --repo-list repos.txt

Example folder structure:
data/
  repo1/
    versions/
      2023-10-01/
      2023-10-02/
  repo2/
    versions/
      ...

"""

import os
import sys
import subprocess
import argparse
import datetime
import logging

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def validate_repo_url(url: str) -> bool:
    # Placeholder: validate if the URL is a correct GitHub repo
    # e.g., check if url starts with https://github.com/
    return url.startswith("https://github.com/")

def clone_or_update_repo(repo_url: str, base_path="data"):
    """
    If the repo does not exist locally, clone it.
    If it exists, pull changes.
    """
    repo_name = repo_url.rstrip("/").split("/")[-1]
    repo_path = os.path.join(base_path, repo_name)
    if not os.path.exists(repo_path):
        logging.info(f"Cloning new repo: {repo_url}")
        try:
            subprocess.run(["git", "clone", repo_url, repo_path], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to clone repo {repo_url}: {e}")
    else:
        logging.info(f"Updating existing repo: {repo_url}")
        try:
            subprocess.run(["git", "-C", repo_path, "pull"], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to update repo {repo_url}: {e}")

def compress_archive(src_path: str, dest_archive: str):
    """
    Heavy compression for the given folder.
    Example usage with tar + xz or other methods.
    """
    logging.info(f"Compressing {src_path} to {dest_archive}")
    try:
        subprocess.run(["tar", "-cJf", dest_archive, "-C", src_path, "."], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Compression failed for {src_path}: {e}")

def create_versioned_archive(repo_path: str):
    """
    Archive the current state of the repo into a timestamped folder.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_folder = os.path.join(repo_path, "versions", timestamp)
    os.makedirs(archive_folder, exist_ok=True)

    # Copy or checkout clean files into archive_folder (placeholder).
    # For simplicity, let's assume we do a fresh copy:
    subprocess.run(["cp", "-r", repo_path, archive_folder])

    # Compress it
    archive_file = f"{archive_folder}.tar.xz"
    compress_archive(archive_folder, archive_file)

def check_for_updates(base_path="data"):
    """
    Compare local repos with remote to see if there's a new commit.
    If new commits found, store a new version.
    Placeholder method illustrating logic.
    """
    for repo_name in os.listdir(base_path):
        repo_path = os.path.join(base_path, repo_name)
        if not os.path.isdir(repo_path):
            continue
        # Attempt to detect changes by checking 'git status' or commits
        # For brevity, we'll always assume there's an update
        logging.info(f"Detected new changes for {repo_name}, archiving...")
        create_versioned_archive(repo_path)

def detect_deleted_or_archived(repos: list):
    """
    Check if any of the repos have been deleted or archived.
    Log it or mark it.
    (Placeholder - possibly check GitHub API or remote status.)
    """
    for repo in repos:
        # If the repo is no longer accessible, log it
        pass

def main():
    parser = argparse.ArgumentParser(description="GitHub Repo Saver")
    parser.add_argument("--repo-list", required=True, help="Path to text file containing GitHub repo URLs")
    args = parser.parse_args()

    setup_logging()

    if not os.path.isfile(args.repo_list):
        logging.error(f"Repo list file not found: {args.repo_list}")
        sys.exit(1)

    # Read repo URLs
    with open(args.repo_list, "r") as f:
        repos = [line.strip() for line in f if line.strip()]

    valid_repos = []
    for r in repos:
        if validate_repo_url(r):
            valid_repos.append(r)
        else:
            logging.warning(f"Invalid repo URL skipped: {r}")

    # Clone or Update
    os.makedirs("data", exist_ok=True)
    for repo_url in valid_repos:
        clone_or_update_repo(repo_url, base_path="data")

    # Check daily updates placeholder
    # For now, just call check_for_updates directly
    check_for_updates(base_path="data")

    # Detect archived or deleted repos (placeholder)
    detect_deleted_or_archived(valid_repos)

if __name__ == "__main__":
    main()