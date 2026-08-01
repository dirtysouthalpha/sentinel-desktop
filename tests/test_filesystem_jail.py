"""The root jail for the dashboard filesystem API.

These tests were written **before** ``core/filesystem.py`` existed, because the
endpoints they guard are arbitrary file read over HTTP on a host that is
reachable across Tailscale, gated only by a bearer token. If the jail leaks, a
leaked token becomes "read any file on the box" — including the token store
itself.

The property under test is always the same one: **resolve first, then verify
containment.** Checking the string before resolving is the classic mistake —
``C:\\AgentLink\\..\\Windows`` passes a ``startswith`` test and resolves outside
the jail, and a junction passes every string test there is.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core import filesystem as fsmod


@pytest.fixture
def jail(tmp_path, monkeypatch):
    """A real on-disk jail with a file inside it and a secret outside it."""
    root = tmp_path / "jail"
    (root / "sub").mkdir(parents=True)
    (root / "inside.txt").write_text("inside the jail", encoding="utf-8")
    (root / "sub" / "nested.txt").write_text("nested", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SENTINEL_API_TOKEN=hunter2", encoding="utf-8")

    monkeypatch.setenv(fsmod.ROOTS_ENV, str(root))
    fsmod.allowed_roots.cache_clear()
    yield root
    fsmod.allowed_roots.cache_clear()


def _denied(path):
    with pytest.raises(fsmod.FilesystemError) as exc:
        fsmod.resolve_within_roots(path)
    return exc.value


# ---------------------------------------------------------------------------
# The happy path must actually work, or the tests below prove nothing
# ---------------------------------------------------------------------------


def test_file_inside_the_jail_resolves(jail):
    assert fsmod.resolve_within_roots(str(jail / "inside.txt")).name == "inside.txt"


def test_nested_file_inside_the_jail_resolves(jail):
    assert fsmod.resolve_within_roots(str(jail / "sub" / "nested.txt")).name == "nested.txt"


def test_the_root_itself_resolves(jail):
    assert fsmod.resolve_within_roots(str(jail)) == jail.resolve()


# ---------------------------------------------------------------------------
# Traversal — every spelling of ".."
# ---------------------------------------------------------------------------


def test_parent_traversal_is_refused(jail):
    assert _denied(str(jail / ".." / "outside" / "secret.txt")).code == "outside_root"


def test_deep_traversal_is_refused(jail):
    assert _denied(str(jail / ".." / ".." / ".." / ".." / "Windows")).code == "outside_root"


def test_forward_slash_traversal_is_refused(jail):
    assert _denied(str(jail).replace("\\", "/") + "/../outside/secret.txt").code == "outside_root"


def test_traversal_embedded_mid_path_is_refused(jail):
    """``jail/sub/../../outside`` — lands outside despite starting inside."""
    assert _denied(str(jail / "sub" / ".." / ".." / "outside" / "secret.txt")).code == "outside_root"


def test_a_sibling_directory_sharing_a_prefix_is_refused(jail):
    """``/tmp/x/jail-evil`` must not pass because it startswith ``/tmp/x/jail``.

    This is why containment is a path-component comparison and not a string
    ``startswith``.
    """
    evil = jail.parent / (jail.name + "-evil")
    evil.mkdir()
    (evil / "secret.txt").write_text("nope", encoding="utf-8")
    assert _denied(str(evil / "secret.txt")).code == "outside_root"


# ---------------------------------------------------------------------------
# Windows-specific escapes
# ---------------------------------------------------------------------------


def test_unc_path_is_refused(jail):
    assert _denied(r"\\evil-host\share\payload.txt").code == "unc"


def test_unc_forward_slash_form_is_refused(jail):
    assert _denied("//evil-host/share/payload.txt").code == "unc"


def test_extended_length_device_path_is_refused(jail):
    assert _denied(r"\\?\C:\Windows\System32\config\SAM").code == "unc"


def test_dos_device_namespace_is_refused(jail):
    assert _denied(r"\\.\PhysicalDrive0").code == "unc"


def test_another_drive_is_refused(jail):
    assert _denied(r"Z:\somewhere\else.txt").code == "outside_root"


@pytest.mark.skipif(os.name != "nt", reason="NTFS alternate data streams are Windows-only")
def test_alternate_data_stream_is_refused(jail):
    assert _denied(str(jail / "inside.txt") + ":$DATA").code in {"outside_root", "ads"}


# ---------------------------------------------------------------------------
# Reparse points — the escape that beats every string check
# ---------------------------------------------------------------------------


def _can_make_links(tmp_path) -> bool:
    """Symlink creation needs privilege or developer mode on Windows."""
    probe, target = tmp_path / "_probe_link", tmp_path / "_probe_target"
    target.mkdir(exist_ok=True)
    try:
        probe.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


def test_symlink_pointing_outside_the_jail_is_refused(jail, tmp_path):
    if not _can_make_links(tmp_path):
        pytest.skip("no privilege to create symlinks on this host")
    link = jail / "escape"
    link.symlink_to(tmp_path / "outside", target_is_directory=True)
    assert _denied(str(link / "secret.txt")).code == "outside_root"


def test_symlink_staying_inside_the_jail_is_allowed(jail, tmp_path):
    if not _can_make_links(tmp_path):
        pytest.skip("no privilege to create symlinks on this host")
    link = jail / "shortcut"
    link.symlink_to(jail / "sub", target_is_directory=True)
    assert fsmod.resolve_within_roots(str(link / "nested.txt")).name == "nested.txt"


# ---------------------------------------------------------------------------
# Malformed and hostile input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_path_is_refused(jail, bad):
    with pytest.raises(fsmod.FilesystemError) as exc:
        fsmod.resolve_within_roots(bad)
    assert exc.value.code == "empty"


def test_nul_byte_is_refused(jail):
    assert _denied(str(jail / "inside.txt") + "\x00.png").code == "nul"


def test_a_missing_path_is_not_found_not_leaked(jail):
    """A path inside the jail that does not exist must not 404 differently
    from one outside it in a way that turns the API into an oracle."""
    with pytest.raises(fsmod.FilesystemError) as exc:
        fsmod.resolve_within_roots(str(jail / "nope.txt"), must_exist=True)
    assert exc.value.code == "not_found"


# ---------------------------------------------------------------------------
# Secret files stay unreadable even inside the jail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [".env", "id_rsa", "id_ed25519", "server.pem", "private.key", ".git-credentials", ".npmrc"],
)
def test_credential_filenames_are_refused(jail, name):
    (jail / name).write_text("secret", encoding="utf-8")
    assert _denied(str(jail / name)).code == "denied_name"


@pytest.mark.parametrize("dirname", [".ssh", ".gnupg", ".aws"])
def test_credential_directories_are_refused(jail, dirname):
    (jail / dirname).mkdir()
    (jail / dirname / "config").write_text("secret", encoding="utf-8")
    assert _denied(str(jail / dirname / "config")).code == "denied_name"


def test_denied_names_are_hidden_from_listings(jail):
    (jail / ".env").write_text("secret", encoding="utf-8")
    names = [e["name"] for e in fsmod.list_directory(str(jail))["entries"]]
    assert ".env" not in names
    assert "inside.txt" in names


# ---------------------------------------------------------------------------
# Size caps
# ---------------------------------------------------------------------------


def test_read_is_truncated_at_the_cap(jail):
    (jail / "big.txt").write_text("x" * 5000, encoding="utf-8")
    out = fsmod.read_file(str(jail / "big.txt"), max_bytes=1000)
    assert out["truncated"] is True
    assert len(out["content"]) <= 1000


def test_read_refuses_a_file_over_the_hard_ceiling(jail, monkeypatch):
    monkeypatch.setattr(fsmod, "MAX_READ_BYTES", 100)
    (jail / "huge.bin").write_bytes(b"\x00" * 500)
    out = fsmod.read_file(str(jail / "huge.bin"), max_bytes=10_000)
    assert out["truncated"] is True
    assert out["bytes_read"] <= 100


def test_max_bytes_cannot_be_raised_past_the_ceiling(jail):
    (jail / "big.txt").write_text("y" * (fsmod.MAX_READ_BYTES + 5000), encoding="utf-8")
    out = fsmod.read_file(str(jail / "big.txt"), max_bytes=fsmod.MAX_READ_BYTES * 100)
    assert out["bytes_read"] <= fsmod.MAX_READ_BYTES


def test_listing_is_bounded(jail, monkeypatch):
    monkeypatch.setattr(fsmod, "MAX_ENTRIES", 5)
    for i in range(20):
        (jail / f"f{i}.txt").write_text("x", encoding="utf-8")
    out = fsmod.list_directory(str(jail))
    assert len(out["entries"]) == 5
    assert out["truncated"] is True


# ---------------------------------------------------------------------------
# Image handling — the data URI the dashboard will render
# ---------------------------------------------------------------------------


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def test_png_returns_a_base64_raster_data_uri(jail):
    (jail / "pic.png").write_bytes(PNG_1PX)
    out = fsmod.read_file(str(jail / "pic.png"))
    assert out["is_image"] is True
    assert out["data_uri"].startswith("data:image/png;base64,")


def test_svg_is_never_served_as_an_image_data_uri(jail):
    """An SVG can carry <script>. It must come back as inert text, never as a
    data URI the dashboard would hand to <img>."""
    (jail / "x.svg").write_text('<svg onload="alert(1)"></svg>', encoding="utf-8")
    out = fsmod.read_file(str(jail / "x.svg"))
    assert out["is_image"] is False
    assert "data_uri" not in out or not out["data_uri"]


def test_a_png_extension_on_non_image_bytes_is_not_trusted(jail):
    """Sniff the magic bytes, don't trust the extension."""
    (jail / "fake.png").write_text("<svg onload=alert(1)>", encoding="utf-8")
    out = fsmod.read_file(str(jail / "fake.png"))
    assert out["is_image"] is False


