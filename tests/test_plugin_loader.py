"""Tests for core/plugin_loader.py — plugin discovery, loading, and management."""

import textwrap

import pytest

from core.plugin_loader import REQUIRED_PLUGIN_ATTRS, PluginAPI, PluginLoader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_plugin(tmp_path, filename, content):
    """Write a plugin .py file into the plugin directory."""
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

MISSING_ATTR_PLUGIN = """\
    PLUGIN_NAME = "BadPlugin"
    # Missing PLUGIN_VERSION and PLUGIN_DESCRIPTION

    def register(api):
        pass
"""

MISSING_REGISTER_PLUGIN = """\
    PLUGIN_NAME = "NoRegister"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_DESCRIPTION = "Missing register function"
"""

CRASH_ON_REGISTER_PLUGIN = """\
    PLUGIN_NAME = "CrashPlugin"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "Crashes during register"

    def register(api):
        raise RuntimeError("boom")
"""

SYNTAX_ERROR_PLUGIN = """\
    PLUGIN_NAME = "BadSyntax
    # Missing closing quote above
"""


# ---------------------------------------------------------------------------
# PluginAPI
# ---------------------------------------------------------------------------


class TestPluginAPI:
    def test_register_action(self):
        api = PluginAPI("test")

        def handler(**kw):
            return {"success": True}

        api.register_action("do_thing", handler, "Does a thing")
        assert len(api.actions) == 1
        assert api.actions[0].name == "do_thing"
        assert api.actions[0].handler is handler
        assert api.actions[0].plugin_name == "test"

    def test_register_action_non_callable_raises(self):
        api = PluginAPI("test")
        with pytest.raises(TypeError, match="callable"):
            api.register_action("bad", "not a function")

    def test_register_command(self):
        api = PluginAPI("test")

        def handler(text):
            return {"ok": True}

        api.register_command("say", handler, keywords=["hello", "hi"])
        assert len(api.commands) == 1
        assert api.commands[0].keywords == ["hello", "hi"]

    def test_register_command_non_callable_raises(self):
        api = PluginAPI("test")
        with pytest.raises(TypeError, match="callable"):
            api.register_command("bad", 42)

    def test_register_setting(self):
        api = PluginAPI("test")
        api.register_setting("volume", default=50, label="Volume level")
        assert len(api.settings) == 1
        assert api.settings[0].default == 50

    def test_get_engine(self):
        engine = object()
        api = PluginAPI("test", engine=engine)
        assert api.get_engine() is engine

    def test_get_config(self):
        cfg = {"key": "value"}
        api = PluginAPI("test", config=cfg)
        assert api.get_config() is cfg

    def test_log_calls_callback(self):
        messages = []
        api = PluginAPI("test", log_callback=messages.append)
        api.log("hello")
        assert len(messages) == 1
        assert "[plugin:test] hello" in messages[0]


# ---------------------------------------------------------------------------
# PluginLoader — loading
# ---------------------------------------------------------------------------


