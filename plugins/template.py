"""
Sentinel Desktop — Template Plugin.

This file demonstrates how to author a plugin for Sentinel Desktop.

Plugin Authoring Guide
======================
Every plugin is a single ``*.py`` file placed in the ``plugins/`` directory.
Sentinel discovers plugins at startup via ``PluginLoader.load_all()`` and
validates them using **duck typing** — no base class or decorator required.

Required module-level attributes
---------------------------------
    PLUGIN_NAME         str   – Human-readable name (must be unique).
    PLUGIN_VERSION      str   – Semver string, e.g. "1.0.0".
    PLUGIN_DESCRIPTION  str   – One-line description.

Required function
-----------------
    register(api: PluginAPI) -> None
        Called once when the plugin is loaded.  Use the *api* object to
        register actions, commands, and settings:

        • api.register_action(name, handler, description)
        • api.register_command(name, handler, keywords)
        • api.register_setting(key, default, label)

        Helper methods on *api*:
        • api.get_engine()  – access the AgentEngine (may be None).
        • api.get_config()  – global configuration dict.
        • api.log(message)  – emit a plugin-scoped log message.

Error handling
--------------
If a plugin raises during ``register()`` it is skipped — the application
continues running normally.  Fix the error, then use
``PluginLoader.reload_plugin(name)`` to retry without restarting.
"""

# -- required metadata -------------------------------------------------------

PLUGIN_NAME = "Template Plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Starter template demonstrating the plugin interface."

# -- registration entry point ------------------------------------------------


def register(api):
    """Called by PluginLoader when the plugin is loaded."""

    api.log(f"Template Plugin v{PLUGIN_VERSION} registering...")

    def template_test_handler(**kwargs):
        """Dummy action handler for demonstration purposes."""
        api.log("template_test action invoked with kwargs: %s", kwargs)
        return {"success": True, "message": "Template test action executed."}

    api.register_action(
        name="template_test",
        handler=template_test_handler,
        description="A dummy action that always succeeds.  Use as a reference "
        "when building real plugin actions.",
    )

    api.register_setting(
        key="example_flag",
        default=False,
        label="Example boolean flag (does nothing)",
    )

    api.log("Template Plugin registered successfully.")
