"""Regression tests for the v31 marketplace download hardening.

Two defects:

1. ``_is_metadata_url`` blocked only 169.254.*/known-metadata hosts, so a
   registry-supplied ``file://`` or ``http://localhost/...`` download URL was
   still fetched and written into ``plugins/`` — where it becomes importable
   Python.
2. ``if plugin.sha256:`` silently skipped integrity verification whenever the
   registry omitted the hash, i.e. an attacker-controlled registry could just
   leave it out.
"""

from __future__ import annotations

import hashlib
import urllib.request

import pytest

from core import marketplace
from core.marketplace import _is_allowed_download_url, install_plugin

PAYLOAD = b"x = 1\n"
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


class _Resp:
    def __init__(self, content=PAYLOAD):
        self._content = content

    def read(self):
        return self._content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def plugins_dir(tmp_path, monkeypatch):
    d = tmp_path / "plugins"
    d.mkdir()
    monkeypatch.setattr(marketplace, "PLUGINS_DIR", d)
    return d


def _register(monkeypatch, **kwargs):
    kwargs.setdefault("name", "weather")
    kwargs.setdefault("version", "1.0")
    plugin = marketplace.PluginInfo(**kwargs)
    monkeypatch.setattr(marketplace, "fetch_registry", lambda: [plugin])
    return plugin


# ---------------------------------------------------------------------------
# URL allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_url",
    [
        # non-https schemes
        "file:///C:/Windows/System32/drivers/etc/hosts",
        "file:///etc/passwd",
        "http://example.com/plugin.py",
        "ftp://example.com/plugin.py",
        "gopher://example.com/1",
        "data:text/plain,x%20%3D%201",
        "jar:http://example.com/a.jar!/b",
        "plugin.py",
        "",
        # loopback / link-local / unspecified
        "https://localhost/plugin.py",
        "https://127.0.0.1/plugin.py",
        "https://127.0.0.5:8443/plugin.py",
        "https://[::1]/plugin.py",
        "https://0.0.0.0/plugin.py",
        "https://169.254.169.254/latest/meta-data/",
        "https://metadata.google.internal/x",
        "https://foo.localhost/plugin.py",
    ],
)
def test_disallowed_download_urls(bad_url):
    ok, reason = _is_allowed_download_url(bad_url)
    assert ok is False, f"{bad_url!r} was allowed"
    assert reason


@pytest.mark.parametrize(
    "ok_url",
    [
        "https://raw.githubusercontent.com/dirtysouthalpha/x/main/p.py",
        "https://example.com/plugin.py",
        "https://example.com:8443/plugin.py",
        "https://93.184.216.34/plugin.py",
    ],
)
def test_allowed_download_urls(ok_url):
    ok, reason = _is_allowed_download_url(ok_url)
    assert ok is True, f"{ok_url!r} rejected: {reason}"
    assert reason == ""


@pytest.mark.parametrize(
    "bad_url",
    [
        "file:///etc/passwd",
        "http://example.com/plugin.py",
        "https://localhost/plugin.py",
        "https://127.0.0.1/plugin.py",
    ],
)
def test_install_refuses_disallowed_url_without_fetching(plugins_dir, monkeypatch, bad_url):
    _register(monkeypatch, download_url=bad_url, sha256=PAYLOAD_SHA)

    def _boom(*a, **k):
        raise AssertionError(f"fetched a disallowed URL: {bad_url}")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    result = install_plugin("weather")
    assert result["success"] is False
    assert "Rejected download URL" in result["message"]
    assert list(plugins_dir.iterdir()) == []


def test_install_refuses_file_url_and_writes_nothing(plugins_dir, monkeypatch, tmp_path):
    """A file:// URL must not be turned into an importable plugin."""
    secret = tmp_path / "secret.txt"
    secret.write_text("import os  # attacker payload\n")
    _register(monkeypatch, download_url=secret.as_uri(), sha256=PAYLOAD_SHA)
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("fetched"))
    )
    result = install_plugin("weather")
    assert result["success"] is False
    assert not (plugins_dir / "weather.py").exists()


# ---------------------------------------------------------------------------
# Mandatory integrity check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_hash", ["", None, "   ", "abc", "notahash", "A" * 63, "z" * 64])
def test_install_requires_a_valid_sha256(plugins_dir, monkeypatch, missing_hash):
    """An unpinned or malformed hash must refuse the install, not skip the check."""
    _register(monkeypatch, download_url="https://example.com/p.py", sha256=missing_hash)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())

    result = install_plugin("weather")
    assert result["success"] is False
    assert "sha256" in result["message"].lower()
    assert not (plugins_dir / "weather.py").exists()


def test_install_rejects_hash_mismatch(plugins_dir, monkeypatch):
    _register(monkeypatch, download_url="https://example.com/p.py", sha256="0" * 64)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())

    result = install_plugin("weather")
    assert result["success"] is False
    assert "mismatch" in result["message"].lower()
    assert not (plugins_dir / "weather.py").exists()


def test_install_succeeds_with_https_and_matching_hash(plugins_dir, monkeypatch):
    _register(monkeypatch, download_url="https://example.com/p.py", sha256=PAYLOAD_SHA)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())

    result = install_plugin("weather")
    assert result["success"] is True, result["message"]
    assert (plugins_dir / "weather.py").read_bytes() == PAYLOAD


def test_install_accepts_uppercase_registry_hash(plugins_dir, monkeypatch):
    _register(monkeypatch, download_url="https://example.com/p.py", sha256=PAYLOAD_SHA.upper())
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    assert install_plugin("weather")["success"] is True


def test_traversal_name_rejected_before_any_network_access(plugins_dir, monkeypatch):
    """A name we would never install must not trigger a download."""
    _register(monkeypatch, name="../../evil", download_url="https://example.com/p.py",
              sha256=PAYLOAD_SHA)

    def _boom(*a, **k):
        raise AssertionError("downloaded content for a rejected plugin name")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    result = install_plugin("../../evil")
    assert result["success"] is False
    assert "Rejected plugin name" in result["message"]
