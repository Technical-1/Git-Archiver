"""
Tests for src/github_api.py
"""

import pytest
from unittest.mock import patch, MagicMock

from src import github_api


class TestGetApiHeaders:
    """Tests for get_api_headers function"""

    def test_returns_dict(self):
        with patch.object(github_api, 'get_github_token', return_value=""):
            result = github_api.get_api_headers()
            assert isinstance(result, dict)

    def test_has_accept_header(self):
        with patch.object(github_api, 'get_github_token', return_value=""):
            result = github_api.get_api_headers()
            assert "Accept" in result
            assert "application/vnd.github.v3+json" in result["Accept"]

    def test_has_user_agent(self):
        with patch.object(github_api, 'get_github_token', return_value=""):
            result = github_api.get_api_headers()
            assert "User-Agent" in result

    def test_includes_token_when_configured(self):
        with patch.object(github_api, 'get_github_token', return_value="test_token"):
            result = github_api.get_api_headers()
            assert "Authorization" in result
            assert "token test_token" in result["Authorization"]

    def test_no_auth_when_no_token(self):
        with patch.object(github_api, 'get_github_token', return_value=""):
            result = github_api.get_api_headers()
            assert "Authorization" not in result


class TestGetRepoDescription:
    """Tests for get_repo_description function"""

    @patch('src.github_api.requests.get')
    @patch('src.github_api.get_github_token', return_value="")
    @patch('src.github_api.time.sleep')  # Skip sleep in tests
    def test_returns_description_on_success(self, mock_sleep, mock_token, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-RateLimit-Remaining": "1000"}
        mock_response.json.return_value = {
            "description": "A test repository",
            "archived": False
        }
        mock_get.return_value = mock_response

        desc, is_archived, is_deleted = github_api.get_repo_description("user", "repo")
        assert desc == "A test repository"
        assert is_archived is False
        assert is_deleted is False

    @patch('src.github_api.requests.get')
    @patch('src.github_api.get_github_token', return_value="")
    @patch('src.github_api.time.sleep')
    def test_returns_archived_status(self, mock_sleep, mock_token, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"X-RateLimit-Remaining": "1000"}
        mock_response.json.return_value = {
            "description": "An archived repo",
            "archived": True
        }
        mock_get.return_value = mock_response

        desc, is_archived, is_deleted = github_api.get_repo_description("user", "repo")
        assert is_archived is True
        assert is_deleted is False

    @patch('src.github_api.requests.get')
    @patch('src.github_api.get_github_token', return_value="")
    @patch('src.github_api.time.sleep')
    def test_returns_deleted_on_404(self, mock_sleep, mock_token, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_get.return_value = mock_response

        desc, is_archived, is_deleted = github_api.get_repo_description("user", "repo")
        assert is_deleted is True


class TestGetRateLimitStatus:
    """Tests for get_rate_limit_status function"""

    @patch('src.github_api.requests.get')
    @patch('src.github_api.get_github_token', return_value="")
    def test_returns_rate_limit_info(self, mock_token, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resources": {
                "core": {
                    "limit": 5000,
                    "remaining": 4999,
                    "reset": 1234567890
                }
            }
        }
        mock_get.return_value = mock_response

        result = github_api.get_rate_limit_status()
        assert result is not None
        assert result["limit"] == 5000
        assert result["remaining"] == 4999

    @patch('src.github_api.requests.get')
    @patch('src.github_api.get_github_token', return_value="")
    def test_returns_none_on_error(self, mock_token, mock_get):
        mock_get.side_effect = Exception("Network error")

        result = github_api.get_rate_limit_status()
        assert result is None
