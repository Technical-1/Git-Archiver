"""
Tests for src/repo_manager.py
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from src import repo_manager


class TestCreateVersionedArchive:
    """Tests for create_versioned_archive function"""

    def test_creates_versions_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake repo directory
            repo_path = os.path.join(tmpdir, "test-repo.git")
            os.makedirs(repo_path)

            # Create a test file
            with open(os.path.join(repo_path, "README.md"), 'w') as f:
                f.write("Test content")

            result = repo_manager.create_versioned_archive(repo_path)

            # Check versions directory was created
            versions_path = os.path.join(repo_path, "versions")
            assert os.path.exists(versions_path)
            assert result is True

    def test_handles_empty_directory(self):
        # Should handle directory with no files gracefully
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "empty-repo.git")
            os.makedirs(repo_path)

            # Should not crash on empty directory
            result = repo_manager.create_versioned_archive(repo_path)
            # Returns True because it creates archive (even if empty)
            assert result is True


class TestCloneOrUpdateRepo:
    """Tests for clone_or_update_repo function"""

    @patch('src.repo_manager.create_versioned_archive')
    @patch('src.repo_manager.subprocess.run')
    @patch('src.repo_manager.get_online_repo_description')
    @patch('src.repo_manager.save_cloned_info')
    @patch('src.repo_manager.load_cloned_info')
    def test_calls_git_for_new_repo(self, mock_load, mock_save, mock_desc, mock_run, mock_archive):
        mock_load.return_value = {}
        mock_desc.return_value = ("Test repo", False, False)  # desc, is_archived, is_deleted
        mock_run.return_value = MagicMock(returncode=0)
        mock_archive.return_value = True

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(repo_manager, 'DATA_FOLDER', tmpdir):
                repo_manager.clone_or_update_repo("https://github.com/test/repo.git")

        # Should have called subprocess
        assert mock_run.called


class TestDetectDeletedOrArchived:
    """Tests for detect_deleted_or_archived function"""

    @patch('src.repo_manager.batch_get_repo_descriptions')
    @patch('src.repo_manager.save_cloned_info')
    @patch('src.repo_manager.load_cloned_info')
    def test_updates_deleted_status(self, mock_load, mock_save, mock_batch):
        # Setup mock data
        mock_load.return_value = {
            "https://github.com/test/repo.git": {
                "status": "active"
            }
        }
        # Return (description, is_archived, is_deleted)
        mock_batch.return_value = {"test/repo": ("", False, True)}

        count = repo_manager.detect_deleted_or_archived()

        assert count == 1
        # Verify save was called with updated status
        save_call_args = mock_save.call_args[0][0]
        assert save_call_args["https://github.com/test/repo.git"]["status"] == "deleted"

    @patch('src.repo_manager.batch_get_repo_descriptions')
    @patch('src.repo_manager.save_cloned_info')
    @patch('src.repo_manager.load_cloned_info')
    def test_updates_archived_status(self, mock_load, mock_save, mock_batch):
        mock_load.return_value = {
            "https://github.com/test/repo.git": {
                "status": "active"
            }
        }
        mock_batch.return_value = {"test/repo": ("A repo", True, False)}

        count = repo_manager.detect_deleted_or_archived()

        assert count == 1
        save_call_args = mock_save.call_args[0][0]
        assert save_call_args["https://github.com/test/repo.git"]["status"] == "archived"

    @patch('src.repo_manager.batch_get_repo_descriptions')
    @patch('src.repo_manager.save_cloned_info')
    @patch('src.repo_manager.load_cloned_info')
    def test_preserves_active_status(self, mock_load, mock_save, mock_batch):
        mock_load.return_value = {
            "https://github.com/test/repo.git": {
                "status": "active"
            }
        }
        mock_batch.return_value = {"test/repo": ("A repo", False, False)}

        count = repo_manager.detect_deleted_or_archived()

        # Status didn't change, so count should be 0
        assert count == 0
