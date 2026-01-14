"""
Data store for repository tracking information.
Handles loading, saving, and recovery of cloned_repos.json.
"""

import os
import re
import json
import shutil
import logging

from .config import CLONED_JSON_PATH, DATA_FOLDER


def load_cloned_info() -> dict:
    """
    Load repository info from the JSON file with robust error handling.

    The JSON structure looks like:
    {
      "https://github.com/user/repo.git": {
        "last_cloned": "YYYY-MM-DD HH:MM:SS",
        "last_updated": "YYYY-MM-DD HH:MM:SS",
        "local_path": "data/repo.git",
        "online_description": "Repo description from GitHub",
        "status": "active"/"archived"/"deleted"/"error"/"pending",
        "last_error": "Error message if any"
      },
      ...
    }
    """
    if not os.path.isfile(CLONED_JSON_PATH):
        return {}

    try:
        with open(CLONED_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except json.JSONDecodeError as e:
        logging.error(f"JSON file is corrupted: {e}. Attempting recovery.")
        return recover_json_data()
    except OSError as e:
        logging.error(f"Failed to open JSON file: {e}")
        return {}


def recover_json_data() -> dict:
    """
    Recover data from a corrupted JSON file by:
    1. Trying to parse as many valid repository entries as possible
    2. Creating a backup of the corrupted file
    3. Returning a clean dictionary with the recovered data
    """
    backup_path = f"{CLONED_JSON_PATH}.corrupted.bak"
    try:
        # Create a backup of the corrupted file
        shutil.copy2(CLONED_JSON_PATH, backup_path)
        logging.info(f"Created backup of corrupted JSON at {backup_path}")

        # Try to extract valid entries using regex
        with open(CLONED_JSON_PATH, 'r', encoding='utf-8') as file:
            content = file.read()

        # Pattern to match repository entries
        pattern = r'"(https://github\.com/[^"]+\.git)"\s*:\s*{([^{}]|{[^{}]*})*?}'
        matches = re.findall(pattern, content)

        if not matches:
            logging.error("No valid repository entries found in corrupted file")
            return {}

        # Process each match
        recovered_data = {}
        for match in matches:
            try:
                repo_url = match[0]
                entry_content = "{" + match[1] + "}"
                try:
                    repo_data = json.loads(entry_content)
                    recovered_data[repo_url] = repo_data
                except json.JSONDecodeError:
                    logging.warning(f"Creating basic entry for: {repo_url}")
                    recovered_data[repo_url] = {
                        "last_cloned": "",
                        "last_updated": "",
                        "local_path": f"data/{repo_url.split('/')[-1]}",
                        "online_description": "",
                        "status": "pending"
                    }
            except Exception as e:
                logging.error(f"Error recovering {repo_url}: {e}")

        # Save the recovered data
        if recovered_data:
            with open(CLONED_JSON_PATH, 'w', encoding='utf-8') as file:
                json.dump(recovered_data, file, indent=2, ensure_ascii=False)
            logging.info(f"Successfully recovered {len(recovered_data)} repositories")

        return recovered_data

    except Exception as e:
        logging.error(f"Recovery failed: {e}")
        return {}


def save_cloned_info(data: dict):
    """
    Save repository data to the JSON file safely.
    Creates a clean JSON file with validation and backup.
    """
    if not data:
        logging.warning("Attempted to save empty data, aborting save operation")
        return

    backup_path = f"{CLONED_JSON_PATH}.bak"

    try:
        # Create directory if needed
        os.makedirs(os.path.dirname(CLONED_JSON_PATH) if os.path.dirname(CLONED_JSON_PATH) else ".", exist_ok=True)

        # Sanitize and clean the data
        clean_data = _sanitize_repo_data(data)

        # Create a temporary file for safe writing
        temp_path = f"{CLONED_JSON_PATH}.tmp"

        # First make a backup of the existing file
        if os.path.exists(CLONED_JSON_PATH):
            try:
                shutil.copy2(CLONED_JSON_PATH, backup_path)
                logging.info(f"Created backup at {backup_path}")
            except Exception as e:
                logging.warning(f"Failed to create backup: {e}")

        # Write to a temporary file first
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(clean_data, f, indent=2, ensure_ascii=False)

            # Verify the JSON is valid by reading it back
            with open(temp_path, "r", encoding="utf-8") as f:
                json.load(f)

            # Replace the original file with our new one
            shutil.move(temp_path, CLONED_JSON_PATH)
            logging.info(f"Successfully saved {len(clean_data)} repositories to {CLONED_JSON_PATH}")

        except Exception as e:
            logging.error(f"Error writing JSON file: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise

    except Exception as e:
        logging.error(f"Critical error saving repository data: {e}")
        # Try to recover from backup
        if os.path.exists(backup_path):
            try:
                logging.warning("Attempting to recover from backup")
                shutil.copy2(backup_path, CLONED_JSON_PATH)
                logging.info("Restored from backup")
            except Exception as restore_error:
                logging.error(f"Failed to restore from backup: {restore_error}")


def _sanitize_repo_data(data: dict) -> dict:
    """Sanitize and validate repository data before saving"""
    clean_data = {}

    for repo_url, repo_info in data.items():
        # Skip any non-string URLs
        if not isinstance(repo_url, str):
            logging.warning(f"Skipping non-string URL: {repo_url}")
            continue

        clean_info = {}

        # Process expected fields with proper types
        if "last_cloned" in repo_info and isinstance(repo_info["last_cloned"], str):
            clean_info["last_cloned"] = repo_info["last_cloned"]
        else:
            clean_info["last_cloned"] = ""

        if "last_updated" in repo_info and isinstance(repo_info["last_updated"], str):
            clean_info["last_updated"] = repo_info["last_updated"]
        else:
            clean_info["last_updated"] = ""

        if "local_path" in repo_info and isinstance(repo_info["local_path"], str):
            clean_info["local_path"] = repo_info["local_path"]
        else:
            repo_name = repo_url.split("/")[-1]
            clean_info["local_path"] = os.path.join(DATA_FOLDER, repo_name)

        if "online_description" in repo_info and isinstance(repo_info["online_description"], str):
            desc = repo_info["online_description"].replace("\n", " ").replace("\r", " ")
            if len(desc) > 500:
                desc = desc[:497] + "..."
            clean_info["online_description"] = desc
        else:
            clean_info["online_description"] = ""

        if "status" in repo_info and isinstance(repo_info["status"], str):
            status = repo_info["status"]
            if status not in ["active", "archived", "deleted", "error", "pending"]:
                status = "pending"
            clean_info["status"] = status
        else:
            clean_info["status"] = "pending"

        # Preserve last_error field if present
        if "last_error" in repo_info and isinstance(repo_info["last_error"], str):
            clean_info["last_error"] = repo_info["last_error"][:200]

        clean_data[repo_url] = clean_info

    return clean_data


def get_repo_count_by_status(data: dict = None) -> dict:
    """Get count of repositories by status"""
    if data is None:
        data = load_cloned_info()

    counts = {"active": 0, "pending": 0, "archived": 0, "deleted": 0, "error": 0, "other": 0}
    for info in data.values():
        status = info.get("status", "")
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
    return counts
