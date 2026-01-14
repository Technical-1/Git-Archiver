"""
Tests for src/data_store.py
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch

from src import data_store


class TestLoadClonedInfo:
    """Tests for load_cloned_info function"""

    def test_returns_dict(self):
        with patch.object(data_store, 'CLONED_JSON_PATH', '/nonexistent/path.json'):
            result = data_store.load_cloned_info()
            assert isinstance(result, dict)

    def test_returns_empty_when_no_file(self):
        with patch.object(data_store, 'CLONED_JSON_PATH', '/nonexistent/path.json'):
            result = data_store.load_cloned_info()
            assert result == {}

    def test_loads_valid_json(self):
        test_data = {
            "https://github.com/user/repo.git": {
                "last_cloned": "2024-01-01 12:00:00",
                "status": "active"
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            with patch.object(data_store, 'CLONED_JSON_PATH', temp_path):
                result = data_store.load_cloned_info()
                assert "https://github.com/user/repo.git" in result
                assert result["https://github.com/user/repo.git"]["status"] == "active"
        finally:
            os.unlink(temp_path)


class TestSaveClonedInfo:
    """Tests for save_cloned_info function"""

    def test_saves_data(self):
        test_data = {
            "https://github.com/test/repo.git": {
                "last_cloned": "2024-01-01 12:00:00",
                "status": "active",
                "local_path": "data/repo.git",
                "online_description": "Test repo"
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = os.path.join(tmpdir, "cloned_repos.json")

            with patch.object(data_store, 'CLONED_JSON_PATH', temp_path):
                data_store.save_cloned_info(test_data)

                with open(temp_path, 'r') as f:
                    saved = json.load(f)
                    assert "https://github.com/test/repo.git" in saved

    def test_creates_backup(self):
        test_data = {"https://github.com/test/repo.git": {"status": "active"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = os.path.join(tmpdir, "cloned_repos.json")
            backup_path = temp_path + ".bak"

            # Create initial file
            with open(temp_path, 'w') as f:
                json.dump({"old": "data"}, f)

            with patch.object(data_store, 'CLONED_JSON_PATH', temp_path):
                data_store.save_cloned_info(test_data)

                # Check backup was created
                assert os.path.exists(backup_path)


class TestGetRepoCountByStatus:
    """Tests for get_repo_count_by_status function"""

    def test_counts_statuses(self):
        test_data = {
            "https://github.com/a/1.git": {"status": "active"},
            "https://github.com/a/2.git": {"status": "active"},
            "https://github.com/a/3.git": {"status": "pending"},
            "https://github.com/a/4.git": {"status": "deleted"},
        }

        result = data_store.get_repo_count_by_status(test_data)
        assert result["active"] == 2
        assert result["pending"] == 1
        assert result["deleted"] == 1

    def test_empty_data_returns_zeroes(self):
        result = data_store.get_repo_count_by_status({})
        # Returns dict with all status keys, all zero
        assert result["active"] == 0
        assert result["pending"] == 0
        assert result["deleted"] == 0


class TestSanitizeRepoData:
    """Tests for _sanitize_repo_data function"""

    def test_adds_missing_fields(self):
        # _sanitize_repo_data takes the full dict with URL keys
        data = {
            "https://github.com/test/repo.git": {}
        }
        result = data_store._sanitize_repo_data(data)
        repo_info = result["https://github.com/test/repo.git"]

        assert "last_cloned" in repo_info
        assert "last_updated" in repo_info
        assert "local_path" in repo_info
        assert "online_description" in repo_info
        assert "status" in repo_info

    def test_preserves_existing_fields(self):
        data = {
            "https://github.com/test/repo.git": {
                "last_cloned": "2024-01-01 12:00:00",
                "status": "active"
            }
        }
        result = data_store._sanitize_repo_data(data)
        repo_info = result["https://github.com/test/repo.git"]

        assert repo_info["last_cloned"] == "2024-01-01 12:00:00"
        assert repo_info["status"] == "active"
