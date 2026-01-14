"""
GitHub API interactions.
Handles fetching repository information and rate limiting.
"""

import time
import logging
import requests

from .config import GITHUB_API_BASE, GITHUB_RATE_LIMIT_PAUSE, get_github_token


def get_api_headers() -> dict:
    """Get headers for GitHub API requests, including auth token if available"""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-Repo-Saver/2.0"
    }

    token = get_github_token()
    if token:
        headers["Authorization"] = f"token {token}"

    return headers


def get_repo_description(owner: str, repo_name: str) -> tuple:
    """
    Fetch a GitHub repository's description and status.
    Handles API rate limiting by waiting when necessary.

    Args:
        owner: Repository owner username
        repo_name: Repository name

    Returns:
        tuple: (description, is_archived, is_deleted)
    """
    api_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}"
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Wait between API calls to avoid rate limiting
            token = get_github_token()
            wait_time = 0.5 if token else 1.0
            time.sleep(wait_time)

            headers = get_api_headers()
            resp = requests.get(api_url, headers=headers, timeout=15)

            # Check rate limits
            if 'X-RateLimit-Remaining' in resp.headers:
                remaining = int(resp.headers['X-RateLimit-Remaining'])
                if remaining < 10:
                    logging.warning(f"GitHub API rate limit low ({remaining} remaining). Slowing down.")
                    time.sleep(5)
                elif remaining < 50:
                    time.sleep(2)

            if resp.status_code == 200:
                data = resp.json()
                desc = data.get("description", "") or ""
                archived = data.get("archived", False)
                return desc, archived, False

            elif resp.status_code == 404:
                return "", False, True  # Repo doesn't exist or is private/deleted

            elif resp.status_code in (403, 429):
                # Handle rate limiting
                reset_time = int(resp.headers.get('X-RateLimit-Reset', 0))
                current_time = int(time.time())
                wait_time = max(30, min(reset_time - current_time, GITHUB_RATE_LIMIT_PAUSE))

                logging.warning(f"GitHub API rate limited (status {resp.status_code}). Pausing for {wait_time} seconds")
                time.sleep(wait_time)

                retry_count += 1
                continue

            else:
                logging.warning(f"Unexpected status code {resp.status_code} fetching {owner}/{repo_name}")
                if retry_count < max_retries - 1:
                    retry_count += 1
                    time.sleep(5)
                    continue
                return "", False, False

        except requests.RequestException as e:
            logging.warning(f"Failed to fetch {owner}/{repo_name}: {e}")
            if retry_count < max_retries - 1:
                retry_count += 1
                time.sleep(5)
                continue
            return "", False, False

    return "[API Error]", False, False


def get_rate_limit_status(token: str = None) -> dict:
    """
    Check current GitHub API rate limit status.

    Args:
        token: Optional token to check (uses saved token if not provided)

    Returns:
        dict with 'remaining', 'limit', and 'reset' keys, or None on error
    """
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Repo-Saver/2.0"
        }

        if token is None:
            token = get_github_token()

        if token:
            headers["Authorization"] = f"token {token}"

        resp = requests.get(
            f"{GITHUB_API_BASE}/rate_limit",
            headers=headers,
            timeout=10
        )

        if resp.status_code == 200:
            data = resp.json()
            core = data.get("resources", {}).get("core", {})
            return {
                "remaining": core.get("remaining", 0),
                "limit": core.get("limit", 60),
                "reset": core.get("reset", 0)
            }

    except Exception as e:
        logging.warning(f"Failed to check rate limit: {e}")

    return None
