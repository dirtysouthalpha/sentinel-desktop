"""Path-traversal guards on plugin install/uninstall (ported from v22 Aria)."""

from __future__ import annotations

import pytest

from core import marketplace
from core.marketplace import (
    _is_metadata_url,
    _safe_plugin_path,
    install_plugin,
    uninstall_plugin,
)


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.170.2/v2/credentials",
        "http://metadata.google.internal/computeMetadata/v1/",
        "https://metadata.azure.com/metadata/instance",
        "http://169.254.99.99/anything",
    ],
)
def test_is_metadata_url_blocks_ssrf(bad_url):
    assert _is_metadata_url(bad_url) is True


@pytest.mark.parametrize(
    "ok_url",
    [
        "https://raw.githubusercontent.com/dirtysouthalpha/x/main/p.py",
        "https://example.com/plugin.py",
    ],
)
def test_is_metadata_url_allows_normal(ok_url):
    assert _is_metadata_url(ok_url) is False


def test_install_refuses_metadata_download_url(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr(marketplace, "PLUGINS_DIR", plugins)
    evil = marketplace.PluginInfo(
        name="weather", version="1.0",
        download_url="http://169.254.169.254/latest/meta-data/",
    )
    monkeypatch.setattr(marketplace, "fetch_registry", lambda: [evil])
    result = install_plugin("weather")
    assert result["success"] is False
    assert "metadata" in result["message"].lower()


@pytest.mark.parametrize(
    "bad_name",
    [
        "../../core/engine",
        "..\\..\\core\\engine",
        "../evil",
        "/etc/passwd",
        "sub/dir",
        ".hidden",
        "-leadingdash",
        "..",
        "",
    ],
)
def test_safe_plugin_path_rejects_traversal(bad_name):
    with pytest.raises(ValueError):
        _safe_plugin_path(bad_name)


@pytest.mark.parametrize("good_name", ["weather", "my_plugin", "plugin-2", "a.b.c", "X1"])
def test_safe_plugin_path_accepts_valid_names(good_name):
    dest = _safe_plugin_path(good_name)
    assert dest.name == f"{good_name}.py"
    assert dest.parent == marketplace.PLUGINS_DIR.resolve()


def test_uninstall_rejects_traversal_name_without_touching_fs(tmp_path, monkeypatch):
    # Point PLUGINS_DIR at a temp dir and drop a sentinel file one level up
    # that a traversal name would target.
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    victim = tmp_path / "victim.py"
    victim.write_text("keep me")
    monkeypatch.setattr(marketplace, "PLUGINS_DIR", plugins)

    result = uninstall_plugin("../victim")
    assert result["success"] is False
    assert "Rejected plugin name" in result["message"]
    assert victim.exists()  # traversal did not delete it


def test_install_rejects_traversal_name(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr(marketplace, "PLUGINS_DIR", plugins)

    # Registry returns a plugin whose name is a traversal string.
    evil = marketplace.PluginInfo(
        name="../../evil", version="1.0", download_url="http://x/evil"
    )
    monkeypatch.setattr(marketplace, "fetch_registry", lambda: [evil])
    # Make the download return valid python so we reach the write step.
    import urllib.request

    class _Resp:
        def read(self):
            return b"x = 1\n"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())

    result = install_plugin("../../evil")
    assert result["success"] is False
    assert "Rejected plugin name" in result["message"]
    assert not (tmp_path / "evil.py").exists()  # nothing written outside plugins
