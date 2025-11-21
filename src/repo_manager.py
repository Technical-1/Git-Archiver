#!/usr/bin/env python3
"""
Backend module for GitHub Repo Saver.
Handles all repository management logic without GUI dependencies.
"""

import os
import json
import subprocess
import logging
import datetime
import requests
import threading
from typing import Dict, Tuple, Optional
from time import time


###############################################################################
#                               CONFIGURATION
###############################################################################

CLONED_JSON_PATH = os.path.join("config", "cloned_repos.json")
DATA_FOLDER = "data"  # local folder where repos will be cloned
AUTO_UPDATE_CONFIG_PATH = os.path.join("config", "auto_update_config.json")

# Thread-safe JSON write lock
_json_write_lock = threading.Lock()

# GitHub API cache (TTL: 5 minutes)
_github_api_cache = {}
_github_api_cache_lock = threading.Lock()
GITHUB_API_CACHE_TTL = 300  # 5 minutes


###############################################################################
#                               LOGGING
###############################################################################

def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


###############################################################################
#                               URL VALIDATION
###############################################################################

def validate_repo_url(url: str) -> bool:
    """
    Validate that a URL is a proper GitHub repository URL.
    
    Args:
        url: The URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not url.startswith("https://github.com/"):
        return False
    
    # Check if URL has at least owner/repo format
    parts = url.strip("/").split("/")
    if len(parts) < 5:  # https:, '', github.com, owner, repo
        return False
    
    # Check for valid repo name (alphanumeric, hyphens, underscores, dots)
    repo_name = parts[-1].replace(".git", "")
    if not repo_name or not all(c.isalnum() or c in "-_." for c in repo_name):
        return False
        
    return True


###############################################################################
#                               DATA PERSISTENCE
###############################################################################

def load_cloned_info() -> Dict[str, Dict]:
    """
    Load repository data from JSON file.
    
    Returns:
        Dictionary mapping repo URLs to their metadata:
        {
            "https://github.com/user/repo.git": {
                "last_cloned": "YYYY-MM-DD HH:MM:SS",
                "last_updated": "YYYY-MM-DD HH:MM:SS",
                "local_path": "data/repo.git",
                "online_description": "...",
                "status": "active"/"archived"/"deleted"/"error",
            },
            ...
        }
    """
    # Ensure config directory exists
    config_dir = os.path.dirname(CLONED_JSON_PATH)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    
    if not os.path.isfile(CLONED_JSON_PATH):
        return {}
    try:
        with open(CLONED_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.error(f"Failed to load cloned repos data: {e}")
        return {}


def save_cloned_info(data: Dict[str, Dict]):
    """
    Save repository data to JSON file using atomic write pattern.
    Thread-safe version.
    
    Args:
        data: Dictionary mapping repo URLs to their metadata
    """
    with _json_write_lock:
        temp_file = f"{CLONED_JSON_PATH}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            # On Windows, we need to remove the target file first
            if os.name == 'nt' and os.path.exists(CLONED_JSON_PATH):
                os.unlink(CLONED_JSON_PATH)
                
            # Atomic rename operation
            os.rename(temp_file, CLONED_JSON_PATH)
        except Exception as e:
            logging.error(f"Failed to save cloned repo data: {e}")
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass
            raise


def update_repo_record(repo_url: str, updates: Dict) -> bool:
    """
    Thread-safe function to update a single repository record without loading/saving entire file.
    More efficient for single updates.
    
    Args:
        repo_url: Repository URL
        updates: Dictionary of fields to update
        
    Returns:
        True if successful
    """
    with _json_write_lock:
        data = load_cloned_info()
        if repo_url not in data:
            return False
        data[repo_url].update(updates)
        save_cloned_info(data)
        return True


def current_timestamp() -> str:
    """Return the current local time as a formatted string."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


###############################################################################
#                               GITHUB API
###############################################################################

