"""Tests for core/plugin_loader.py — reload failure edge case, get_all_commands,
get_all_settings, _ensure_plugin_dir OSError."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from core.plugin_loader import PluginLoader


def _write_plugin(tmp_path: Path, filename: str, content: str) -> Path:
    plugin_file = tmp_path / filename
    plugin_file.write_text(textwrap.dedent(content), encoding="utf-8")
    return plugin_file


VALID_PLUGIN = """\
    PLUGIN_NAME = "TestPlugin"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "A test plugin"

    def register(api):
        api.register_action("greet", lambda **kw: {"success": True}, "Say hello")
        api.register_command("hi", lambda text: {"success": True}, keywords=["hello"])
        api.register_setting("theme", default="dark", label="Color theme")
"""

BAD_SYNTAX_PLUGIN = """\
    PLUGIN_NAME = "BadSyntax
    # Missing closing quote
"""


class TestReloadFailureAfterUnload:
    def test_reload_failure_returns_false(self, tmp_path: Path) -> None:
        """If unload succeeds but re-load fails, reload_plugin returns False."""
        path = _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(path)

        # Overwrite the plugin file with bad syntax so reload fails
        path.write_text(textwrap.dedent(BAD_SYNTAX_PLUGIN), encoding="utf-8")

        result = loader.reload_plugin("TestPlugin")
        assert result is False

    def test_plugin_removed_from_registry_after_failed_reload(self, tmp_path: Path) -> None:
        """After a failed reload, the plugin should not remain loaded."""
        path = _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(path)

        path.write_text(textwrap.dedent(BAD_SYNTAX_PLUGIN), encoding="utf-8")

        loader.reload_plugin("TestPlugin")
        assert "TestPlugin" not in loader
        assert len(loader) == 0


class TestGetAllCommands:
    def test_returns_commands_from_all_plugins(self, tmp_path: Path) -> None:
        _write_plugin(tmp_path, "plugin1.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "plugin1.py")

        commands = loader.get_all_commands()
        assert len(commands) == 1
        assert commands[0].name == "hi"
        assert commands[0].keywords == ["hello"]

    def test_returns_empty_when_no_plugins(self, tmp_path: Path) -> None:
        loader = PluginLoader(plugin_dir=tmp_path)
        assert loader.get_all_commands() == []

    def test_returns_multiple_plugins_commands(self, tmp_path: Path) -> None:
        plugin2 = """\
            PLUGIN_NAME = "PluginTwo"
            PLUGIN_VERSION = "1.0.0"
            PLUGIN_DESCRIPTION = "Second plugin"

            def register(api):
                api.register_command("bye", lambda text: None, keywords=["goodbye"])
        """
        _write_plugin(tmp_path, "plugin1.py", VALID_PLUGIN)
        _write_plugin(tmp_path, "plugin2.py", plugin2)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "plugin1.py")
        loader.load_plugin(tmp_path / "plugin2.py")

        commands = loader.get_all_commands()
        assert len(commands) == 2
        names = [c.name for c in commands]
        assert "hi" in names
        assert "bye" in names


class TestGetAllSettings:
    def test_returns_settings_from_all_plugins(self, tmp_path: Path) -> None:
        _write_plugin(tmp_path, "plugin1.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "plugin1.py")

        settings = loader.get_all_settings()
        assert len(settings) == 1
        assert settings[0].key == "theme"
        assert settings[0].default == "dark"

    def test_returns_empty_when_no_plugins(self, tmp_path: Path) -> None:
        loader = PluginLoader(plugin_dir=tmp_path)
        assert loader.get_all_settings() == []


class TestEnsurePluginDir:
    def test_raises_on_makedirs_failure(self, tmp_path: Path) -> None:
        """If mkdir fails, _ensure_plugin_dir should raise."""
        # Create a file where a directory is expected
        blocker = tmp_path / "blocked"
        blocker.write_text("i am a file", encoding="utf-8")
        loader = PluginLoader(plugin_dir=blocker / "subdir")
        with pytest.raises(OSError):
            loader._ensure_plugin_dir()
