"""Sentinel Desktop v7.0 — Native Computer-Use Adapters.

First-class adapters for Anthropic's ``computer_20250124`` tool and OpenAI's
``computer-use-preview`` tool. When the active provider supports native
computer-use, the LLM uses its *own* screen-control loop instead of our
JSON action protocol. This is significantly more accurate for providers
that have been specifically trained for desktop control.

All other providers continue using the JSON action protocol unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Computer-use tool type identifiers
ANTHROPIC_COMPUTER_TOOL = {
    "type": "computer_20250124",
    "name": "computer",
    "display_width_px": 1920,
    "display_height_px": 1080,
}

OPENAI_COMPUTER_TOOL = {
    "type": "computer_use_preview",
    "display_width": 1920,
    "display_height": 1080,
    "environment": "windows",
}


def get_computer_use_type(provider: str) -> str | None:
    """Check if a provider supports native computer-use and return the type.

    Args:
        provider: Provider key (e.g. "anthropic", "openai").

    Returns:
        "anthropic", "openai", or None if the provider doesn't support it.
    """
    from core.provider_registry import PROVIDERS

    config = PROVIDERS.get(provider, {})
    return config.get("computer_use")


def build_anthropic_tools(
    standard_tools: list[dict[str, Any]] | None = None,
    display_width: int = 1920,
    display_height: int = 1080,
) -> list[dict[str, Any]]:
    """Build Anthropic tool list with the native computer tool.

    Anthropic's computer tool uses its own action format (not our JSON
    protocol). The model emits actions like ``{"type": "click", "x": 500,
    "y": 300}`` which we translate to our action format.

    Args:
        standard_tools: Our standard JSON-action tools (added as fallback).
        display_width: Display width in pixels.
        display_height: Display height in pixels.

    Returns:
        List of Anthropic-format tools.
    """
    tools: list[dict[str, Any]] = [
        {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": display_width,
            "display_height_px": display_height,
        },
    ]

    # Add standard tools as function tools (fallback for non-screen actions)
    if standard_tools:
        for tool in standard_tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                tools.append(
                    {
                        "type": "text_editor_20250124",
                        "name": func.get("name", "text_editor"),
                    }
                )
                break  # One text editor is enough

    return tools


def build_openai_tools(
    standard_tools: list[dict[str, Any]] | None = None,
    display_width: int = 1920,
    display_height: int = 1080,
) -> list[dict[str, Any]]:
    """Build OpenAI tool list with the native computer tool.

    OpenAI's computer-use-preview tool uses its own action format.
    The model emits actions like ``{"type": "click", "x": 500, "y": 300}``.

    Args:
        standard_tools: Our standard JSON-action tools (added as fallback).
        display_width: Display width in pixels.
        display_height: Display height in pixels.

    Returns:
        List of OpenAI-format tools.
    """
    tools: list[dict[str, Any]] = [
        {
            "type": "computer_use_preview",
            "display_width": display_width,
            "display_height": display_height,
            "environment": "windows",
        },
    ]

    # Keep standard tools for non-screen actions (type_text, etc.)
    if standard_tools:
        tools.extend(standard_tools)

    return tools


def translate_anthropic_action(response_block: dict[str, Any]) -> dict[str, Any] | None:
    """Translate an Anthropic computer tool response to our action format.

    Anthropic returns actions like:
        {"type": "tool_use", "name": "computer", "input": {"action": "click", ...}}

    We convert to our standard action dict.

    Args:
        response_block: A single content block from Anthropic's response.

    Returns:
        Our action dict, or None if not a computer tool action.
    """
    if response_block.get("type") != "tool_use":
        return None
    if response_block.get("name") != "computer":
        return None

    inp = response_block.get("input", {})
    action_type = inp.get("action", "").lower()
    _coord = inp.get("coordinate", [0, 0])
    _cx, _cy = _coord[0], _coord[1]
    _start = inp.get("start_coordinate", [0, 0])
    _sx, _sy = _start[0], _start[1]

    action_map: dict[str, dict[str, Any]] = {
        "click": {"action": "click", "x": _cx, "y": _cy},
        "left_click": {"action": "click", "x": _cx, "y": _cy},
        "right_click": {"action": "right_click", "x": _cx, "y": _cy},
        "double_click": {"action": "double_click", "x": _cx, "y": _cy},
        "middle_click": {"action": "click", "x": _cx, "y": _cy, "button": "middle"},
        "type": {"action": "type_text", "text": inp.get("text", "")},
        "key": {"action": "hotkey", "keys": _parse_anthropic_key(inp.get("text", ""))},
        "screenshot": {"action": "screenshot"},
        "mouse_move": {"action": "mouse_move", "x": _cx, "y": _cy},
        "left_click_drag": {
            "action": "drag",
            "from_x": _sx,
            "from_y": _sy,
            "to_x": _cx,
            "to_y": _cy,
        },
        "scroll": {
            "action": "scroll",
            "amount": _parse_scroll_direction(inp.get("direction", "down"), inp.get("amount", 1)),
        },
        "wait": {"action": "wait", "seconds": 2},
    }

    action = action_map.get(action_type)
    if action:
        logger.debug("Translated Anthropic action '%s' → %s", action_type, action["action"])
        return action

    # Unknown action — pass through as-is
    logger.debug("Unknown Anthropic computer action: %s", action_type)
    return {"action": action_type, **inp}


def translate_openai_action(response_item: dict[str, Any]) -> dict[str, Any] | None:
    """Translate an OpenAI computer-use response to our action format.

    OpenAI returns actions in the tool_calls array with:
        {"function": {"name": "computer_use_preview", "arguments": "{\"action\": \"click\", ...}"}}

    Args:
        response_item: A tool call item from OpenAI's response.

    Returns:
        Our action dict, or None if not a computer-use action.
    """
    import json

    func = response_item.get("function", {})
    name = func.get("name", "")

    # Check if this is a computer-use tool call vs a standard function call
    if name != "computer_use_preview":
        # Standard function call — already in our format
        args = func.get("arguments", "{}")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return None
        return {"action": name, **args}

    args = func.get("arguments", "{}")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return None

    action_type = args.get("action", args.get("type", "")).lower()

    # Map OpenAI computer actions to our format
    coordinate = args.get("coordinate", args.get("x", [0, 0]))
    if isinstance(coordinate, list) and len(coordinate) >= 2:
        x, y = coordinate[0], coordinate[1]
    elif isinstance(coordinate, dict):
        x, y = coordinate.get("x", 0), coordinate.get("y", 0)
    else:
        x, y = 0, 0

    action_map: dict[str, dict[str, Any]] = {
        "click": {"action": "click", "x": x, "y": y},
        "left_click": {"action": "click", "x": x, "y": y},
        "right_click": {"action": "right_click", "x": x, "y": y},
        "double_click": {"action": "double_click", "x": x, "y": y},
        "type": {"action": "type_text", "text": args.get("text", "")},
        "keypress": {"action": "hotkey", "keys": _parse_anthropic_key(args.get("text", ""))},
        "screenshot": {"action": "screenshot"},
        "mouse_move": {"action": "mouse_move", "x": x, "y": y},
        "drag": {
            "action": "drag",
            "from_x": (
                args.get("start_coordinate", [0, 0])[0]
                if isinstance(args.get("start_coordinate"), list)
                else 0
            ),
            "from_y": (
                args.get("start_coordinate", [0, 0])[1]
                if isinstance(args.get("start_coordinate"), list)
                else 0
            ),
            "to_x": x,
            "to_y": y,
        },
        "scroll": {
            "action": "scroll",
            "amount": _parse_scroll_direction(
                args.get("direction", "down"),
                args.get("amount", 1),
            ),
        },
        "wait": {"action": "wait", "seconds": 2},
    }

    action = action_map.get(action_type)
    if action:
        logger.debug("Translated OpenAI action '%s' → %s", action_type, action["action"])
        return action

    return {"action": action_type, **args}


def _parse_anthropic_key(key_text: str) -> list[str]:
    """Parse Anthropic key text to a list of key names for our hotkey action.

    Anthropic uses format like "ctrl+c", "alt+f4", "enter", etc.
    """
    if not key_text:
        return ["enter"]

    # Split on + for combos
    parts = key_text.replace(" ", "").split("+")
    # Map common key names
    key_map = {
        "return": "enter",
        "win": "win",
        "windows": "win",
        "cmd": "command",
        "command": "command",
    }
    return [key_map.get(p.lower(), p.lower()) for p in parts]


def _parse_scroll_direction(direction: str, amount: int = 1) -> int:
    """Convert scroll direction + amount to our scroll amount (negative = up)."""
    if direction == "up":
        return -amount
    return amount
