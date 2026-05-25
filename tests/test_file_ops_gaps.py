"""Gap tests for file_ops.py — _get_lockdown_root import/error paths."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import core.file_ops as file_ops
from core.file_ops import _get_lockdown_root, list_directory


class TestGetLockdownRootErrors:
    """_get_lockdown_root handles config import and load failures."""

    def test_import_error_returns_none(self) -> None:
        with patch.dict("sys.modules", {"config": None}):
            result = _get_lockdown_root()
        assert result is None

    def test_os_error_returns_none(self) -> None:
        mock_config = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        mock_config.Config.return_value.load.side_effect = OSError("config missing")
        with patch.dict("sys.modules", {"config": mock_config}):
            result = _get_lockdown_root()
        assert result is None

    def test_tenant_lockdown_enabled_returns_home_sandbox(self, monkeypatch) -> None:
        monkeypatch.delenv("SENTINEL_SANDBOX_ROOT", raising=False)
        mock_config = MagicMock()
        mock_config.Config.return_value.get.return_value = True
        with patch.dict("sys.modules", {"config": mock_config}):
            result = _get_lockdown_root()
        assert result == (Path.home() / "SentinelDesktop").resolve(strict=False)


class TestListDirectorySkipsUnreadableEntries:
    """list_directory skips entries whose stat()/is_dir() raise OSError."""

    def test_unreadable_entry_is_skipped(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(file_ops, "_get_lockdown_root", lambda: None)

        good = MagicMock()
        good.name = "good.txt"
        good.is_dir.return_value = False
        good.is_file.return_value = True
        good.stat.return_value = MagicMock(st_size=10)

        bad = MagicMock()
        bad.name = "bad.txt"
        bad.is_dir.side_effect = OSError("permission denied")

        monkeypatch.setattr(file_ops.os, "scandir", lambda _p: iter([good, bad]))
        result = list_directory(str(tmp_path))
        assert result is not None
        names = [e["name"] for e in result]
        assert names == ["good.txt"]