def get_online_repo_description(owner: str, repo_name: str, use_cache: bool = True) -> Tuple[str, bool, bool]:
    """
    Query GitHub API to fetch repository description and status.
    Uses caching to reduce API calls.
    
    Args:
        owner: GitHub repository owner
        repo_name: Repository name
        use_cache: Whether to use cached results (default True)
        
    Returns:
        Tuple of (description_str, is_archived_bool, is_deleted_bool)
    """
    cache_key = f"{owner}/{repo_name}"
    current_time = time()
    
    # Check cache first
    if use_cache:
        with _github_api_cache_lock:
            if cache_key in _github_api_cache:
                cached_time, cached_result = _github_api_cache[cache_key]
                if current_time - cached_time < GITHUB_API_CACHE_TTL:
                    return cached_result
    
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
    try:
        resp = requests.get(
            api_url, 
            headers={"Accept": "application/vnd.github.v3+json"}, 
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            desc = data.get("description", "") or ""
            archived = data.get("archived", False)
            result = (desc, archived, False)
        elif resp.status_code == 404:
            result = ("", False, True)  # repo does not exist or is private/deleted
        else:
            logging.warning(f"Unexpected status code {resp.status_code} fetching {owner}/{repo_name}")
            result = ("", False, False)
        
        # Cache the result
        if use_cache:
            with _github_api_cache_lock:
                _github_api_cache[cache_key] = (current_time, result)
        
        return result
    except requests.RequestException as e:
        logging.warning(f"Failed to fetch {owner}/{repo_name}: {e}")
        return "", False, False


def batch_get_repo_descriptions(repos: list, use_cache: bool = True) -> Dict[str, Tuple[str, bool, bool]]:
    """
    Batch fetch multiple repository descriptions using GraphQL API.
    More efficient than individual REST API calls.
    
    Args:
        repos: List of (owner, repo_name) tuples
        use_cache: Whether to use cached results (default True)
        
    Returns:
        Dictionary mapping "owner/repo" to (description, is_archived, is_deleted)
    """
    if not repos:
        return {}
    
    current_time = time()
    results = {}
    repos_to_fetch = []
    
    # Check cache first
    if use_cache:
        with _github_api_cache_lock:
            for owner, repo_name in repos:
                cache_key = f"{owner}/{repo_name}"
                if cache_key in _github_api_cache:
                    cached_time, cached_result = _github_api_cache[cache_key]
                    if current_time - cached_time < GITHUB_API_CACHE_TTL:
                        results[cache_key] = cached_result
                    else:
                        repos_to_fetch.append((owner, repo_name))
                else:
                    repos_to_fetch.append((owner, repo_name))
    else:
        repos_to_fetch = repos
    
    if not repos_to_fetch:
        return results
    
    # Use GraphQL API for batching (up to 100 repos per query)
    # Note: GraphQL API requires authentication for private repos, but works for public repos
    # We'll use REST API fallback if GraphQL fails
    try:
        # Build GraphQL query (batch up to 100 repos)
        query_parts = []
        repos_batch = repos_to_fetch[:100]  # GitHub GraphQL limit
        
        for idx, (owner, repo_name) in enumerate(repos_batch):
            alias = f"repo{idx}"
            query_parts.append(
                f'{alias}: repository(owner: "{owner}", name: "{repo_name}") {{ '
                f'description isArchived isPrivate }}'
            )
        
        query = f"query {{ {' '.join(query_parts)} }}"
        
        # Try GraphQL API (works for public repos without auth)
        graphql_url = "https://api.github.com/graphql"
        resp = requests.post(
            graphql_url,
            json={"query": query},
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=15
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data and not data.get("errors"):
                for idx, (owner, repo_name) in enumerate(repos_batch):
                    alias = f"repo{idx}"
                    cache_key = f"{owner}/{repo_name}"
                    repo_data = data["data"].get(alias)
                    
                    if repo_data:
                        desc = repo_data.get("description", "") or ""
                        archived = repo_data.get("isArchived", False)
                        results[cache_key] = (desc, archived, False)
                    else:
                        # Repository not found or private
                        results[cache_key] = ("", False, True)
                    
                    # Cache the result
                    if use_cache:
                        with _github_api_cache_lock:
                            _github_api_cache[cache_key] = (current_time, results[cache_key])
                
                # Handle remaining repos if more than 100
                if len(repos_to_fetch) > 100:
                    remaining_results = batch_get_repo_descriptions(repos_to_fetch[100:], use_cache)
                    results.update(remaining_results)
                
                logging.info(f"Batch fetched {len(repos_batch)} repositories via GraphQL")
                return results
            else:
                logging.warning(f"GraphQL API returned errors: {data.get('errors', [])}")
    except Exception as e:
        logging.warning(f"GraphQL batch query failed, falling back to REST API: {e}")
    
    # Fall back to individual REST API calls
    logging.info(f"Falling back to REST API for {len(repos_to_fetch)} repositories")
    for owner, repo_name in repos_to_fetch:
        cache_key = f"{owner}/{repo_name}"
        if cache_key not in results:
            results[cache_key] = get_online_repo_description(owner, repo_name, use_cache)
    
    return results


def parse_repo_url(repo_url: str) -> Optional[Tuple[str, str]]:
    """
    Parse a GitHub repository URL into owner and repo name.
    
    Args:
        repo_url: Full GitHub repository URL
        
    Returns:
        Tuple of (owner, repo_name) or None if invalid
    """
    parts = repo_url.replace("https://github.com/", "").split("/")
    if len(parts) >= 2:
        owner = parts[0]
        raw_repo = parts[1].replace(".git", "")
        return owner, raw_repo
    return None


###############################################################################
#                               ARCHIVE MANAGEMENT
###############################################################################

def _get_file_hashes(repo_path: str) -> Dict[str, str]:
    """Get MD5 hashes of all files in repo (excluding .git)"""
    import hashlib
    file_hashes = {}
    
    for root, dirs, files in os.walk(repo_path):
        # Skip .git directory
        dirs[:] = [d for d in dirs if d != '.git' and d != 'versions']
        
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, repo_path)
            
            try:
                with open(file_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                    file_hashes[rel_path] = file_hash
            except Exception as e:
                logging.warning(f"Error hashing {file_path}: {e}")
    
    return file_hashes


def _get_changed_files(repo_path: str, last_archive_path: str = None) -> list:
    """Get list of changed files since last archive"""
    current_hashes = _get_file_hashes(repo_path)
    
    if not last_archive_path or not os.path.exists(last_archive_path):
        # First archive - include all files
        return list(current_hashes.keys())
    
    # Extract previous hashes from archive metadata
    metadata_path = last_archive_path.replace('.tar.xz', '.json')
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                previous_hashes = metadata.get('file_hashes', {})
        except Exception:
            previous_hashes = {}
    else:
        previous_hashes = {}
    
    # Find changed files
    changed_files = []
    for file_path, current_hash in current_hashes.items():
        previous_hash = previous_hashes.get(file_path)
        if previous_hash != current_hash:
            changed_files.append(file_path)
    
    # Also include deleted files
    for file_path in previous_hashes:
        if file_path not in current_hashes:
            changed_files.append(file_path)
    
    return changed_files


def create_versioned_archive(repo_path: str, async_mode: bool = False, incremental: bool = True) -> bool:
    """
    Compress the repo folder into a timestamped archive.
    Supports incremental archives (only changed files) to save space.
    Can run in background thread for non-blocking operation.
    
    Args:
        repo_path: Path to the repository folder
        async_mode: If True, runs in background thread (default False)
        incremental: If True, only archive changed files (default True)
        
    Returns:
        True if successful (or queued for async), False otherwise
    """
    def _create_archive():
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        versions_folder = os.path.join(repo_path, "versions")
        os.makedirs(versions_folder, exist_ok=True)

        archive_path = os.path.join(versions_folder, f"{timestamp}.tar.xz")
        logging.info(f"Creating new archive: {archive_path}")
        
        try:
            # Get list of archives to find the last one
            archives = list_archives(repo_path)
            last_archive_path = None
            if incremental and archives:
                last_archive_path = os.path.join(versions_folder, archives[0])
            
            if incremental and last_archive_path:
                # Incremental archive - only changed files
                changed_files = _get_changed_files(repo_path, last_archive_path)
                if not changed_files:
                    logging.info(f"No changes detected, skipping archive creation")
                    return True
                
                logging.info(f"Creating incremental archive with {len(changed_files)} changed files")
                
                # Create archive with only changed files
                # Create a temporary file list
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
                    for file_path in changed_files:
                        f.write(f"{file_path}\n")
                    file_list_path = f.name
                
                try:
                    subprocess.run(
                        ["tar", "-cJf", archive_path, "--exclude=.git", "--exclude=versions", 
                         "-C", repo_path, "-T", file_list_path],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                finally:
                    os.unlink(file_list_path)
            else:
                # Full archive - all files
                logging.info("Creating full archive")
                subprocess.run(
                    ["tar", "-cJf", archive_path, "--exclude=.git", "--exclude=versions", 
                     "-C", repo_path, "."],
                    check=True, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE
                )
            
            # Save metadata with file hashes
            metadata_path = archive_path.replace('.tar.xz', '.json')
            file_hashes = _get_file_hashes(repo_path)
            metadata = {
                "timestamp": timestamp,
                "file_hashes": file_hashes,
                "incremental": incremental and last_archive_path is not None,
                "changed_files_count": len(_get_changed_files(repo_path, last_archive_path)) if incremental and last_archive_path else len(file_hashes)
            }
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Verify the archive was created successfully
            if os.path.exists(archive_path) and os.path.getsize(archive_path) > 0:
                archive_size = os.path.getsize(archive_path)
                size_mb = archive_size / (1024 * 1024)
                logging.info(f"Archive created successfully: {archive_path} ({size_mb:.2f} MB)")
                return True
            else:
                logging.error(f"Archive creation failed, output file not found or empty: {archive_path}")
                return False
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to create archive for {repo_path}: {e}")
            error_output = e.stderr.decode() if hasattr(e, 'stderr') and e.stderr else 'No error output'
            logging.error(f"Error output: {error_output}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error creating archive: {e}")
            return False
    
    if async_mode:
        # Run in background thread
        thread = threading.Thread(target=_create_archive, daemon=True)
        thread.start()
        return True
    else:
        return _create_archive()


def list_archives(repo_path: str) -> list:
    """
    List all archive files for a repository.
    
    Args:
        repo_path: Path to the repository folder
        
    Returns:
        List of archive filenames (sorted, newest first)
    """
    versions_dir = os.path.join(repo_path, "versions")
    if not os.path.isdir(versions_dir):
        return []
    
    archives = [f for f in os.listdir(versions_dir) if f.endswith(".tar.xz")]
    archives.sort(reverse=True)
    return archives


def get_archive_info(repo_path: str, archive_name: str) -> Optional[Dict]:
    """
    Get information about a specific archive.
    
    Args:
        repo_path: Path to the repository folder
        archive_name: Name of the archive file
        
    Returns:
        Dictionary with archive info or None if not found
    """
    versions_dir = os.path.join(repo_path, "versions")
    archive_path = os.path.join(versions_dir, archive_name)
    
    if not os.path.exists(archive_path):
        return None
    
    size = os.path.getsize(archive_path)
    timestamp = archive_name.split(".")[0]
    
    try:
        date_obj = datetime.datetime.strptime(timestamp, "%Y%m%d-%H%M%S")
        date_str = date_obj.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        date_str = timestamp
    
    return {
        "name": archive_name,
        "path": archive_path,
        "size": size,
        "timestamp": timestamp,
        "date_str": date_str
    }


def delete_archive(repo_path: str, archive_name: str) -> bool:
    """
    Delete an archive file.
    
    Args:
        repo_path: Path to the repository folder
        archive_name: Name of the archive file to delete
        
    Returns:
        True if successful, False otherwise
    """
    versions_dir = os.path.join(repo_path, "versions")
    archive_path = os.path.join(versions_dir, archive_name)
    
    try:
        if os.path.exists(archive_path):
            os.unlink(archive_path)
            return True
        return False
    except Exception as e:
        logging.error(f"Failed to delete archive {archive_path}: {e}")
        return False


###############################################################################
#                               GIT OPERATIONS
###############################################################################

def clone_repo(repo_url: str, repo_path: str, timeout: int = 600, shallow: bool = True) -> Tuple[bool, str]:
    """
    Clone a repository with optional shallow clone for faster initial clone.
    
    Args:
        repo_url: GitHub repository URL
        repo_path: Local path where to clone
        timeout: Timeout in seconds (default 600 = 10 minutes)
        shallow: Use shallow clone (depth=1) for faster cloning (default True)
        
    Returns:
        Tuple of (success: bool, error_message: str)
    """
    logging.info(f"Cloning {repo_url} -> {repo_path}")
    try:
        os.makedirs(DATA_FOLDER, exist_ok=True)
        
        # Build git clone command
        clone_cmd = ["git", "clone"]
        if shallow:
            clone_cmd.extend(["--depth", "1"])
        clone_cmd.extend([repo_url, repo_path])
        
        clone_proc = subprocess.run(
            clone_cmd,
            check=False, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout
        )
        if clone_proc.returncode == 0:
            return True, ""
        else:
            err_msg = clone_proc.stdout.strip()
            logging.error(f"Failed to clone {repo_url}: {err_msg}")
            return False, err_msg
    except subprocess.TimeoutExpired:
        error_msg = f"Clone timed out after {timeout} seconds"
        logging.error(f"Timeout cloning {repo_url}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Clone exception: {str(e)}"
        logging.error(f"Exception during clone for {repo_url}: {error_msg}")
        return False, error_msg


def check_repo_has_updates(repo_path: str) -> Tuple[bool, str]:
    """
    Check if repository has updates available without pulling.
    Uses git fetch + log comparison for efficiency.
    
    Args:
        repo_path: Local path to the repository
        
    Returns:
        Tuple of (has_updates: bool, error_message: str)
    """
    try:
        # Fetch latest refs without merging
        fetch_proc = subprocess.run(
            ["git", "-C", repo_path, "fetch", "--quiet"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60
        )
        
        if fetch_proc.returncode != 0:
            return False, fetch_proc.stdout.strip()
        
        # Check if local branch is behind remote
        status_proc = subprocess.run(
            ["git", "-C", repo_path, "rev-list", "--count", "HEAD..@{upstream}"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        
        if status_proc.returncode == 0:
            behind_count = status_proc.stdout.strip()
            return bool(behind_count and int(behind_count) > 0), ""
        else:
            # Fallback: try to compare commits
            log_proc = subprocess.run(
                ["git", "-C", repo_path, "log", "HEAD..@{upstream}", "--oneline"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )
            has_updates = bool(log_proc.stdout.strip())
            return has_updates, ""
    except subprocess.TimeoutExpired:
        return False, "Check timed out"
    except Exception as e:
        return False, str(e)


def pull_repo(repo_path: str, timeout: int = 300, check_first: bool = True) -> Tuple[bool, str, bool]:
    """
    Pull updates for an existing repository.
    Optionally checks for updates first to avoid unnecessary operations.
    
    Args:
        repo_path: Local path to the repository
        timeout: Timeout in seconds (default 300 = 5 minutes)
        check_first: Check for updates before pulling (default True)
        
    Returns:
        Tuple of (success: bool, error_message: str, has_updates: bool)
        has_updates indicates if new commits were pulled
    """
    # Check first if updates are available (more efficient)
    if check_first:
        has_updates, check_error = check_repo_has_updates(repo_path)
        if check_error:
            logging.warning(f"Update check failed for {repo_path}: {check_error}, proceeding with pull")
        elif not has_updates:
            logging.info(f"No updates available for {repo_path}")
            return True, "", False
    
    logging.info(f"Pulling updates for {repo_path}")
    try:
        pull_proc = subprocess.run(
            ["git", "-C", repo_path, "pull"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout
        )
        if pull_proc.returncode == 0:
            pull_out = pull_proc.stdout.lower()
            has_updates = "already up to date" not in pull_out and "up to date" not in pull_out
            return True, "", has_updates
        else:
            error_msg = pull_proc.stdout.strip()
            logging.error(f"Failed to pull {repo_path}: {error_msg}")
            return False, error_msg, False
    except subprocess.TimeoutExpired:
        error_msg = f"Pull timed out after {timeout} seconds"
        logging.error(f"Timeout pulling {repo_path}")
        return False, error_msg, False
    except Exception as e:
        error_msg = f"Pull exception: {str(e)}"
        logging.error(f"Exception during pull for {repo_path}: {error_msg}")
        return False, error_msg, False


###############################################################################
#                               REPOSITORY MANAGEMENT
###############################################################################

def clone_or_update_repo(repo_url: str) -> Tuple[bool, Optional[str]]:
    """
    Clone or update a repository, updating the JSON database.
    
    This is the main function that orchestrates:
    - Loading existing JSON record (or creating a new one)
    - Checking GitHub for description/archived/deleted status
    - Cloning or pulling as appropriate
    - Creating archives when updates are detected
    - Saving JSON updates
    
    Args:
        repo_url: GitHub repository URL
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    repos_data = load_cloned_info()
    repo_name = repo_url.rstrip("/").split("/")[-1]  # e.g. "some-repo.git"
    repo_path = os.path.join(DATA_FOLDER, repo_name)

    # Parse out owner/repo and get GitHub status
    parsed = parse_repo_url(repo_url)
    if parsed is None:
        error_msg = "Invalid repository URL format"
        logging.error(f"{error_msg}: {repo_url}")
        
        record = repos_data.get(repo_url, {
            "last_cloned": "",
            "last_updated": "",
            "local_path": repo_path,
            "online_description": error_msg,
            "status": "error",
        })
        repos_data[repo_url] = record
        save_cloned_info(repos_data)
        return False, error_msg
    
    owner, raw_repo = parsed
    desc, is_arch, is_del = get_online_repo_description(owner, raw_repo)
    
    # Determine status
    if is_del:
        status = "deleted"
    elif is_arch:
        status = "archived"
    else:
        status = "active"

    now = current_timestamp()
    record = repos_data.get(repo_url, {
        "last_cloned": "",
        "last_updated": "",
        "local_path": repo_path,
        "online_description": desc,
        "status": status,
    })

    record["online_description"] = desc
    record["status"] = status
    record["local_path"] = repo_path
    
    success = True
    error_msg = None

    if status != "deleted":
        # If local folder exists, do a pull
        if os.path.isdir(repo_path):
            # Use optimized pull with check-first
            pull_success, pull_error, has_updates = pull_repo(repo_path, check_first=True)
            
            if pull_success:
                record["last_cloned"] = now
                record["last_updated"] = now
                
                # Create archive if we got new commits (async to not block)
                if has_updates:
                    create_versioned_archive(repo_path, async_mode=True)
            else:
                record["status"] = "error"
                record["online_description"] = f"Pull error: {pull_error[:100]}"
                success = False
                error_msg = pull_error
        else:
            # Clone new repository (use shallow clone for speed)
            clone_success, clone_error = clone_repo(repo_url, repo_path, shallow=True)
            
            if clone_success:
                record["last_cloned"] = now
                record["last_updated"] = now
                # Create initial archive (async to not block)
                create_versioned_archive(repo_path, async_mode=True)
            else:
                record["status"] = "error"
                record["online_description"] = f"Clone error: {clone_error[:100]}"
                success = False
                error_msg = clone_error
    else:
        logging.warning(f"Skipping clone - GitHub indicates {repo_url} is deleted.")

    repos_data[repo_url] = record
    save_cloned_info(repos_data)
    
    if error_msg:
        return False, error_msg
    return True, None


def clear_github_api_cache():
    """Clear the GitHub API cache. Useful when forcing fresh API calls."""
    with _github_api_cache_lock:
        _github_api_cache.clear()


def detect_deleted_or_archived(use_cache: bool = True) -> int:
    """
    Re-check all repositories for archived/deleted status and update.
    Uses GraphQL batching for efficiency when checking multiple repos.
    
    Args:
        use_cache: Whether to use cached API responses (default True)
    
    Returns:
        Number of repositories that were updated
    """
    data = load_cloned_info()
    updated_count = 0
    
    # Collect all repos for batch processing
    repos_to_check = []
    repo_urls = []
    
    for repo_url, rec in data.items():
        parsed = parse_repo_url(repo_url)
        if parsed is None:
            continue
        owner, raw_repo = parsed
        repos_to_check.append((owner, raw_repo))
        repo_urls.append(repo_url)
    
    # Batch fetch using GraphQL
    if repos_to_check:
        batch_results = batch_get_repo_descriptions(repos_to_check, use_cache=use_cache)
        
        # Update statuses
        for repo_url, (owner, raw_repo) in zip(repo_urls, repos_to_check):
            cache_key = f"{owner}/{raw_repo}"
            desc, is_arch, is_del = batch_results.get(cache_key, ("", False, False))
            
            rec = data[repo_url]
            old_status = rec.get("status", "")
            
            if is_del:
                rec["status"] = "deleted"
            elif is_arch:
                rec["status"] = "archived"
            else:
                rec["status"] = "active"
            
            rec["online_description"] = desc
            
            if old_status != rec["status"]:
                updated_count += 1
    else:
        # Fallback to individual calls if batch fails
        for repo_url, rec in data.items():
            parsed = parse_repo_url(repo_url)
            if parsed is None:
                continue
                
            owner, raw_repo = parsed
            desc, is_arch, is_del = get_online_repo_description(owner, raw_repo, use_cache=use_cache)
            
            old_status = rec.get("status", "")
            
            if is_del:
                rec["status"] = "deleted"
            elif is_arch:
                rec["status"] = "archived"
            else:
                rec["status"] = "active"
            
            rec["online_description"] = desc
            
            if old_status != rec["status"]:
                updated_count += 1

    if updated_count > 0:
        save_cloned_info(data)
    
    return updated_count


def add_repo_to_database(repo_url: str) -> bool:
    """
    Add a repository to the database without cloning/updating it.
    
    Args:
        repo_url: GitHub repository URL
        
    Returns:
        True if added successfully, False if already exists or invalid
    """
    if not validate_repo_url(repo_url):
        return False
    
    # Ensure .git suffix
    if not repo_url.endswith(".git"):
        repo_url += ".git"
    
    repos_data = load_cloned_info()
    
    if repo_url in repos_data:
        return False  # Already exists
    
    repo_name = repo_url.rstrip("/").split("/")[-1]
    repo_path = os.path.join(DATA_FOLDER, repo_name)
    
    repos_data[repo_url] = {
        "last_cloned": "",
        "last_updated": "",
        "local_path": repo_path,
        "online_description": "",
        "status": "pending"
    }
    
    save_cloned_info(repos_data)
    return True


###############################################################################
#                               AUTO-UPDATE CONFIG
###############################################################################

def get_last_auto_update_time() -> Optional[str]:
    """
    Get the timestamp of the last auto-update from config file.
    
    Returns:
        Timestamp string or None if not found
    """
    # Ensure config directory exists
    config_dir = os.path.dirname(AUTO_UPDATE_CONFIG_PATH)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    
    if os.path.exists(AUTO_UPDATE_CONFIG_PATH):
        try:
            with open(AUTO_UPDATE_CONFIG_PATH, "r") as f:
                config = json.load(f)
                return config.get("last_auto_update")
        except Exception as e:
            logging.error(f"Error loading auto-update config: {e}")
    return None


def save_last_auto_update_time(timestamp: str):
    """
    Save the timestamp of the last auto-update to config file.
    
    Args:
        timestamp: Timestamp string to save
    """
    # Ensure config directory exists
    config_dir = os.path.dirname(AUTO_UPDATE_CONFIG_PATH)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    
    config = {"last_auto_update": timestamp}
    try:
        with open(AUTO_UPDATE_CONFIG_PATH, "w") as f:
            json.dump(config, f)
    except Exception as e:
        logging.error(f"Error saving auto-update config: {e}")


def should_run_auto_update() -> Tuple[bool, Optional[str]]:
    """
    Check if auto-update should run (24 hours since last update).
    
    Returns:
        Tuple of (should_run: bool, last_update_time: Optional[str])
    """
    last_update = get_last_auto_update_time()
    
    if last_update is None:
        return True, None
    
    try:
        last_time = datetime.datetime.strptime(last_update, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()
        time_diff = now - last_time
        
        # If it's been more than 24 hours, run update
        if time_diff.total_seconds() >= 86400:  # 24 hours in seconds
            return True, last_update
        return False, last_update
    except ValueError:
        # Invalid timestamp format, run update
        return True, last_update


def delete_repo_from_database(repo_url: str) -> bool:
    """
    Remove a repository from the database.
    
    Args:
        repo_url: GitHub repository URL to delete
        
    Returns:
        True if deleted successfully, False if not found
    """
    repos_data = load_cloned_info()
    
    if repo_url not in repos_data:
        return False
    
    del repos_data[repo_url]
    save_cloned_info(repos_data)
    return True


def delete_multiple_repos_from_database(repo_urls: list) -> Dict[str, bool]:
    """
    Remove multiple repositories from the database.
    
    Args:
        repo_urls: List of GitHub repository URLs to delete
        
    Returns:
        Dictionary mapping repo URLs to deletion success status
    """
    repos_data = load_cloned_info()
    results = {}
    
    for repo_url in repo_urls:
        if repo_url in repos_data:
            del repos_data[repo_url]
            results[repo_url] = True
        else:
            results[repo_url] = False
    
    if any(results.values()):  # If any were deleted, save the updated data
        save_cloned_info(repos_data)
    
    return results

