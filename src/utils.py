"""
Utility functions for logging, validation, and timestamps.
"""

import logging
import datetime
import socket


def setup_logging():
    """Configure logging with a readable format and timestamp"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def current_timestamp() -> str:
    """Get a formatted string of the current date and time"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def validate_repo_url(url: str) -> bool:
    """
    Check if a URL looks like a valid GitHub repository.

    Handles various GitHub URL formats:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/
    - https://github.com/owner/repo.git
    """
    if not url or not isinstance(url, str):
        return False

    # Clean up the URL
    url = url.strip()

    # Skip comment lines
    if url.startswith('#'):
        return False

    # Must start with github.com
    if not url.startswith("https://github.com/") and not url.startswith("http://github.com/"):
        return False

    # Remove protocol and github.com part
    path = url.split("github.com/", 1)[-1]

    # Remove trailing slashes
    path = path.rstrip("/")

    # Remove .git extension if present
    if path.endswith(".git"):
        path = path[:-4]

    # Split the path into parts
    parts = path.split("/")

    # Need at least owner/repo
    if len(parts) < 2:
        return False

    # Extract owner and repo
    owner, repo = parts[0], parts[1]

    # Check for empty components
    if not owner or not repo:
        return False

    # Check repo name has only valid characters (alphanumeric plus dash, underscore, dot)
    if not all(c.isalnum() or c in "-_." for c in repo):
        return False

    return True


def normalize_repo_url(url: str) -> str:
    """Normalize a GitHub URL to standard format with .git suffix"""
    url = url.strip().rstrip("/")
    if not url.endswith(".git"):
        url += ".git"
    return url


def extract_owner_repo(url: str) -> tuple:
    """Extract owner and repo name from a GitHub URL"""
    parts = url.replace("https://github.com/", "").replace("http://github.com/", "").split("/")
    if len(parts) >= 2:
        owner = parts[0]
        repo = parts[1].replace(".git", "")
        return owner, repo
    return None, None


def is_internet_connected(host="8.8.8.8", port=53, timeout=3) -> bool:
    """
    Check if internet connection is available.
    Uses Google's DNS server by default.
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False
