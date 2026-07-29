"""Tests for core/updater.py — version checking against GitHub releases."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from core import updater


class TestGetLatestVersion:
    def test_returns_version_string_on_success(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps({"tag_name": "v32.1.0"}).encode()

        with patch("core.updater.urllib.request.urlopen", return_value=mock_resp):
            result = updater.get_latest_version()
        assert result == "32.1.0"

    def test_strips_v_prefix(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps({"tag_name": "v31.0.0"}).encode()

        with patch("core.updater.urllib.request.urlopen", return_value=mock_resp):
            result = updater.get_latest_version()
        assert result == "31.0.0"
        assert not result.startswith("v")

    def test_returns_none_when_no_tag(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps({"tag_name": ""}).encode()

        with patch("core.updater.urllib.request.urlopen", return_value=mock_resp):
            result = updater.get_latest_version()
        assert result is None

    def test_returns_none_on_http_error(self):
        from urllib.error import HTTPError

        with patch(
            "core.updater.urllib.request.urlopen",
            side_effect=HTTPError("url", 404, "Not Found", None, None),
        ):
            result = updater.get_latest_version()
        assert result is None

    def test_returns_none_on_connection_error(self):
        with patch("core.updater.urllib.request.urlopen", side_effect=ConnectionError):
            result = updater.get_latest_version()
        assert result is None

    def test_returns_none_on_timeout(self):
        with patch("core.updater.urllib.request.urlopen", side_effect=TimeoutError):
            result = updater.get_latest_version()
        assert result is None


class TestIsUpdateAvailable:
    def test_update_available(self, monkeypatch):
        monkeypatch.setattr(updater, "get_latest_version", lambda: "32.0.0")
        is_available, latest = updater.is_update_available()
        assert is_available is True
        assert latest == "32.0.0"

    def test_no_update_same_version(self, monkeypatch):
        monkeypatch.setattr(updater, "get_latest_version", lambda: "31.0.0")
        is_available, latest = updater.is_update_available()
        assert is_available is False

    def test_no_update_when_fetch_fails(self, monkeypatch):
        monkeypatch.setattr(updater, "get_latest_version", lambda: None)
        is_available, latest = updater.is_update_available()
        assert is_available is False
        assert latest is None

    def test_patch_version_comparison(self, monkeypatch):
        """31.0.1 > 31.0.0 should be detected as newer."""
        monkeypatch.setattr(updater, "get_latest_version", lambda: "31.0.1")
        is_available, latest = updater.is_update_available()
        assert is_available is True

    def test_old_version_not_flagged(self, monkeypatch):
        """A version older than current should not be flagged."""
        monkeypatch.setattr(updater, "get_latest_version", lambda: "30.0.0")
        is_available, latest = updater.is_update_available()
        assert is_available is False

    def test_various_version_comparisons(self, monkeypatch):
        """Test several version pairs to confirm semantic comparison works."""
        cases = [
            ("31.0.1", True),
            ("31.1.0", True),
            ("32.0.0", True),
            ("30.9.9", False),
            ("31.0.0", False),
        ]
        for version, expected in cases:
            monkeypatch.setattr(updater, "get_latest_version", lambda v=version: v)
            is_available, latest = updater.is_update_available()
            assert is_available == expected, f"version {version}: expected {expected}, got {is_available}"


class TestGithubApiConstant:
    def test_github_api_url(self):
        assert "github.com" in updater.GITHUB_API
        assert "sentinel-desktop" in updater.GITHUB_API

    def test_module_version_import(self):
        """The updater imports __version__ from core — make sure it resolves."""
        from core import __version__

        assert isinstance(__version__, str)
        assert "." in __version__
