"""
Tests for src/utils.py
"""

import pytest
from src.utils import validate_repo_url, normalize_repo_url, extract_owner_repo, current_timestamp


class TestValidateRepoUrl:
    """Tests for URL validation"""

    def test_valid_https_url(self):
        assert validate_repo_url("https://github.com/user/repo") is True

    def test_valid_https_url_with_git(self):
        assert validate_repo_url("https://github.com/user/repo.git") is True

    def test_valid_https_url_with_trailing_slash(self):
        assert validate_repo_url("https://github.com/user/repo/") is True

    def test_valid_http_url(self):
        assert validate_repo_url("http://github.com/user/repo") is True

    def test_invalid_empty_string(self):
        assert validate_repo_url("") is False

    def test_invalid_none(self):
        assert validate_repo_url(None) is False

    def test_invalid_non_github(self):
        assert validate_repo_url("https://gitlab.com/user/repo") is False

    def test_invalid_missing_repo(self):
        assert validate_repo_url("https://github.com/user") is False

    def test_invalid_comment_line(self):
        assert validate_repo_url("# comment") is False

    def test_repo_with_dash(self):
        assert validate_repo_url("https://github.com/user/my-repo") is True

    def test_repo_with_underscore(self):
        assert validate_repo_url("https://github.com/user/my_repo") is True

    def test_repo_with_dot(self):
        assert validate_repo_url("https://github.com/user/my.repo") is True


class TestNormalizeRepoUrl:
    """Tests for URL normalization"""

    def test_adds_git_suffix(self):
        assert normalize_repo_url("https://github.com/user/repo") == "https://github.com/user/repo.git"

    def test_keeps_existing_git_suffix(self):
        assert normalize_repo_url("https://github.com/user/repo.git") == "https://github.com/user/repo.git"

    def test_strips_whitespace(self):
        assert normalize_repo_url("  https://github.com/user/repo  ") == "https://github.com/user/repo.git"

    def test_removes_trailing_slash(self):
        assert normalize_repo_url("https://github.com/user/repo/") == "https://github.com/user/repo.git"


class TestExtractOwnerRepo:
    """Tests for extracting owner/repo from URL"""

    def test_basic_url(self):
        owner, repo = extract_owner_repo("https://github.com/octocat/Hello-World")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_with_git_suffix(self):
        owner, repo = extract_owner_repo("https://github.com/octocat/Hello-World.git")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_with_trailing_slash(self):
        owner, repo = extract_owner_repo("https://github.com/octocat/Hello-World/")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_invalid_url_returns_none_tuple(self):
        owner, repo = extract_owner_repo("not-a-url")
        assert owner is None
        assert repo is None

    def test_short_url_returns_none_tuple(self):
        owner, repo = extract_owner_repo("https://github.com/user")
        assert owner is None
        assert repo is None


class TestCurrentTimestamp:
    """Tests for timestamp generation"""

    def test_returns_string(self):
        ts = current_timestamp()
        assert isinstance(ts, str)

    def test_timestamp_format(self):
        ts = current_timestamp()
        # Should be in format YYYY-MM-DD HH:MM:SS
        assert len(ts) == 19
        assert ts[4] == "-"
        assert ts[7] == "-"
        assert ts[10] == " "
        assert ts[13] == ":"
        assert ts[16] == ":"
