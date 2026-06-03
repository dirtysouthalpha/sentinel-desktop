"""Sentinel Desktop — Smart app launcher.

``smart_open(name)`` is what the agent should call instead of ``open_app``
99% of the time:

1. Looks up *name* against a friendly-name → (window-title, launch-command)
   table covering most common Windows apps.
2. Checks every visible window — if a match already exists, just focuses it.
   No more "open Outlook" launching a second Outlook process when one's
   already running.
3. Falls through to ``cmd /c start <command>``, which goes through Windows'
   PATH resolution AND its URI protocol handlers. That's why ``outlook``
   works here even when ``outlook.exe`` isn't on PATH (the ``outlook:``
   protocol resolves via the Office installation).

Unknown names fall back to using the name itself as both the title hint and
the launch command, so ``smart_open("steam")`` does the right thing without
needing an explicit alias.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from typing import Any

from core import window_manager as wm

logger = logging.getLogger(__name__)


# friendly name → {title: window-title-substring, launch: command-or-protocol}
APP_ALIASES: dict[str, dict[str, str]] = {
    # Microsoft Office
    "outlook": {"title": "Outlook", "launch": "outlook"},
    "excel": {"title": "Excel", "launch": "excel"},
    "word": {"title": "Word", "launch": "winword"},
    "powerpoint": {"title": "PowerPoint", "launch": "powerpnt"},
    "onenote": {"title": "OneNote", "launch": "onenote"},
    "teams": {"title": "Teams", "launch": "msteams"},
    # Browsers
    "chrome": {"title": "Chrome", "launch": "chrome"},
    "edge": {"title": "Edge", "launch": "msedge"},
    "firefox": {"title": "Firefox", "launch": "firefox"},
    "brave": {"title": "Brave", "launch": "brave"},
    # System
    "explorer": {"title": "File Explorer", "launch": "explorer"},
    "file explorer": {"title": "File Explorer", "launch": "explorer"},
    "notepad": {"title": "Notepad", "launch": "notepad"},
    "notepad++": {"title": "Notepad++", "launch": "notepad++"},
    "calc": {"title": "Calculator", "launch": "calc"},
    "calculator": {"title": "Calculator", "launch": "calc"},
    "paint": {"title": "Paint", "launch": "mspaint"},
    "powershell": {"title": "PowerShell", "launch": "powershell"},
    "cmd": {"title": "Command Prompt", "launch": "cmd"},
    "terminal": {"title": "Terminal", "launch": "wt"},
    "task manager": {"title": "Task Manager", "launch": "taskmgr"},
    "settings": {"title": "Settings", "launch": "ms-settings:"},
    "control panel": {"title": "Control Panel", "launch": "control"},
    # Dev tools
    "vscode": {"title": "Visual Studio Code", "launch": "code"},
    "code": {"title": "Visual Studio Code", "launch": "code"},
    "visual studio": {"title": "Visual Studio", "launch": "devenv"},
    # Communication
    "slack": {"title": "Slack", "launch": "slack"},
    "discord": {"title": "Discord", "launch": "discord"},
    "zoom": {"title": "Zoom", "launch": "zoom"},
    # Misc
    "spotify": {"title": "Spotify", "launch": "spotify"},
    "steam": {"title": "Steam", "launch": "steam"},
}


# Conservative whitelist for unknown app names. Curated APP_ALIASES values
# bypass this check (they're trusted at definition time and include URI
# protocols like ``ms-settings:``). Anything matching this pattern is safe
# to splice into ``cmd /c start "" <token>`` because Windows command-line
# parsing treats it as a single non-metacharacter argument.
_UNKNOWN_NAME_RE = re.compile(r"^[A-Za-z0-9._+-]+$")


def _is_safe_launch_token(token: str) -> bool:
    """Return True if *token* is safe to pass to ``cmd /c start`` unescaped."""
    return bool(token) and bool(_UNKNOWN_NAME_RE.fullmatch(token))


def _try_focus_existing_window(window_title: str) -> dict[str, Any] | None:
    """Try to focus an existing window by title.

    Args:
        window_title: The title of the window to focus.

    Returns:
        Result dict if focusing succeeded, None otherwise.

    """
    try:
        ok = wm.focus_window(window_title)
    except (OSError, RuntimeError) as exc:
        logger.warning("smart_open focus failed for %r: %s", window_title, exc)
        return None

    if ok:
        return {
            "success": True,
            "output": f"Already open — focused window {window_title!r}",
            "focused": True,
            "window_title": window_title,
        }
    return None


def _launch_new_app(name: str, launch_cmd: str) -> dict[str, Any]:
    """Launch a new application instance.

    Args:
        name: The friendly name of the app.
        launch_cmd: The command to launch the app.

    Returns:
        Result dict with launch status.

    """
    import platform
    cmd_exe = shutil.which("cmd") if platform.system() == "Windows" else "cmd"
    if not cmd_exe:
        return {
            "success": False,
            "output": "cmd.exe not found on Windows",
            "error": "cmd_not_found",
        }
    try:
        subprocess.Popen(  # noqa: S603 - Intentional process execution for desktop automation
            [cmd_exe, "/c", "start", "", launch_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        return {
            "success": True,
            "output": f"Launched {name!r} via 'start {launch_cmd}'",
            "focused": False,
            "command": launch_cmd,
        }
    except (OSError, subprocess.SubprocessError, FileNotFoundError) as exc:
        return {
            "success": False,
            "output": f"Failed to launch {name!r}: {exc}",
            "error": "launch_failed",
        }


def smart_open(name: str) -> dict[str, Any]:
    """Focus or launch the named app. Returns ``{success, output, ...}``.

    The result dict is shaped to match what ActionExecutor handlers return.
    """
    if not name or not name.strip():
        return {"success": False, "output": "smart_open needs an app name", "error": "empty_name"}

    resolved = _resolve_app(name)
    if isinstance(resolved, dict):
        return resolved  # error result from validation
    title_hint, launch_cmd = resolved

    try:
        existing = _find_existing(title_hint)
    except (OSError, RuntimeError) as exc:
        logger.debug("smart_open list_windows failed: %s", exc)
        existing = None

    if existing:
        result = _try_focus_existing_window(existing)
        if result:
            return result

    return _launch_new_app(name, launch_cmd)


def _resolve_app(name: str) -> tuple[str, str] | dict[str, Any]:
    """Resolve *name* to (title_hint, launch_cmd), or return an error dict."""
    key = re.sub(r"\.(exe|lnk|url)$", "", name.strip().lower())
    alias = APP_ALIASES.get(key)
    if alias is not None:
        return alias["title"], alias["launch"]
    if not _is_safe_launch_token(key):
        return {
            "success": False,
            "output": f"refusing to launch {name!r}: contains shell metacharacters",
            "error": "unsafe_app_name",
        }
    return key, key


def _find_existing(title_hint: str) -> str | None:
    """Return the title of an open window matching *title_hint*, or None."""
    needle = title_hint.lower()
    if not needle:
        return None
    try:
        windows = wm.list_windows()
    except (OSError, RuntimeError) as exc:
        logger.debug("list_windows failed: %s", exc)
        return None
    best: str | None = None
    for w in windows:
        title = w.get("title") or ""
        if not title:
            continue
        if needle in title.lower():
            # Prefer a focused window if there are multiple matches.
            if w.get("is_focused"):
                return title
            best = title
    return best
