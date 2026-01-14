"""
Configuration constants and settings management.
"""

import os
import json
import logging

# File paths
CLONED_JSON_PATH = "cloned_repos.json"
DATA_FOLDER = "data"
SETTINGS_FILE = "settings.json"
AUTO_UPDATE_CONFIG = "auto_update_config.json"

# GitHub API settings
GITHUB_RATE_LIMIT_PAUSE = 60  # seconds
GITHUB_API_BASE = "https://api.github.com"

# Default settings
DEFAULT_SETTINGS = {
    "github_token": "",
    "window_width": 1200,
    "window_height": 600,
    "auto_update_enabled": True
}


def load_settings() -> dict:
    """Load application settings from settings.json"""
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
            # Merge with defaults for any missing keys
            for key, value in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
    except Exception as e:
        logging.warning(f"Could not load settings: {e}")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict):
    """Save application settings to settings.json"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logging.error(f"Could not save settings: {e}")


def get_github_token() -> str:
    """Get the GitHub token from settings"""
    settings = load_settings()
    return settings.get("github_token", "")


def get_last_auto_update_time() -> str:
    """Load the timestamp of the last automatic update"""
    if os.path.exists(AUTO_UPDATE_CONFIG):
        try:
            with open(AUTO_UPDATE_CONFIG, "r") as f:
                config = json.load(f)
                return config.get("last_auto_update")
        except Exception as e:
            logging.error(f"Error loading auto-update config: {e}")
    return None


def save_last_auto_update_time(timestamp: str):
    """Save the timestamp of when we last ran an automatic update"""
    config = {"last_auto_update": timestamp}
    try:
        with open(AUTO_UPDATE_CONFIG, "w") as f:
            json.dump(config, f)
    except Exception as e:
        logging.error(f"Error saving auto-update config: {e}")
