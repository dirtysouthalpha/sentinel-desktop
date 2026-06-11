"""Tests for safe file operations."""

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
    assert names[0] == "z_dir"  # directory comes first
    assert names[1] == "a_file.txt"
    assert entries[0]["is_dir"] is True
    assert entries[1]["is_dir"] is False


def test_list_missing_directory_returns_none(tmp_path):
    assert file_ops.list_directory(str(tmp_path / "missing")) is None


# ---------------------------------------------------------------------------
# Tenant sandbox tests — SENTINEL_SANDBOX_ROOT env var activates enforcement.
# ---------------------------------------------------------------------------


def test_sandbox_blocks_write_outside_root(tmp_path, monkeypatch):
    """Writing outside the sandbox root must fail without touching the FS."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "outside.txt"

    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))

    assert file_ops.write_file(str(outside), "leaked") is False
    assert not outside.exists()


def test_sandbox_blocks_read_outside_root(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret", encoding="utf-8")

    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))

    assert file_ops.read_file(str(secret)) is None


def test_sandbox_blocks_traversal(tmp_path, monkeypatch):
    """``..`` segments that escape the sandbox must be rejected."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))

    escaping = str(sandbox / ".." / "escapee.txt")
    assert file_ops.write_file(escaping, "x") is False
    assert not (tmp_path / "escapee.txt").exists()


def test_sandbox_allows_paths_inside_root(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))

    inside = sandbox / "deep" / "ok.txt"
    assert file_ops.write_file(str(inside), "hi") is True
    assert file_ops.read_file(str(inside)) == "hi"


def test_sandbox_blocks_list_directory_outside_root(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()

    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))

    assert file_ops.list_directory(str(sibling)) is None


def test_lockdown_off_passthrough(tmp_path, monkeypatch):
    """With no env var and lockdown=False, paths work as-given."""
    monkeypatch.delenv("SENTINEL_SANDBOX_ROOT", raising=False)
    # The default Config has tenant_lockdown=False — read/write should
    # work on any path the OS lets us touch.
    p = tmp_path / "ok.txt"
    assert file_ops.write_file(str(p), "data") is True
    assert file_ops.read_file(str(p)) == "data"


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


def test_write_file_returns_false_on_oserror(tmp_path, monkeypatch):
    """write_file should return False when OS prevents write."""

    def bad_open(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", bad_open)
    assert file_ops.write_file(str(tmp_path / "fail.txt"), "x") is False


def test_read_file_with_encoding(tmp_path):
    """read_file should respect the encoding parameter."""
    p = tmp_path / "utf16.txt"
    p.write_text("hello", encoding="utf-16")
    assert file_ops.read_file(str(p), encoding="utf-16") == "hello"


def test_list_directory_includes_file_size(tmp_path):
    """list_directory entries should include size for regular files."""
    (tmp_path / "sized.txt").write_text("12345", encoding="utf-8")
    entries = file_ops.list_directory(str(tmp_path))
    sized = next(e for e in entries if e["name"] == "sized.txt")
    assert sized["size"] == 5
    assert sized["is_dir"] is False


def test_read_file_unicode_error_returns_none(tmp_path):
    """read_file should return None when file can't be decoded."""
    p = tmp_path / "binary.bin"
    p.write_bytes(b"\x80\x81\x82\xff")
    assert file_ops.read_file(str(p), encoding="utf-8") is None


# ---------------------------------------------------------------------------
# PermissionError / OSError branches for file operations
# ---------------------------------------------------------------------------


def test_delete_file_permission_error(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))
    assert file_ops.delete_file(str(outside)) is False


def test_delete_file_oserror(tmp_path, monkeypatch):
    target = tmp_path / "target.txt"
    target.write_text("x")
    monkeypatch.setattr("pathlib.Path.unlink", lambda *a, **kw: (_ for _ in ()).throw(OSError("busy")))
    assert file_ops.delete_file(str(target)) is False


def test_move_file_permission_error(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    src = tmp_path / "src.txt"
    src.write_text("x")
    dst = tmp_path / "dst.txt"
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))
    assert file_ops.move_file(str(src), str(dst)) is False


def test_move_file_oserror(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    src.write_text("x")
    dst = tmp_path / "dst.txt"
    monkeypatch.setattr("pathlib.Path.rename", lambda *a, **kw: (_ for _ in ()).throw(OSError("rename failed")))
    assert file_ops.move_file(str(src), str(dst)) is False


def test_copy_file_permission_error(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    src = tmp_path / "src.txt"
    src.write_text("x")
    dst = tmp_path / "dst.txt"
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))
    assert file_ops.copy_file(str(src), str(dst)) is False


def test_copy_file_oserror(tmp_path, monkeypatch):
    import shutil
    src = tmp_path / "src.txt"
    src.write_text("x")
    dst = tmp_path / "dst.txt"
    monkeypatch.setattr(shutil, "copy2", lambda *a, **kw: (_ for _ in ()).throw(OSError("copy failed")))
    assert file_ops.copy_file(str(src), str(dst)) is False


def test_mkdir_permission_error(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "new_dir"
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))
    assert file_ops.mkdir(str(outside)) is False


def test_mkdir_oserror(tmp_path, monkeypatch):
    target = tmp_path / "blocked_dir"
    monkeypatch.setattr("pathlib.Path.mkdir", lambda *a, **kw: (_ for _ in ()).throw(OSError("read-only")))
    assert file_ops.mkdir(str(target)) is False


def test_stat_file_permission_error(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))
    assert file_ops.stat_file(str(outside)) is None


def test_find_files_permission_error(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))
    assert file_ops.find_files("*.txt", root=str(outside)) is None


def test_find_files_oserror(tmp_path, monkeypatch):
    from glob import glob as real_glob
    monkeypatch.setattr("glob.glob", lambda *a, **kw: (_ for _ in ()).throw(OSError("glob error")))
    assert file_ops.find_files("*.txt", root=str(tmp_path)) is None


def test_archive_create_permission_error(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "out.zip"
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))
    assert file_ops.archive_create(str(outside), []) is False


def test_archive_create_oserror(tmp_path, monkeypatch):
    import zipfile
    archive = tmp_path / "fail.zip"
    monkeypatch.setattr(zipfile, "ZipFile", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
    assert file_ops.archive_create(str(archive), []) is False


def test_archive_extract_permission_error(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside_zip = tmp_path / "archive.zip"
    outside_zip.write_bytes(b"PK")
    monkeypatch.setenv("SENTINEL_SANDBOX_ROOT", str(sandbox))
    assert file_ops.archive_extract(str(outside_zip), str(tmp_path / "out")) is False
