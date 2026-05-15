"""
Sentinel Desktop v2 — Plugin Loader.

Discovers, loads, and manages .py plugin files from a configurable plugin
directory.  Each plugin is a regular Python module that exposes four module-
level attributes and one function via duck typing:

    PLUGIN_NAME         str   — human-readable plugin name
    PLUGIN_VERSION      str   — semver string, e.g. "1.0.0"
    PLUGIN_DESCRIPTION  str   — one-line description
    register(api)       func  — called once at load; receives a PluginAPI

Failed plugins are captured but never crash the host application.  All public
methods are thread-safe (guarded by a threading.Lock).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required duck-typed attributes every plugin must define
# ---------------------------------------------------------------------------
REQUIRED_PLUGIN_ATTRS = ("PLUGIN_NAME", "PLUGIN_VERSION", "PLUGIN_DESCRIPTION")

# ---------------------------------------------------------------------------
# Data holders for registered actions / commands / settings
# ---------------------------------------------------------------------------


@dataclass
class PluginAction:
    """An action registered by a plugin."""

    name: str
    handler: Callable[..., Any]
    description: str
    plugin_name: str


@dataclass
class PluginCommand:
    """A voice / command-palette command registered by a plugin."""

    name: str
    handler: Callable[..., Any]
    keywords: list[str]
    plugin_name: str


@dataclass
class PluginSetting:
    """A user-configurable setting registered by a plugin."""

    key: str
    default: Any
    label: str
    plugin_name: str


# ---------------------------------------------------------------------------
# PluginAPI — passed into each plugin's ``register(api)`` call
# ---------------------------------------------------------------------------


class PluginAPI:
    """Facade that plugins use to hook into Sentinel Desktop.

    Instances are created internally by *PluginLoader* and should not be
    instantiated by hand.

    Attributes
    ----------
    actions : list[PluginAction]
        Actions registered by the owning plugin.
    commands : list[PluginCommand]
        Commands registered by the owning plugin.
    settings : list[PluginSetting]
        Settings registered by the owning plugin.
    """

    def __init__(
        self,
        plugin_name: str,
        engine: Any = None,
        config: dict[str, Any] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._engine = engine
        self._config = config or {}
        self._log_callback = log_callback or logger.info

        self.actions: list[PluginAction] = []
        self.commands: list[PluginCommand] = []
        self.settings: list[PluginSetting] = []

    # -- registration helpers ------------------------------------------------

    def register_action(
        self, name: str, handler: Callable[..., Any], description: str = ""
    ) -> None:
        """Register a named action that the agent can invoke.

        Parameters
        ----------
        name : str
            Unique action identifier (scoped to this plugin).
        handler : callable
            ``handler(**kwargs) -> dict`` — receives action parameters and
            must return a dict with at least ``{"success": bool}``.
        description : str
            Human-readable description shown in the action catalogue.
        """
        if not callable(handler):
            raise TypeError(f"handler for action '{name}' must be callable")
        self.actions.append(
            PluginAction(
                name=name,
                handler=handler,
                description=description,
                plugin_name=self._plugin_name,
            )
        )

    def register_command(
        self, name: str, handler: Callable[..., Any], keywords: Sequence[str] | None = None
    ) -> None:
        """Register a command-palette / voice command.

        Parameters
        ----------
        name : str
            Unique command identifier.
        handler : callable
            ``handler(text: str) -> dict``
        keywords : list[str]
            Words/phrases that trigger this command.
        """
        if not callable(handler):
            raise TypeError(f"handler for command '{name}' must be callable")
        self.commands.append(
            PluginCommand(
                name=name,
                handler=handler,
                keywords=list(keywords or []),
                plugin_name=self._plugin_name,
            )
        )

    def register_setting(self, key: str, default: Any = None, label: str = "") -> None:
        """Declare a user-configurable setting for this plugin.

        Parameters
        ----------
        key : str
            Unique setting key (scoped to plugin).
        default : Any
            Default value when the user hasn't configured one.
        label : str
            Human-readable label for the settings UI.
        """
        self.settings.append(
            PluginSetting(
                key=key,
                default=default,
                label=label,
                plugin_name=self._plugin_name,
            )
        )

    # -- accessor helpers ----------------------------------------------------

    def get_engine(self) -> Any:
        """Return the current :class:`AgentEngine` instance, if available."""
        return self._engine

    def get_config(self) -> dict[str, Any]:
        """Return the global configuration dict."""
        return self._config

    def log(self, message: str) -> None:
        """Emit a log message attributed to this plugin."""
        self._log_callback(f"[plugin:{self._plugin_name}] {message}")


# ---------------------------------------------------------------------------
# Internal per-plugin bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class _LoadedPlugin:
    """Internal state for a single loaded plugin."""

    name: str
    version: str
    description: str
    filepath: str
    module: ModuleType
    api: PluginAPI
    error: str | None = None


# ---------------------------------------------------------------------------
# PluginLoader — the main public interface
# ---------------------------------------------------------------------------


class PluginLoader:
    """Discover, load, and manage Sentinel Desktop plugins.

    Parameters
    ----------
    plugin_dir : str or Path
        Directory containing ``*.py`` plugin modules.  Created on first
        :meth:`load_all` if it doesn't exist.
    engine : object, optional
        The :class:`AgentEngine` instance to expose to plugins via
        :meth:`PluginAPI.get_engine`.
    config : dict, optional
        Global configuration dict forwarded to plugins.
    """

    def __init__(
        self,
        plugin_dir: str | Path = "plugins",
        engine: Any = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._plugin_dir = Path(plugin_dir)
        self._engine = engine
        self._config = config or {}
        self._lock = threading.Lock()
        # name -> _LoadedPlugin
        self._plugins: dict[str, _LoadedPlugin] = {}

    # -- public helpers ------------------------------------------------------

    @property
    def plugin_dir(self) -> Path:
        """Return the resolved plugin directory path."""
        return self._plugin_dir

    # -- loading ------------------------------------------------------------

    def load_all(self) -> list[dict[str, Any]]:
        """Scan *plugin_dir* and load every ``*.py`` file found.

        Returns a list of info dicts (one per plugin).  Plugins that fail to
        load are included with ``"loaded": False`` and an ``"error"`` key.

        Thread-safe.
        """
        results: list[dict[str, Any]] = []
        self._ensure_plugin_dir()

        py_files = sorted(self._plugin_dir.glob("*.py"))
        if not py_files:
            logger.debug("No .py files found in %s", self._plugin_dir)
            return results

        for filepath in py_files:
            try:
                info = self.load_plugin(filepath)
                results.append(info)
            except Exception as exc:
                logger.error("Failed to load plugin %s: %s", filepath, exc)
                results.append(
                    {
                        "name": filepath.stem,
                        "loaded": False,
                        "error": str(exc),
                        "filepath": str(filepath),
                    }
                )

        return results

    def load_plugin(self, filepath: str | Path) -> dict[str, Any]:
        """Load a single plugin from *filepath*.

        Returns an info dict with ``"loaded": True`` on success.  Raises
        on critical errors so the caller can decide how to handle them.

        Thread-safe.
        """
        filepath = Path(filepath).resolve()
        module_name = f"sentinel_plugin_{filepath.stem}"

        with self._lock:
            # If already loaded under the same path, unload first.
            for existing in self._plugins.values():
                if Path(existing.filepath) == filepath:
                    self._unload_unlocked(existing.name)

            # --- import the module ---
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create import spec for {filepath}")

            module = importlib.util.module_from_spec(spec)

            # Stash in sys.modules so relative / absolute imports inside the
            # plugin can resolve the package name if needed.
            sys.modules[module_name] = module

            try:
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except Exception as exc:
                logger.debug("Plugin module exec failed for %s: %s", module_name, exc)
                # Clean up the broken module reference.
                sys.modules.pop(module_name, None)
                raise

            # --- duck-type validation ---
            missing = [a for a in REQUIRED_PLUGIN_ATTRS if not hasattr(module, a)]
            if missing:
                sys.modules.pop(module_name, None)
                raise AttributeError(
                    f"Plugin {filepath.name} is missing required attributes: " + ", ".join(missing)
                )

            if not hasattr(module, "register") or not callable(module.register):
                sys.modules.pop(module_name, None)
                raise AttributeError(f"Plugin {filepath.name} must define a callable register(api)")

            plugin_name = module.PLUGIN_NAME
            plugin_version = module.PLUGIN_VERSION
            plugin_description = module.PLUGIN_DESCRIPTION

            # Check for name collision with an already-loaded plugin
            if plugin_name in self._plugins:
                self._unload_unlocked(plugin_name)

            # --- build API & call register() ---
            api = PluginAPI(
                plugin_name=plugin_name,
                engine=self._engine,
                config=self._config,
            )

            try:
                module.register(api)
            except Exception as exc:
                logger.debug("Plugin register() failed for %s: %s", module_name, exc)
                sys.modules.pop(module_name, None)
                raise

            loaded = _LoadedPlugin(
                name=plugin_name,
                version=plugin_version,
                description=plugin_description,
                filepath=str(filepath),
                module=module,
                api=api,
            )
            self._plugins[plugin_name] = loaded

            logger.info(
                "Loaded plugin %s v%s from %s",
                plugin_name,
                plugin_version,
                filepath.name,
            )

            return self._plugin_info(loaded, loaded=True)

    # -- unloading ----------------------------------------------------------

    def unload_plugin(self, name: str) -> bool:
        """Unload a previously loaded plugin by name.

        Returns ``True`` if the plugin was found and removed, ``False``
        otherwise.  Thread-safe.
        """
        with self._lock:
            if name not in self._plugins:
                logger.warning("unload_plugin: '%s' not found", name)
                return False
            self._unload_unlocked(name)
            return True

    def _unload_unlocked(self, name: str) -> None:
        """Internal unload — caller must hold ``self._lock``."""
        loaded = self._plugins.pop(name, None)
        if loaded is None:
            return

        # Remove the module from sys.modules so a future reload gets a fresh
        # import.
        module_name = loaded.module.__name__
        sys.modules.pop(module_name, None)

        logger.info("Unloaded plugin '%s'", name)

    # -- reloading ----------------------------------------------------------

    def reload_plugin(self, name: str) -> bool:
        """Reload a plugin by name (unload then load from disk).

        Returns ``True`` on success, ``False`` if the plugin was not found or
        failed to reload.  Thread-safe.
        """
        with self._lock:
            loaded = self._plugins.get(name)
            if loaded is None:
                logger.warning("reload_plugin: '%s' not found", name)
                return False

            filepath = loaded.filepath
            self._unload_unlocked(name)

        # Load outside the lock — load_plugin takes the lock itself.
        try:
            info = self.load_plugin(filepath)
            return info.get("loaded", False)
        except Exception as exc:
            logger.error("Failed to reload plugin '%s': %s", name, exc)
            return False

    # -- querying -----------------------------------------------------------

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return info dicts for all currently loaded plugins.

        Each dict contains: name, version, description, filepath, loaded,
        actions, commands, settings.  Thread-safe.
        """
        with self._lock:
            return [self._plugin_info(p, loaded=True) for p in self._plugins.values()]

    def get_action(self, name: str) -> PluginAction | None:
        """Look up a registered action by its scoped name across all plugins."""
        with self._lock:
            for loaded in self._plugins.values():
                for action in loaded.api.actions:
                    if action.name == name:
                        return action
        return None

    def get_all_actions(self) -> list[PluginAction]:
        """Return every registered action from every loaded plugin."""
        with self._lock:
            actions: list[PluginAction] = []
            for loaded in self._plugins.values():
                actions.extend(loaded.api.actions)
            return actions

    def get_all_commands(self) -> list[PluginCommand]:
        """Return every registered command from every loaded plugin."""
        with self._lock:
            commands: list[PluginCommand] = []
            for loaded in self._plugins.values():
                commands.extend(loaded.api.commands)
            return commands

    def get_all_settings(self) -> list[PluginSetting]:
        """Return every registered setting from every loaded plugin."""
        with self._lock:
            settings: list[PluginSetting] = []
            for loaded in self._plugins.values():
                settings.extend(loaded.api.settings)
            return settings

    # -- internals ----------------------------------------------------------

    def _ensure_plugin_dir(self) -> None:
        """Create the plugin directory if it doesn't exist."""
        self._plugin_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _plugin_info(plugin: _LoadedPlugin, *, loaded: bool) -> dict[str, Any]:
        """Serialise a ``_LoadedPlugin`` into a public-facing dict."""
        return {
            "name": plugin.name,
            "version": plugin.version,
            "description": plugin.description,
            "filepath": plugin.filepath,
            "loaded": loaded,
            "error": plugin.error,
            "actions": [{"name": a.name, "description": a.description} for a in plugin.api.actions],
            "commands": [{"name": c.name, "keywords": c.keywords} for c in plugin.api.commands],
            "settings": [
                {"key": s.key, "default": s.default, "label": s.label} for s in plugin.api.settings
            ],
        }

    # -- dunder helpers -----------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._plugins

    def __repr__(self) -> str:
        return f"PluginLoader(plugin_dir={self._plugin_dir!r}, loaded={len(self._plugins)})"
