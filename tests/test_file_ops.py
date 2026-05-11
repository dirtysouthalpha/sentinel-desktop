"""Tests for safe file operations."""
import pytest

from core import file_ops


def test_write_and_read(tmp_path):
    p = tmp_path / "sub" / "hello.txt"  # parent doesn't exist yet
    assert file_ops.write_file(str(p), "hello world") is True
    assert p.read_text(encoding="utf-8") == "hello world"
    assert file_ops.read_file(str(p)) == "hello world"


def test_read_missing_returns_none(tmp_path):
    assert file_ops.read_file(str(tmp_path / "nope.txt")) is None


def test_list_directory_sorts_dirs_first(tmp_path):
    (tmp_path / "z_dir").mkdir()
    (tmp_path / "a_file.txt").write_text("x", encoding="utf-8")
    entries = file_ops.list_directory(str(tmp_path))
    names = [e["name"] for e in entries]
    assert names[0] == "z_dir"     # directory comes first
    assert names[1] == "a_file.txt"
    assert entries[0]["is_dir"] is True
    assert entries[1]["is_dir"] is False


def test_list_missing_directory_returns_none(tmp_path):
    assert file_ops.list_directory(str(tmp_path / "missing")) is None
