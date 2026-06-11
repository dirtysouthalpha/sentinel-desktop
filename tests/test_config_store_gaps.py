"""Gap tests for core.config_store — covers lines 67-69, 112, 116, 136, 156."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.config_store import ConfigStore, get_default_store


class TestConfigStoreSaveOSError:
    """OSError in save() returns False (lines 67-69)."""

    def test_save_oserror_returns_false(self, tmp_path):
        cfg = ConfigStore(path=tmp_path / "cfg.json")
        cfg.set("k", "v", auto_save=False)

        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = cfg.save()

        assert result is False

    def test_save_oserror_logs_error(self, tmp_path, caplog):
        import logging
        cfg = ConfigStore(path=tmp_path / "cfg.json")
        cfg.set("x", 1, auto_save=False)

        with patch.object(Path, "write_text", side_effect=OSError("no space")):
            with caplog.at_level(logging.ERROR, logger="core.config_store"):
                cfg.save()

        assert "save failed" in caplog.text.lower() or "Config save failed" in caplog.text


class TestConfigStoreDeleteAutoSave:
    """delete() with auto_save=True calls save() (lines 112, 116)."""

    def test_delete_existing_nested_key_autosave(self, tmp_path):
        cfg = ConfigStore(path=tmp_path / "cfg.json")
        cfg.set("a.b", 42, auto_save=False)

        # auto_save=True → save() should be called on deletion of existing key
        result = cfg.delete("a.b", auto_save=True)

        assert result is True
        # Reload to confirm persistence
        reloaded = ConfigStore(path=tmp_path / "cfg.json")
        assert reloaded.get("a.b") is None

    def test_delete_traverses_nested_path(self, tmp_path):
        """Line 112 — node = node[part] inside delete() for loop."""
        cfg = ConfigStore(path=tmp_path / "cfg.json")
        cfg.set("x.y.z", "deep", auto_save=False)

        result = cfg.delete("x.y.z", auto_save=False)
        assert result is True
        assert cfg.get("x.y.z") is None

    def test_delete_auto_save_true_calls_save(self, tmp_path):
        cfg = ConfigStore(path=tmp_path / "cfg.json")
        cfg.set("key", "val", auto_save=False)

        with patch.object(cfg, "save", wraps=cfg.save) as mock_save:
            cfg.delete("key", auto_save=True)

        mock_save.assert_called_once()

    def test_delete_auto_save_not_called_when_key_missing(self, tmp_path):
        cfg = ConfigStore(path=tmp_path / "cfg.json")

        with patch.object(cfg, "save") as mock_save:
            result = cfg.delete("nonexistent", auto_save=True)

        assert result is False
        mock_save.assert_not_called()


class TestConfigStoreResetAutoSave:
    """reset() with auto_save=True calls save() (line 136)."""

    def test_reset_autosave_persists_empty(self, tmp_path):
        cfg = ConfigStore(path=tmp_path / "cfg.json")
        cfg.set("a", 1, auto_save=False)
        cfg.set("b", 2, auto_save=False)

        cfg.reset(auto_save=True)

        reloaded = ConfigStore(path=tmp_path / "cfg.json")
        assert reloaded.keys() == []

    def test_reset_autosave_calls_save(self, tmp_path):
        cfg = ConfigStore(path=tmp_path / "cfg.json")
        cfg.set("x", 99, auto_save=False)

        with patch.object(cfg, "save", wraps=cfg.save) as mock_save:
            cfg.reset(auto_save=True)

        mock_save.assert_called_once()


class TestGetDefaultStoreSingleton:
    """get_default_store() creates singleton (line 156)."""

    def test_get_default_store_returns_config_store(self, monkeypatch):
        import core.config_store as cs
        monkeypatch.setattr(cs, "_SINGLETON", None)
        # Patch the path so it uses a temp location
        import tempfile, os
        tmp = tempfile.mktemp(suffix=".json")
        monkeypatch.setattr(cs, "_DEFAULT_PATH", Path(tmp))

        store = get_default_store()
        assert isinstance(store, ConfigStore)

    def test_get_default_store_returns_same_instance(self, monkeypatch):
        import core.config_store as cs
        monkeypatch.setattr(cs, "_SINGLETON", None)
        import tempfile
        tmp = tempfile.mktemp(suffix=".json")
        monkeypatch.setattr(cs, "_DEFAULT_PATH", Path(tmp))

        s1 = get_default_store()
        s2 = get_default_store()
        assert s1 is s2