class TestPluginLoaderLoad:
    def test_load_valid_plugin(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        info = loader.load_plugin(tmp_path / "valid.py")
        assert info["loaded"] is True
        assert info["name"] == "TestPlugin"
        assert info["version"] == "1.0.0"

    def test_load_plugin_registers_actions(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "valid.py")
        actions = loader.get_all_actions()
        assert len(actions) == 1
        assert actions[0].name == "greet"

    def test_load_plugin_registers_commands(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "valid.py")
        commands = loader.get_all_commands()
        assert len(commands) == 1
        assert commands[0].keywords == ["hello"]

    def test_load_plugin_registers_settings(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "valid.py")
        settings = loader.get_all_settings()
        assert len(settings) == 1
        assert settings[0].key == "theme"
        assert settings[0].default == "dark"

    def test_load_missing_attr_raises(self, tmp_path):
        _write_plugin(tmp_path, "missing.py", MISSING_ATTR_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        with pytest.raises(AttributeError, match="missing required attributes"):
            loader.load_plugin(tmp_path / "missing.py")

    def test_load_missing_register_raises(self, tmp_path):
        _write_plugin(tmp_path, "noreg.py", MISSING_REGISTER_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        with pytest.raises(AttributeError, match="callable register"):
            loader.load_plugin(tmp_path / "noreg.py")

    def test_load_crash_on_register_raises(self, tmp_path):
        _write_plugin(tmp_path, "crash.py", CRASH_ON_REGISTER_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        with pytest.raises(RuntimeError, match="boom"):
            loader.load_plugin(tmp_path / "crash.py")

    def test_load_syntax_error_raises(self, tmp_path):
        _write_plugin(tmp_path, "syntax_err.py", SYNTAX_ERROR_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        with pytest.raises(SyntaxError):
            loader.load_plugin(tmp_path / "syntax_err.py")

    def test_load_nonexistent_raises(self, tmp_path):
        loader = PluginLoader(plugin_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load_plugin(tmp_path / "nope.py")


# ---------------------------------------------------------------------------
# PluginLoader — load_all
# ---------------------------------------------------------------------------


class TestPluginLoaderLoadAll:
    def test_load_all_empty_dir(self, tmp_path):
        loader = PluginLoader(plugin_dir=tmp_path)
        results = loader.load_all()
        assert results == []

    def test_load_all_mixed(self, tmp_path):
        _write_plugin(tmp_path, "good.py", VALID_PLUGIN)
        _write_plugin(tmp_path, "bad.py", MISSING_ATTR_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        results = loader.load_all()
        assert len(results) == 2
        loaded = [r for r in results if r.get("loaded")]
        failed = [r for r in results if not r.get("loaded")]
        assert len(loaded) == 1
        assert len(failed) == 1

    def test_load_all_creates_dir(self, tmp_path):
        plugin_dir = tmp_path / "new_plugins"
        loader = PluginLoader(plugin_dir=plugin_dir)
        results = loader.load_all()
        assert results == []
        assert plugin_dir.exists()


# ---------------------------------------------------------------------------
# PluginLoader — unload / reload
# ---------------------------------------------------------------------------


class TestPluginLoaderUnload:
    def test_unload_existing(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "valid.py")
        assert loader.unload_plugin("TestPlugin") is True
        assert len(loader) == 0

    def test_unload_nonexistent(self, tmp_path):
        loader = PluginLoader(plugin_dir=tmp_path)
        assert loader.unload_plugin("Nope") is False


class TestPluginLoaderReload:
    def test_reload_existing(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "valid.py")
        assert loader.reload_plugin("TestPlugin") is True

    def test_reload_nonexistent(self, tmp_path):
        loader = PluginLoader(plugin_dir=tmp_path)
        assert loader.reload_plugin("Nope") is False


# ---------------------------------------------------------------------------
# PluginLoader — querying
# ---------------------------------------------------------------------------


class TestPluginLoaderQuery:
    def test_list_plugins(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "valid.py")
        plugins = loader.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "TestPlugin"

    def test_get_action(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "valid.py")
        action = loader.get_action("greet")
        assert action is not None
        assert action.name == "greet"

    def test_get_action_not_found(self, tmp_path):
        loader = PluginLoader(plugin_dir=tmp_path)
        assert loader.get_action("nope") is None

    def test_len(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        assert len(loader) == 0
        loader.load_plugin(tmp_path / "valid.py")
        assert len(loader) == 1

    def test_contains(self, tmp_path):
        _write_plugin(tmp_path, "valid.py", VALID_PLUGIN)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(tmp_path / "valid.py")
        assert "TestPlugin" in loader
        assert "Nope" not in loader

    def test_repr(self, tmp_path):
        loader = PluginLoader(plugin_dir=tmp_path)
        r = repr(loader)
        assert "PluginLoader" in r
        assert "loaded=0" in r

    def test_plugin_dir_property(self, tmp_path):
        loader = PluginLoader(plugin_dir=tmp_path)
        assert loader.plugin_dir == tmp_path


# ---------------------------------------------------------------------------
# Required attrs constant
# ---------------------------------------------------------------------------


class TestConstants:
    def test_required_attrs(self):
        assert "PLUGIN_NAME" in REQUIRED_PLUGIN_ATTRS
        assert "PLUGIN_VERSION" in REQUIRED_PLUGIN_ATTRS
        assert "PLUGIN_DESCRIPTION" in REQUIRED_PLUGIN_ATTRS