# ---------------------------------------------------------------------------
# Download filename sanitisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ['we"ird.txt', "back`tick.txt", "new\nline.txt", "semi;colon.txt", "quote'.txt"],
)
def test_download_filename_is_sanitised(jail, raw):
    target = jail / "safe.txt"
    target.write_text("x", encoding="utf-8")
    cleaned = fsmod.safe_download_name(raw)
    assert not set(cleaned) & set('"`\n\r;\\/')
    assert cleaned


def test_download_filename_never_empty(jail):
    assert fsmod.safe_download_name('"""') == "download"
    assert fsmod.safe_download_name("") == "download"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_multiple_roots_are_honoured(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x.txt").write_text("x", encoding="utf-8")
    (b / "y.txt").write_text("y", encoding="utf-8")
    monkeypatch.setenv(fsmod.ROOTS_ENV, os.pathsep.join([str(a), str(b)]))
    fsmod.allowed_roots.cache_clear()
    try:
        assert fsmod.resolve_within_roots(str(a / "x.txt")).name == "x.txt"
        assert fsmod.resolve_within_roots(str(b / "y.txt")).name == "y.txt"
        assert _denied(str(tmp_path / "c.txt")).code == "outside_root"
    finally:
        fsmod.allowed_roots.cache_clear()


def test_a_nonexistent_configured_root_is_dropped_not_fatal(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    monkeypatch.setenv(fsmod.ROOTS_ENV, os.pathsep.join([str(real), str(tmp_path / "ghost")]))
    fsmod.allowed_roots.cache_clear()
    try:
        assert fsmod.allowed_roots() == (real.resolve(),)
    finally:
        fsmod.allowed_roots.cache_clear()


def test_no_usable_roots_is_reported_as_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv(fsmod.ROOTS_ENV, str(tmp_path / "does-not-exist"))
    fsmod.allowed_roots.cache_clear()
    try:
        with pytest.raises(fsmod.FilesystemError) as exc:
            fsmod.resolve_within_roots(str(tmp_path / "anything"))
        assert exc.value.code == "no_roots"
        assert exc.value.status == 503
    finally:
        fsmod.allowed_roots.cache_clear()


def test_listing_a_file_rather_than_a_directory_is_refused(jail):
    with pytest.raises(fsmod.FilesystemError) as exc:
        fsmod.list_directory(str(jail / "inside.txt"))
    assert exc.value.code == "not_a_directory"


def test_entries_carry_the_full_resolved_path(jail):
    """The dashboard uses ``entry.path`` verbatim for the next request, so it
    must already be jail-legal."""
    for entry in fsmod.list_directory(str(jail))["entries"]:
        assert Path(entry["path"]).is_absolute()
        fsmod.resolve_within_roots(entry["path"])
