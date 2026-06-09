"""Tests for v13.0 File Operations Plus — file_ops, schemas, executor, tools."""

from __future__ import annotations

import pytest

from core.action_schemas import (
    ACTION_MODELS,
    DeleteFileAction,
    FindFilesAction,
    MoveFileAction,
)
from core.file_ops import (
    archive_create,
    archive_extract,
    copy_file,
    delete_file,
    find_files,
    mkdir,
    move_file,
    stat_file,
)
from core.tool_schemas import TOOLS


@pytest.fixture
def tmp(tmp_path):
    """Provide a temp directory with test files."""
    (tmp_path / "hello.txt").write_text("hello world", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text("inner", encoding="utf-8")
    return tmp_path


# ── file_ops module tests ────────────────────────────────────────────


class TestDeleteFile:
    def test_delete_file(self, tmp):
        f = tmp / "hello.txt"
        assert f.exists()
        assert delete_file(str(f)) is True
        assert not f.exists()

    def test_delete_missing_file(self, tmp):
        assert delete_file(str(tmp / "nope.txt")) is True

    def test_delete_empty_dir(self, tmp):
        d = tmp / "empty"
        d.mkdir()
        assert delete_file(str(d)) is True
        assert not d.exists()

    def test_delete_nonempty_dir_no_force(self, tmp):
        assert delete_file(str(tmp / "sub")) is False

    def test_delete_nonempty_dir_force(self, tmp):
        assert delete_file(str(tmp / "sub"), force=True) is True
        assert not (tmp / "sub").exists()


class TestMoveFile:
    def test_move_file(self, tmp):
        src = tmp / "hello.txt"
        dst = tmp / "moved.txt"
        assert move_file(str(src), str(dst)) is True
        assert not src.exists()
        assert dst.read_text(encoding="utf-8") == "hello world"

    def test_move_nonexistent(self, tmp):
        assert move_file(str(tmp / "nope"), str(tmp / "dst")) is False


class TestCopyFile:
    def test_copy_file(self, tmp):
        src = tmp / "hello.txt"
        dst = tmp / "copy.txt"
        assert copy_file(str(src), str(dst)) is True
        assert src.exists()
        assert dst.read_text(encoding="utf-8") == "hello world"

    def test_copy_creates_parent(self, tmp):
        dst = tmp / "new_dir" / "copy.txt"
        assert copy_file(str(tmp / "hello.txt"), str(dst)) is True
        assert dst.exists()


class TestMkdir:
    def test_mkdir(self, tmp):
        d = tmp / "new_folder"
        assert mkdir(str(d)) is True
        assert d.is_dir()

    def test_mkdir_nested(self, tmp):
        d = tmp / "a" / "b" / "c"
        assert mkdir(str(d), parents=True) is True
        assert d.is_dir()

    def test_mkdir_exists(self, tmp):
        assert mkdir(str(tmp)) is True


class TestStatFile:
    def test_stat_file(self, tmp):
        info = stat_file(str(tmp / "hello.txt"))
        assert info is not None
        assert info["is_file"] is True
        assert info["size"] == 11
        assert info["name"] == "hello.txt"

    def test_stat_dir(self, tmp):
        info = stat_file(str(tmp / "sub"))
        assert info is not None
        assert info["is_dir"] is True

    def test_stat_missing(self, tmp):
        assert stat_file(str(tmp / "nope")) is None


class TestFindFiles:
    def test_find_txt(self, tmp):
        results = find_files("*.txt", root=str(tmp))
        assert results is not None
        assert len(results) >= 2

    def test_find_none(self, tmp):
        results = find_files("*.xyz", root=str(tmp))
        assert results is not None
        assert len(results) == 0

    def test_find_max_results(self, tmp):
        results = find_files("*", root=str(tmp), max_results=1)
        assert results is not None
        assert len(results) <= 1


class TestArchive:
    def test_create_and_extract(self, tmp):
        archive = tmp / "test.zip"
        files = ["hello.txt", "sub/inner.txt"]
        assert archive_create(str(archive), files, base_dir=str(tmp)) is True
        assert archive.exists()

        dest = tmp / "extracted"
        assert archive_extract(str(archive), dest_dir=str(dest)) is True
        assert (dest / "hello.txt").read_text(encoding="utf-8") == "hello world"
        assert (dest / "sub" / "inner.txt").read_text() == "inner"

    def test_extract_nonexistent(self, tmp):
        assert archive_extract(str(tmp / "nope.zip")) is False


# ── Action schema tests ─────────────────────────────────────────────


class TestFileOpSchemas:
    def test_all_registered(self):
        for action in [
            "delete_file", "move_file", "copy_file", "mkdir",
            "stat_file", "find_files", "archive_create",
            "archive_extract",
        ]:
            assert action in ACTION_MODELS

    def test_delete_file_valid(self):
        a = DeleteFileAction(action="delete_file", path="/tmp/x")
        assert a.force is False

    def test_move_file_valid(self):
        a = MoveFileAction(action="move_file", src="/a", dst="/b")
        assert a.src == "/a"

    def test_find_files_max_results(self):
        a = FindFilesAction(action="find_files", pattern="*", max_results=50)
        assert a.max_results == 50


# ── Executor dispatch tests ─────────────────────────────────────────


class TestFileOpExecutor:
    def test_dispatch_table_entries(self):
        from core.action_executor import ActionExecutor
        for action in [
            "delete_file", "move_file", "copy_file", "mkdir",
            "stat_file", "find_files", "archive_create",
            "archive_extract",
        ]:
            assert action in ActionExecutor._dispatch_table

    def test_mkdir_executor(self, tmp):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        result = executor._mkdir(path=str(tmp / "new_dir"))
        assert result["success"] is True

    def test_stat_file_executor(self, tmp):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        result = executor._stat_file(path=str(tmp / "hello.txt"))
        assert result["success"] is True
        assert result["output"]["size"] == 11

    def test_find_files_executor(self, tmp):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        result = executor._find_files(pattern="*.txt", root=str(tmp))
        assert result["success"] is True
        assert result["count"] >= 2


# ── Tool schema tests ────────────────────────────────────────────────


class TestFileOpToolSchemas:
    def test_all_tools_exist(self):
        names = [t["function"]["name"] for t in TOOLS]
        for tool in [
            "delete_file", "move_file", "copy_file", "mkdir",
            "stat_file", "find_files", "archive_create",
            "archive_extract",
        ]:
            assert tool in names

    def test_delete_file_params(self):
        tool = next(t for t in TOOLS if t["function"]["name"] == "delete_file")
        props = tool["function"]["parameters"]["properties"]
        assert "path" in props
        assert "force" in props
