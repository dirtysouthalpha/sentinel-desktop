"""Sentinel Desktop v8.0 — Dual-mode detection.

Analyzes user goals and LLM action outputs to determine whether the agent
should operate in browser DOM mode (web) or native vision mode (desktop).

The detector uses keyword matching and URL patterns to classify intent.
It's intentionally simple — a senior engineer wouldn't overcomplicate this.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


class InteractionMode(Enum):
    """Agent interaction mode."""

    NATIVE = "native"
    WEB = "web"


# Keywords that strongly suggest web automation intent.
_WEB_KEYWORDS: frozenset[str] = frozenset(
    {
        "website",
        "webpage",
        "web page",
        "web app",
        "web ui",
        "portal",
        "browser",
        "firefox",
        "chrome",
        "url",
        "http://",
        "https://",
        "firewall ui",
        "router config",
        "switch management",
        "sonicwall",
        "fortigate",
        "fortinet",
        "unifi",
        "meraki",
        "mikrotik",
        "pfsense",
        "opnsense",
        "juniper",
        "palo alto",
        "ninjaone",
        "connectwise",
        "screenconnect",
        "it glue",
        "admin panel",
        "dashboard",
        "web interface",
        "web console",
        "login page",
        "web portal",
        "intranet",
    }
)

# URL patterns — if a goal contains something that looks like a URL, it's web.
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+\.[^\s<>\"']+|"
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|"
    r"localhost:\d+",
)

# Actions that are exclusively web actions.
_WEB_ONLY_ACTIONS: frozenset[str] = frozenset(
    {
        "web_open",
        "web_click",
        "web_type",
        "web_read",
        "web_extract",
        "web_wait_for",
        "web_screenshot",
        "web_eval_js",
        "web_download",
        "web_upload",
        "web_tabs",
    }
)


def detect_mode_from_goal(goal: str) -> InteractionMode:
    """Detect whether a goal targets a web app or native desktop.

    Args:
        goal: User's natural language goal text.

    Returns:
        InteractionMode.WEB if the goal is web-targeted,
        InteractionMode.NATIVE otherwise.
    """
    goal_lower = goal.lower()

    # URL patterns are a strong signal
    if _URL_PATTERN.search(goal_lower):
        return InteractionMode.WEB

    # Keyword matching
    for keyword in _WEB_KEYWORDS:
        if keyword in goal_lower:
            return InteractionMode.WEB

    return InteractionMode.NATIVE


def detect_mode_from_action(action: dict[str, Any]) -> InteractionMode:
    """Detect mode from a parsed action dict.

    Args:
        action: Action dict with at least an 'action' key.

    Returns:
        InteractionMode.WEB if the action is a web action,
        InteractionMode.NATIVE otherwise.
    """
    action_name = action.get("action", "").lower()
    if action_name in _WEB_ONLY_ACTIONS:
        return InteractionMode.WEB
    return InteractionMode.NATIVE


def classify_handoff(
    current_mode: InteractionMode,
    action: dict[str, Any],
) -> InteractionMode | None:
    """Determine if an action requires a mode handoff.

    Returns:
        New InteractionMode if a handoff is needed, None if no handoff.

    Example handoffs:
        - WEB → NATIVE: web_download completes, next action is open_app
        - NATIVE → WEB: user goal shifts to "check the firewall portal"
    """
    action_mode = detect_mode_from_action(action)

    if action_mode != current_mode:
        return action_mode

    # Special case: web_download followed by a file action → native handoff
    # This is handled by the engine observing the action sequence.
    return None
