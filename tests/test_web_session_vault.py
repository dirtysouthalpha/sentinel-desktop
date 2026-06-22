"""Tests for core.web.session_vault — encrypted cookie persistence."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.web.session_vault import SessionVault


@pytest.fixture
def vault(tmp_path: Path) -> SessionVault:
    """SessionVault pointing at a temp directory."""
    return SessionVault(path=tmp_path / "sessions.json")


class TestSaveAndLoad:
    def test_save_and_load_session(self, vault: SessionVault):
        cookies = [{"name": "session", "value": "abc123", "domain": "192.168.1.1"}]
        assert vault.save_session("192.168.1.1", cookies) is True

        loaded = vault.load_session("192.168.1.1")
        assert loaded is not None
        assert loaded["cookies"] == cookies
        assert "saved_at" in loaded

    def test_save_with_local_storage(self, vault: SessionVault):
        cookies = [{"name": "token", "value": "xyz"}]
        ls = {"theme": "dark", "lang": "en"}
        vault.save_session("app.local", cookies, local_storage=ls)

        loaded = vault.load_session("app.local")
        assert loaded["local_storage"] == ls

    def test_save_without_local_storage(self, vault: SessionVault):
        vault.save_session("x.com", [{"name": "a", "value": "b"}])
        loaded = vault.load_session("x.com")
        assert loaded["local_storage"] == {}

    def test_load_nonexistent_returns_none(self, vault: SessionVault):
        assert vault.load_session("nope.com") is None

    def test_overwrite_existing_session(self, vault: SessionVault):
        vault.save_session("x.com", [{"name": "old", "value": "1"}])
        vault.save_session("x.com", [{"name": "new", "value": "2"}])
        cookies = vault.get_cookies("x.com")
        assert len(cookies) == 1
        assert cookies[0]["name"] == "new"


class TestGetCookies:
    def test_returns_cookies_for_domain(self, vault: SessionVault):
        cookies = [{"name": "sid", "value": "123"}]
        vault.save_session("fw.local", cookies)
        assert vault.get_cookies("fw.local") == cookies

    def test_returns_empty_for_unknown(self, vault: SessionVault):
        assert vault.get_cookies("unknown.com") == []


class TestListDomains:
    def test_empty_vault(self, vault: SessionVault):
        assert vault.list_domains() == []

    def test_lists_saved_domains_sorted(self, vault: SessionVault):
        vault.save_session("z.local", [])
        vault.save_session("a.local", [])
        vault.save_session("m.local", [])
        assert vault.list_domains() == ["a.local", "m.local", "z.local"]


class TestDeleteSession:
    def test_delete_existing(self, vault: SessionVault):
        vault.save_session("x.com", [])
        assert vault.delete_session("x.com") is True
        assert vault.load_session("x.com") is None

    def test_delete_nonexistent(self, vault: SessionVault):
        assert vault.delete_session("nope.com") is False


class TestRestoreToBrowser:
    def test_restore_cookies_to_browser(self, vault: SessionVault):
        cookies = [{"name": "sid", "value": "abc", "domain": "fw.local"}]
        vault.save_session("fw.local", cookies)

        mock_browser = MagicMock()
        result = vault.restore_to_browser("fw.local", mock_browser)
        assert result is True
        mock_browser.set_cookies.assert_called_once_with(cookies)

    def test_restore_no_session_returns_false(self, vault: SessionVault):
        mock_browser = MagicMock()
        result = vault.restore_to_browser("nope.com", mock_browser)
        assert result is False
        mock_browser.set_cookies.assert_not_called()

    def test_restore_browser_error_returns_false(self, vault: SessionVault):
        vault.save_session("fw.local", [{"name": "a", "value": "b"}])
        mock_browser = MagicMock()
        mock_browser.set_cookies.side_effect = Exception("No context")
        result = vault.restore_to_browser("fw.local", mock_browser)
        assert result is False


class TestSaveFromBrowser:
    def test_save_from_browser_manager(self, vault: SessionVault):
        cookies = [{"name": "sid", "value": "xyz"}]
        mock_browser = MagicMock()
        mock_browser.get_cookies.return_value = cookies

        result = vault.save_from_browser("fw.local", mock_browser)
        assert result is True
        mock_browser.get_cookies.assert_called_once()

        loaded = vault.get_cookies("fw.local")
        assert loaded == cookies

    def test_save_from_browser_error(self, vault: SessionVault):
        mock_browser = MagicMock()
        mock_browser.get_cookies.side_effect = Exception("Browser closed")
        result = vault.save_from_browser("fw.local", mock_browser)
        assert result is False


class TestPersistence:
    def test_data_survives_reload(self, tmp_path: Path):
        path = tmp_path / "sessions.json"
        cookies = [{"name": "sid", "value": "persist"}]

        vault1 = SessionVault(path=path)
        vault1.save_session("fw.local", cookies)

        vault2 = SessionVault(path=path)
        loaded = vault2.get_cookies("fw.local")
        assert loaded == cookies

    def test_handles_corrupt_file(self, tmp_path: Path):
        path = tmp_path / "sessions.json"
        path.write_text("not valid json{{{")

        vault = SessionVault(path=path)
        assert vault.list_domains() == []
        assert vault.load_session("any.com") is None

    def test_creates_directory_on_save(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "sessions.json"
        vault = SessionVault(path=path)
        vault.save_session("x.com", [])
        assert path.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
    def test_session_file_is_owner_only_after_save(self, tmp_path: Path):
        # Session cookies authenticate to routers/firewalls/APs — the file
        # must not be readable by other local users.
        path = tmp_path / "sessions.json"
        vault = SessionVault(path=path)
        vault.save_session("192.168.1.1", [{"name": "sess", "value": "secret"}])
        mode = stat.S_IMODE(path.stat().st_mode)
        assert (mode & 0o077) == 0, f"sessions.json group/other bits: {oct(mode)}"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
    def test_existing_world_readable_session_file_is_tightened_on_load(
        self, tmp_path: Path
    ):
        path = tmp_path / "sessions.json"
        path.write_text("{}", encoding="utf-8")
        os.chmod(path, 0o644)
        SessionVault(path=path)  # opening it should heal perms
        mode = stat.S_IMODE(path.stat().st_mode)
        assert (mode & 0o077) == 0, f"sessions.json not healed: {oct(mode)}"


class TestAtRestEncryption:
    """CLAUDE.md v8.0 advertises encrypted cookie persistence; the file must
    not contain plaintext cookie values."""

    def test_saved_session_file_has_no_plaintext_cookie_value(self, tmp_path: Path):
        path = tmp_path / "sessions.json"
        vault = SessionVault(path=path)
        vault.save_session("192.168.1.1", [{"name": "session", "value": "SUPERSECRET-TOKEN"}])
        raw = path.read_text(encoding="utf-8")
        assert "SUPERSECRET-TOKEN" not in raw

    def test_roundtrip_across_instances(self, tmp_path: Path):
        path = tmp_path / "sessions.json"
        SessionVault(path=path).save_session(
            "fw.local", [{"name": "sid", "value": "abc"}]
        )
        # A fresh instance reading the same file must recover the session.
        loaded = SessionVault(path=path).load_session("fw.local")
        assert loaded is not None
        assert loaded["cookies"][0]["value"] == "abc"

    def test_legacy_plaintext_file_is_migrated_to_encrypted(self, tmp_path: Path):
        path = tmp_path / "sessions.json"
        legacy = {
            "old.local": {
                "cookies": [{"name": "c", "value": "v"}],
                "local_storage": {},
                "saved_at": "2026-01-01T00:00:00",
                "domain": "old.local",
            }
        }
        path.write_text(json.dumps(legacy), encoding="utf-8")

        vault = SessionVault(path=path)
        # Legacy plaintext is still readable.
        assert vault.load_session("old.local") is not None
        # A save re-writes the whole store encrypted.
        vault.save_session("new.local", [])
        raw = path.read_text(encoding="utf-8")
        assert "old.local" not in raw
        assert "new.local" not in raw
