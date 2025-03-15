import os
import sys
import subprocess
import argparse
import datetime
import logging
import json
import requests

CLONED_JSON_PATH = "cloned_repos.json"

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def validate_repo_url(url: str) -> bool:
    """
    Ensure the URL starts with https://github.com/
    (Simple placeholder validation.)
    """
    return url.startswith("https://github.com/")

def load_cloned_info() -> dict:
    """
    Load the JSON file that tracks which repos have been cloned/updated.
    Returns a dictionary of the form:
    {
      "https://github.com/user/repo.git": {
         "last_cloned": "2025-03-15 18:00:00",
         "local_path": "data/repo.git"
      },
      ...
    }
    """
    if not os.path.isfile(CLONED_JSON_PATH):
        return {}
    try:
        with open(CLONED_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

def save_cloned_info(data: dict):
    """
    Save the 'data' dictionary to cloned_repos.json
    """
    with open(CLONED_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def current_timestamp() -> str:
    """
    Returns the current date/time as a string for JSON logging.
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def clone_or_update_repo(repo_url: str, base_path="data"):
    """
    If the repo does not exist locally, clone it.
    If it exists, pull changes.
    After a successful clone or pull, record it in cloned_repos.json
    """
    # Load the JSON dictionary
    cloned_data = load_cloned_info()

    repo_name = repo_url.rstrip("/").split("/")[-1]  # e.g. "some-repo.git"
    repo_path = os.path.join(base_path, repo_name)

    # If we already have an entry in JSON, we check if the local folder exists
    if repo_url in cloned_data:
        # The local folder should match
        if os.path.isdir(repo_path):
            # We do a pull
            logging.info(f"Updating existing repo: {repo_url}")
            try:
                subprocess.run(["git", "-C", repo_path, "pull"], check=True)
                # Update last_cloned
                cloned_data[repo_url]["last_cloned"] = current_timestamp()
                save_cloned_info(cloned_data)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to update repo {repo_url}: {e}")
        else:
            # The JSON says we have it, but folder is missing, so let's re-clone
            logging.info(f"Local folder missing, re-cloning: {repo_url}")
            try:
                subprocess.run(["git", "clone", repo_url, repo_path], check=True)
                # Update JSON
                cloned_data[repo_url]["last_cloned"] = current_timestamp()
                cloned_data[repo_url]["local_path"] = repo_path
                save_cloned_info(cloned_data)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to clone repo {repo_url}: {e}")
    else:
        # No JSON entry, so definitely clone
        logging.info(f"Cloning new repo: {repo_url}")
        try:
            subprocess.run(["git", "clone", repo_url, repo_path], check=True)
            # Create a new record in JSON
            cloned_data[repo_url] = {
                "last_cloned": current_timestamp(),
                "local_path": repo_path
            }
            save_cloned_info(cloned_data)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to clone repo {repo_url}: {e}")

def compress_archive(src_path: str, dest_archive: str):
    """
    Heavy compression for the given folder using tar + xz.
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

    # For demonstration, do a raw copy of the entire repo into the archive folder.
    # In a real scenario, you might prefer 'git archive' for a clean snapshot.
    subprocess.run(["cp", "-r", repo_path, archive_folder])

    # Compress it
    archive_file = f"{archive_folder}.tar.xz"
    compress_archive(archive_folder, archive_file)

def check_for_updates(base_path="data"):
    """
    Compare local repos with remote to see if there's a new commit (placeholder).
    If new commits found, store a new version.
    Currently for demonstration: always archiving.
    """
    for repo_name in os.listdir(base_path):
        repo_path = os.path.join(base_path, repo_name)
        if not os.path.isdir(repo_path):
            continue
        logging.info(f"Detected new changes for {repo_name}, archiving...")
        create_versioned_archive(repo_path)

def detect_deleted_or_archived(repos: list):
    """
    Check if each repo is archived or deleted via the GitHub API.
    Logs status (active, archived, deleted).
    """
    for repo in repos:
        parts = repo.replace("https://github.com/", "").split("/")
        if len(parts) < 2:
            logging.warning(f"Skipping invalid repo URL for archive/delete detection: {repo}")
            continue
        owner, repo_name = parts[0], parts[1]
        api_url = f"https://api.github.com/repos/{owner}/{repo_name}"

        try:
            response = requests.get(api_url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("archived", False):
                    logging.info(f"Repo is archived on GitHub: {repo}")
                else:
                    logging.info(f"Repo is active: {repo}")
            elif response.status_code == 404:
                logging.warning(f"Repo is deleted or no longer accessible: {repo}")
            else:
                logging.warning(f"Unexpected status code {response.status_code} checking {repo}")
        except requests.RequestException as e:
            logging.warning(f"Failed to check archived/deleted status for {repo}: {e}")

def main():
    parser = argparse.ArgumentParser(description="GitHub Repo Saver")
    parser.add_argument("--repo-list", required=True, help="Path to text file containing GitHub repo URLs")
    args = parser.parse_args()

    setup_logging()

    if not os.path.isfile(args.repo_list):
        logging.error(f"Repo list file not found: {args.repo_list}")
        sys.exit(1)

    # Read repo URLs
    with open(args.repo_list, "r", encoding="utf-8") as f:
        repos = [line.strip() for line in f if line.strip()]

    valid_repos = []
    for r in repos:
        if validate_repo_url(r):
            valid_repos.append(r)
        else:
            logging.warning(f"Invalid repo URL skipped: {r}")

    # Create data folder if missing
    os.makedirs("data", exist_ok=True)

    # Clone or Update
    for repo_url in valid_repos:
        clone_or_update_repo(repo_url, base_path="data")

    # Example check for updates
    check_for_updates(base_path="data")

    # Example detection of archived or deleted repos
    detect_deleted_or_archived(valid_repos)

if __name__ == "__main__":
    main()
