"""Gap tests for action_executor.py — 5th batch.

Covers remaining 8 uncovered lines after gaps4:
  1304      _delete_file success return
  1311      _move_file success return
  1318      _copy_file success return
  1380      _archive_create failure return
  1399      _archive_extract failure return
  1982-1983 _get_semantic_memory lazy-init branch
  2289      _volume_get success return
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import core.desktop as desktop_mod
import core.file_ops as file_ops_mod
from core.action_executor import ActionExecutor


def _make_executor() -> ActionExecutor:
    original = desktop_mod.DesktopEngine
    desktop_mod.DesktopEngine = MagicMock
    try:
        return ActionExecutor()
    finally:
        desktop_mod.DesktopEngine = original


class TestFileOpsSuccess:
    """Lines 1304, 1311, 1318 — success branches for delete/move/copy."""

    def test_delete_file_success(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "delete_file", return_value=True):
            result = ex._delete_file(path="/tmp/old.txt")
        assert result["success"] is True
        assert "old.txt" in result["output"]

    def test_move_file_success(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "move_file", return_value=True):
            result = ex._move_file(src="/tmp/a.txt", dst="/tmp/b.txt")
        assert result["success"] is True
        assert "a.txt" in result["output"]

    def test_copy_file_success(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "copy_file", return_value=True):
            result = ex._copy_file(src="/tmp/src.txt", dst="/tmp/dst.txt")
        assert result["success"] is True
        assert "src.txt" in result["output"]


class TestArchiveFailure:
    """Lines 1380, 1399 — archive create/extract failure paths."""

    def test_archive_create_failure(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "archive_create", return_value=False):
            result = ex._archive_create(archive_path="/tmp/out.zip", files=["a.txt"])
        assert result["success"] is False
        assert "Failed" in result["output"]

    def test_archive_extract_failure(self):
        ex = _make_executor()
        with patch.object(file_ops_mod, "archive_extract", return_value=False):
            result = ex._archive_extract(archive_path="/tmp/out.zip", dest_dir="/tmp/out")
        assert result["success"] is False
        assert "Failed" in result["output"]


class TestGetSemanticMemoryLazyInit:
    """Lines 1982-1983 — _get_semantic_memory creates SemanticMemory when None."""

    def test_lazy_init_creates_semantic_memory_instance(self):
        ex = _make_executor()
        # _semantic_memory is None at construction time
        assert ex._semantic_memory is None

        fake_mem = MagicMock()
        fake_mem.delete.return_value = True

        with patch("core.memory.semantic.SemanticMemory", return_value=fake_mem):
            result = ex._memory_forget(key="old_fact")

        # Lazy init was triggered; instance is now cached
        assert ex._semantic_memory is fake_mem
        assert result["success"] is True

    def test_lazy_init_reuses_cached_instance(self):
        ex = _make_executor()
        fake_mem = MagicMock()
        fake_mem.delete.return_value = True

        with patch("core.memory.semantic.SemanticMemory", return_value=fake_mem) as mock_cls:
            ex._memory_forget(key="k1")
            ex._memory_forget(key="k2")

        # Constructor called only once even though we called _memory_forget twice
        mock_cls.assert_called_once()


class TestVolumeGetSuccess:
    """Line 2289 — _volume_get success return when level >= 0."""

    def test_volume_get_returns_level(self):
        ex = _make_executor()
        with patch("core.audio.volume_get", return_value=60):
            result = ex._volume_get()
        assert result["success"] is True
        assert result["level"] == 60
        assert "60%" in result["output"]

    def test_volume_get_failure_when_negative(self):
        ex = _make_executor()
        with patch("core.audio.volume_get", return_value=-1):
            result = ex._volume_get()
        assert result["success"] is False
        assert "unavailable" in result["output"].lower()
