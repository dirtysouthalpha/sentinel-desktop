"""Gap tests for plugin_loader.py — same-path reload and name collision."""

from __future__ import annotations

import textwrap
from pathlib import Path

from core.plugin_loader import PluginLoader


def _write_plugin(tmp_path: Path, filename: str, content: str) -> Path:
    plugin_file = tmp_path / filename
    plugin_file.write_text(textwrap.dedent(content), encoding="utf-8")
    return plugin_file


VALID_PLUGIN_A = """\
    PLUGIN_NAME = "PluginA"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "First plugin"

    def register(api):
        api.register_action("action_a", lambda **kw: {"success": True}, "Action A")
"""

VALID_PLUGIN_B = """\
    PLUGIN_NAME = "PluginB"
    PLUGIN_VERSION = "2.0.0"
    PLUGIN_DESCRIPTION = "Second plugin"

    def register(api):
        api.register_action("action_b", lambda **kw: {"success": True}, "Action B")
"""


class TestLoadPluginSamePath:
    """load_plugin unloads existing plugin at same filepath before loading."""

    def test_reload_same_path_replaces_plugin(self, tmp_path: Path) -> None:
        path = _write_plugin(tmp_path, "plug.py", VALID_PLUGIN_A)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(path)
        assert "PluginA" in loader

        # Loading the same path again should replace (unload first, then load)
        loader.load_plugin(path)
        assert "PluginA" in loader
        assert len(loader) == 1

    def test_reload_same_path_updates_action(self, tmp_path: Path) -> None:
        path = _write_plugin(tmp_path, "plug.py", VALID_PLUGIN_A)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(path)

        # Overwrite with updated version
        updated = textwrap.dedent("""\
            PLUGIN_NAME = "PluginA"
            PLUGIN_VERSION = "2.0.0"
            PLUGIN_DESCRIPTION = "Updated plugin"

            def register(api):
                api.register_action("action_a_v2", lambda **kw: {"success": True}, "Action A v2")
        """)
        path.write_text(updated, encoding="utf-8")
        loader.load_plugin(path)

        actions = loader.get_all_actions()
        names = [a.name for a in actions]
        assert "action_a_v2" in names
        assert "action_a" not in names


class TestLoadPluginNameCollision:
    """load_plugin unloads existing plugin with same name before loading new one."""

    def test_name_collision_replaces_existing(self, tmp_path: Path) -> None:
        path_a = _write_plugin(tmp_path, "plug_a.py", VALID_PLUGIN_A)
        loader = PluginLoader(plugin_dir=tmp_path)
        loader.load_plugin(path_a)
        assert "PluginA" in loader

        # Create a different file with the same PLUGIN_NAME
        collision = textwrap.dedent("""\
            PLUGIN_NAME = "PluginA"
            PLUGIN_VERSION = "3.0.0"
            PLUGIN_DESCRIPTION = "Collision plugin"

            def register(api):
                api.register_action("collision_action", lambda **kw: {"success": True}, "Collision")
        """)
        path_b = _write_plugin(tmp_path, "plug_b.py", collision)
        loader.load_plugin(path_b)

        # Should still have only one plugin named "PluginA"
        assert "PluginA" in loader
        assert len(loader) == 1

        # The new action should be present
        actions = loader.get_all_actions()
        names = [a.name for a in actions]
        assert "collision_action" in names
