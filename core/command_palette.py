"""Sentinel Desktop v2 — Command palette (Ctrl+K).

Fuzzy-searchable command palette matching Sentinel Override's ⌘K UX.
Provides quick access to: New Chat, Export Log, Clear Chat, Toggle Theme,
Open Settings, Resume Checkpoint, Toggle Approval Mode, Toggle Stealth,
Switch Desktop, Take Screenshot, Emergency Stop.

Implementation: popup toplevel with a search entry and filtered list.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gui.app import SentinelApp

logger = logging.getLogger(__name__)


class Command:
    """A single palette command."""

    def __init__(
        self,
        name: str,
        shortcut: str,
        category: str,
        handler: Callable[..., Any],
        keywords: list[str] | None = None,
    ) -> None:
        """Initialize a palette command.

        Args:
            name: Display name shown in the palette.
            shortcut: Keyboard shortcut string (e.g. ``"Ctrl+P"``).
            category: Category label for grouping (e.g. ``"Agent"``).
            handler: Callable invoked when the command is executed.
            keywords: Additional search terms for fuzzy matching.

        """
        self.name = name
        self.shortcut = shortcut
        self.category = category
        self.handler = handler
        self.keywords = keywords or []

    def matches(self, query: str) -> float:
        """Return match score 0-1 against query. Uses fuzzy matching."""
        if not query:
            return 0.5
        q = query.lower().strip()
        n = self.name.lower()

        # Exact match
        if q == n:
            return 1.0

        # Starts with
        if n.startswith(q):
            return 0.95

        # Contains
        if q in n:
            return 0.85

        # Keyword match
        for kw in self.keywords:
            if q in kw.lower():
                return 0.75

        # Fuzzy ratio
        ratio = SequenceMatcher(None, q, n).ratio()
        if ratio > 0.5:
            return ratio * 0.7

        return 0.0


class CommandPalette:
    """Manages the command registry and search logic.
    The actual popup UI is rendered by the GUI layer.
    """

    def __init__(self) -> None:
        """Initialize an empty command palette."""
        self._commands: list[Command] = []

    def register(
        self,
        name: str,
        shortcut: str,
        category: str,
        handler: Callable[..., Any],
        keywords: list[str] | None = None,
    ) -> None:
        """Register a command."""
        self._commands.append(Command(name, shortcut, category, handler, keywords))

    def search(self, query: str, limit: int = 10) -> list[tuple[Command, float]]:
        """Search commands by query. Returns list of (command, score) sorted by score desc."""
        scored = [(cmd, cmd.matches(query)) for cmd in self._commands]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(cmd, score) for cmd, score in scored if score > 0.1][:limit]

    def get_all(self) -> list[Command]:
        """Return all commands grouped by category."""
        return sorted(self._commands, key=lambda c: (c.category, c.name))

    def get_categories(self) -> list[str]:
        """Return unique categories."""
        return sorted(set(c.category for c in self._commands))

    def by_shortcut(self, key: str) -> Command | None:
        """Find command by keyboard shortcut."""
        for cmd in self._commands:
            if cmd.shortcut.lower() == key.lower():
                return cmd
        return None


# ── Default command registry ────────────────────────────────────────


def _register_chat_commands(p: CommandPalette, app: SentinelApp) -> None:
    """Register chat-related commands (new, clear, export)."""
    p.register(
        "New Chat",
        "Ctrl+N",
        "Chat",
        lambda: app.clear_chat(),
        keywords=["clear", "reset", "new", "start"],
    )
    p.register("Clear Chat", "Ctrl+L", "Chat", lambda: app.clear_chat(), keywords=["clear", "wipe"])
    p.register(
        "Export Conversation",
        "Ctrl+E",
        "Chat",
        lambda: app.export_chat(),
        keywords=["export", "save", "download"],
    )


def _register_agent_commands(p: CommandPalette, app: SentinelApp) -> None:
    """Register agent control commands (run, stop, emergency, approval, stealth, resume)."""
    p.register(
        "Run Agent",
        "Ctrl+Enter",
        "Agent",
        lambda: app.submit_goal(),
        keywords=["run", "start", "go", "execute"],
    )
    p.register(
        "Stop Agent",
        "Escape",
        "Agent",
        lambda: app.stop_agent(),
        keywords=["stop", "cancel", "abort", "halt"],
    )
    p.register(
        "Emergency Stop",
        "Ctrl+Shift+Esc",
        "Agent",
        lambda: app.emergency_stop(),
        keywords=["emergency", "panic", "kill"],
    )
    p.register(
        "Toggle Approval Mode",
        "Ctrl+Shift+A",
        "Agent",
        lambda: app.toggle_approval(),
        keywords=["approval", "gate", "approve", "confirm"],
    )
    p.register(
        "Toggle Stealth Input",
        "Ctrl+Shift+S",
        "Agent",
        lambda: app.toggle_stealth(),
        keywords=["stealth", "hidden", "background"],
    )
    p.register(
        "Resume from Checkpoint",
        "Ctrl+Shift+R",
        "Agent",
        lambda: app._do_resume_checkpoint(),
        keywords=["resume", "checkpoint", "continue", "restore"],
    )


def _register_desktop_commands(p: CommandPalette, app: SentinelApp) -> None:
    """Register desktop control commands (screenshot, virtual desktop, window list)."""
    p.register(
        "Take Screenshot",
        "Ctrl+Shift+X",
        "Desktop",
        lambda: app.take_screenshot(),
        keywords=["screenshot", "capture", "screen"],
    )
    p.register(
        "Switch Virtual Desktop",
        "Ctrl+Shift+D",
        "Desktop",
        lambda: app.switch_desktop(),
        keywords=["desktop", "virtual", "switch", "isolate"],
    )
    p.register(
        "List Windows",
        "",
        "Desktop",
        lambda: app.list_windows_cmd(),
        keywords=["windows", "list", "apps"],
    )


def _register_log_commands(p: CommandPalette, app: SentinelApp) -> None:
    """Register forensic log export commands (JSON, CSV)."""
    p.register(
        "Export Forensic Log (JSON)",
        "",
        "Logs",
        lambda: app.export_log_json(),
        keywords=["log", "forensic", "json", "export", "audit"],
    )
    p.register(
        "Export Forensic Log (CSV)",
        "",
        "Logs",
        lambda: app.export_log_csv(),
        keywords=["log", "forensic", "csv", "export", "audit"],
    )


def _register_settings_commands(p: CommandPalette, app: SentinelApp) -> None:
    """Register settings commands (open settings, detect models)."""
    p.register(
        "Open Settings",
        "Ctrl+,",
        "Settings",
        lambda: app.open_settings(),
        keywords=["settings", "config", "preferences", "provider"],
    )
    p.register(
        "Detect Models",
        "",
        "Settings",
        lambda: app.detect_models(),
        keywords=["detect", "models", "provider", "api"],
    )


def _register_theme_commands(p: CommandPalette, app: SentinelApp) -> None:
    """Register theme-switching commands — one command per available theme."""
    themes = [
        ("Midnight", ["midnight", "dark", "blue", "theme"]),
        ("Dark", ["dark", "theme"]),
        ("Matrix", ["matrix", "green", "hacker", "theme"]),
        ("Tron", ["tron", "cyan", "blue", "sci-fi", "theme"]),
        ("Cyberpunk", ["cyberpunk", "pink", "neon", "theme"]),
        ("Neon", ["neon", "purple", "theme"]),
        ("Terminal", ["terminal", "green", "monochrome", "theme"]),
        ("Blood", ["blood", "red", "dark", "theme"]),
        ("Ocean", ["ocean", "sea", "blue", "theme"]),
        ("Light", ["light", "bright", "white", "theme"]),
        ("Sunset", ["sunset", "orange", "warm", "theme"]),
        ("Paper", ["paper", "parchment", "warm", "light", "theme"]),
        ("Forest", ["forest", "green", "nature", "theme"]),
        ("Mono", ["mono", "grayscale", "minimal", "theme"]),
    ]
    for name, kws in themes:
        p.register(
            f"Theme: {name}",
            "",
            "Theme",
            lambda n=name.lower(): app.set_theme(n),
            keywords=kws,
        )


def _register_recorder_commands(p: CommandPalette, app: SentinelApp) -> None:
    """Register script recorder/playback commands (record, stop, run, library, powershell)."""
    p.register(
        "⏺ Start Recording",
        "Ctrl+Shift+R",
        "Recorder",
        lambda: _start_recording(app),
        keywords=["record", "capture", "start"],
    )
    p.register(
        "⏹ Stop Recording",
        "",
        "Recorder",
        lambda: _stop_recording(app),
        keywords=["record", "stop", "save"],
    )
    p.register(
        "▶ Run Script...",
        "Ctrl+Shift+P",
        "Recorder",
        lambda: _run_script_dialog(app),
        keywords=["script", "run", "play", "replay"],
    )
    p.register(
        "📋 Script Library",
        "",
        "Recorder",
        lambda: _show_script_library(app),
        keywords=["script", "library", "list", "browse"],
    )
    p.register(
        "💻 PowerShell Command...",
        "",
        "Recorder",
        lambda: _run_powershell_dialog(app),
        keywords=["powershell", "ps", "command", "shell"],
    )


def _register_it_quick_actions(p: CommandPalette, app: SentinelApp) -> None:
    """Register IT support quick-action commands (disk cleanup, network diag, etc.)."""
    scripts = [
        ("🔧 IT: Disk Cleanup", "disk_cleanup", ["disk", "cleanup", "clean", "maintenance"]),
        ("🔧 IT: Network Diagnostics", "network_diag", ["network", "ping", "dns", "diag", "tracert"]),
        ("🔧 IT: Service Restart...", "service_restart", ["service", "restart", "windows"]),
        ("🔧 IT: Event Log Errors", "event_log_errors", ["event", "log", "error", "viewer"]),
        ("🔧 IT: Temp File Cleanup", "temp_file_cleanup", ["temp", "cleanup", "files", "junk"]),
        ("🔧 IT: Software Inventory", "software_inventory", ["software", "inventory", "installed", "list"]),
        ("🔧 IT: System Info Export", "system_info_export", ["system", "info", "export", "msinfo"]),
        ("🔧 IT: Create Restore Point...", "restore_point_create", ["restore", "point", "backup", "system"]),
    ]
    for label, script_name, kws in scripts:
        p.register(
            label,
            "",
            "Quick Actions",
            lambda s=script_name: _run_it_script(app, s),
            keywords=kws,
        )


def create_default_palette(app: SentinelApp) -> CommandPalette:
    """Create and register all default commands for the Sentinel Desktop app.
    `app` is the SentinelApp instance (gui/app.py).
    """
    p = CommandPalette()
    _register_chat_commands(p, app)
    _register_agent_commands(p, app)
    _register_desktop_commands(p, app)
    _register_log_commands(p, app)
    _register_settings_commands(p, app)
    _register_theme_commands(p, app)
    _register_recorder_commands(p, app)
    _register_it_quick_actions(p, app)
    return p


# ── Command handler helpers ────────────────────────────────────────────


def _start_recording(app: Any) -> None:
    """Begin macro recording via the app's engine recorder."""
    try:
        if hasattr(app, "engine") and app.engine:
            app.engine.recorder.start_recording("")
            if hasattr(app, "recorder_panel"):
                app.recorder_panel._on_record_click()
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.error("start_recording failed: %s", exc)


