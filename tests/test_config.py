"""
Tests for src/config.py
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch

from src import config


class TestConstants:
    """Test that constants are defined"""

    def test_cloned_json_path_defined(self):
        assert hasattr(config, 'CLONED_JSON_PATH')
        assert isinstance(config.CLONED_JSON_PATH, str)

    def test_data_folder_defined(self):
        assert hasattr(config, 'DATA_FOLDER')
        assert isinstance(config.DATA_FOLDER, str)

    def test_settings_file_defined(self):
        assert hasattr(config, 'SETTINGS_FILE')
        assert isinstance(config.SETTINGS_FILE, str)

    def test_rate_limit_pause_defined(self):
        assert hasattr(config, 'GITHUB_RATE_LIMIT_PAUSE')
        assert isinstance(config.GITHUB_RATE_LIMIT_PAUSE, int)
        assert config.GITHUB_RATE_LIMIT_PAUSE > 0


class TestLoadSettings:
    """Tests for load_settings function"""

    def test_returns_dict(self):
        result = config.load_settings()
        assert isinstance(result, dict)

    def test_has_default_keys(self):
        result = config.load_settings()
        assert "github_token" in result
        assert "window_width" in result
        assert "window_height" in result
        assert "auto_update_enabled" in result

    def test_loads_from_file(self):
        # Create a temp settings file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"github_token": "test_token_123"}, f)
            temp_path = f.name

        try:
            with patch.object(config, 'SETTINGS_FILE', temp_path):
                result = config.load_settings()
                assert result["github_token"] == "test_token_123"
        finally:
            os.unlink(temp_path)


class TestSaveSettings:
    """Tests for save_settings function"""

    def test_saves_to_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            with patch.object(config, 'SETTINGS_FILE', temp_path):
                config.save_settings({"github_token": "saved_token"})

                with open(temp_path, 'r') as f:
                    saved = json.load(f)
                    assert saved["github_token"] == "saved_token"
        finally:
            os.unlink(temp_path)


class TestGetGithubToken:
    """Tests for get_github_token function"""

    def test_returns_string(self):
        result = config.get_github_token()
        assert isinstance(result, str)

    def test_returns_empty_when_not_set(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            temp_path = f.name

        try:
            with patch.object(config, 'SETTINGS_FILE', temp_path):
                result = config.get_github_token()
                assert result == ""
        finally:
            os.unlink(temp_path)
