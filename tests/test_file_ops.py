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
    assert names[0] == "z_dir"     # directory comes first
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
