"""Tests for core/paths.py — shared storage resolver."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _clean_portable_env(monkeypatch):
    """Ensure SENTINEL_PORTABLE is unset for each test unless explicitly set."""
    monkeypatch.delenv("SENTINEL_PORTABLE", raising=False)
    yield


class TestIsPortable:
    def test_not_portable_by_default(self):
        from core import paths

        assert paths.is_portable() is False

    def test_portable_via_env_var_1(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_PORTABLE", "1")
        from core import paths

        assert paths.is_portable() is True

    def test_portable_via_env_var_true(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_PORTABLE", "true")
        from core import paths

        assert paths.is_portable() is True

    def test_portable_via_env_var_yes(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_PORTABLE", "yes")
        from core import paths

        assert paths.is_portable() is True

    def test_portable_via_marker_dir(self, tmp_path, monkeypatch):
        marker = tmp_path / "portable_data"
        marker.mkdir()
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        from core import paths

        assert paths.is_portable() is True

    def test_not_portable_marker_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        from core import paths

        assert paths.is_portable() is False


class TestDataDir:
    def test_default_non_portable_linux(self, monkeypatch):
        monkeypatch.setattr(os, "name", "posix")
        from core import paths

        result = paths.data_dir()
        assert result == Path.home() / ".sentinel-desktop"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only path branch")
    def test_default_non_portable_windows(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        from core import paths

        result = paths.data_dir()
        assert result == tmp_path / "SentinelDesktop"

    def test_portable_redirects_to_portable_data(self, tmp_path, monkeypatch):
        marker = tmp_path / "portable_data"
        marker.mkdir()
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        from core import paths

        result = paths.data_dir()
        assert result == marker

    def test_portable_via_env_overrides_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SENTINEL_PORTABLE", "1")
        monkeypatch.setattr(sys, "executable", str(tmp_path / "sentinel"))
        from core import paths

        result = paths.data_dir()
        assert result == tmp_path / "portable_data"


class TestConfigPath:
    def test_config_path_is_under_data_dir(self, monkeypatch):
        from core import paths

        with patch.object(paths, "data_dir", return_value=Path("/fake/data")):
            result = paths.config_path()
        assert result == Path("/fake/data/config.json")

    def test_config_path_non_portable_linux(self, monkeypatch):
        monkeypatch.setattr(os, "name", "posix")
        from core import paths

        assert paths.config_path() == Path.home() / ".sentinel-desktop" / "config.json"


class TestCheckpointDir:
    def test_checkpoint_dir_is_under_data_dir(self, monkeypatch):
        from core import paths

        with patch.object(paths, "data_dir", return_value=Path("/fake/data")):
            result = paths.checkpoint_dir()
        assert result == Path("/fake/data/checkpoints")

    def test_checkpoint_dir_non_portable_linux(self, monkeypatch):
        monkeypatch.setattr(os, "name", "posix")
        from core import paths

        assert paths.checkpoint_dir() == Path.home() / ".sentinel-desktop" / "checkpoints"


class TestDedup:
    """Prove config.py and checkpoint.py both use core.paths (dedup guarantee)."""

    def test_config_and_checkpoint_same_data_dir(self, monkeypatch):
        """Config dir and checkpoint base must resolve to the same root."""
        import config as cfg_mod
        import core.checkpoint as ckpt_mod

        assert cfg_mod._CONFIG_DIR == ckpt_mod._BASE_DIR

    def test_checkpoint_uses_paths_checkpoint_dir(self, monkeypatch):
        import core.checkpoint as ckpt_mod
        from core import paths

        assert ckpt_mod._CHECKPOINT_DIR == paths.checkpoint_dir()

    def test_config_uses_paths_config_path(self, monkeypatch):
        import config as cfg_mod
        from core import paths

        assert cfg_mod._CONFIG_PATH == paths.config_path()