def _stop_recording(app: Any) -> None:
    """Stop the current macro recording session."""
    try:
        if hasattr(app, "engine") and app.engine:
            app.engine.recorder.stop_recording()
            if hasattr(app, "recorder_panel"):
                app.recorder_panel._on_stop_click()
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.error("stop_recording failed: %s", exc)


def _run_script_dialog(app: Any) -> None:
    """Open the script replay dialog from the recorder panel."""
    try:
        if hasattr(app, "recorder_panel"):
            app.recorder_panel._on_play_click()
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.error("run_script_dialog failed: %s", exc)


def _show_script_library(app: Any) -> None:
    """Open the script library browser from the recorder panel."""
    try:
        if hasattr(app, "recorder_panel"):
            app.recorder_panel._on_library_click()
    except (OSError, AttributeError, RuntimeError) as exc:
        logger.error("show_script_library failed: %s", exc)


def _run_powershell_dialog(app: Any) -> None:
    """Prompt for a PowerShell command and execute it through the engine."""
    import tkinter.simpledialog as sd

    cmd = sd.askstring("PowerShell", "Enter PowerShell command:", parent=app.root)
    if cmd and hasattr(app, "engine") and app.engine:
        try:
            result = app.engine.powershell.run_command(cmd)
        except (OSError, RuntimeError, ValueError) as exc:
            result = None
            err_msg = str(exc)
            if hasattr(app, "chat_display"):
                app.root.after(
                    0,
                    lambda: app.chat_display.configure(
                        state="normal", text_color=app._t("text_primary", "#e6edf3")
                    ),
                )
                app.root.after(
                    0,
                    lambda: app.chat_display.insert("end", f"\n[PS] > {cmd}\nError: {err_msg}\n"),
                )
            return
        if hasattr(app, "chat_display"):
            app.root.after(
                0,
                lambda: app.chat_display.configure(
                    state="normal", text_color=app._t("text_primary", "#e6edf3")
                ),
            )
            app.root.after(
                0,
                lambda: app.chat_display.insert(
                    "end", f"\n[PS] > {cmd}\n{result.stdout or result.stderr}\n"
                ),
            )


def _run_it_script(app: Any, script_name: str) -> None:
    """Execute a named IT-support script template and display the result."""
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts" / "it_support"
    path = scripts_dir / f"{script_name}.json"
    if not path.exists():
        return
    if hasattr(app, "engine") and app.engine:
        try:
            from core.script_engine import ScriptEngine

            engine = ScriptEngine(app.engine.executor)
            result = engine.run_script(str(path))
        except (RuntimeError, OSError, ValueError, ImportError) as exc:
            err_msg = str(exc)
            if hasattr(app, "notes_label"):
                app.root.after(
                    0, lambda: app.notes_label.configure(text=f"Script error: {err_msg}")
                )
            return
        if hasattr(app, "notes_label"):
            status = (
                f"✅ {result.steps_completed}/{result.steps_total}"
                if result.success
                else f"❌ {result.error}"
            )
            app.root.after(0, lambda: app.notes_label.configure(text=f"Script: {status}"))
