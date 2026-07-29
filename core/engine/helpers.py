"""Pure helper functions extracted from the agent engine.

These are stateless utilities — JSON scanning and message cleaning — that
don't belong to any one subsystem.
"""

from __future__ import annotations

import json
from typing import Any


def _find_balanced_json_with_key(text: str, key: str) -> dict[str, Any] | None:
    """Scan *text* for a balanced ``{...}`` JSON object that contains *key*.

    Handles strings and escape characters so nested braces don't break the
    scanner the way the original regex did.
    """
    needle = f'"{key}"'
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                if needle in candidate:
                    try:
                        obj = json.loads(candidate)
                    except json.JSONDecodeError:
                        obj = None
                    if isinstance(obj, dict) and key in obj:
                        return obj
                start = -1
    return None


def _clean_messages_for_api(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of *messages* with internal ``_sentinel_*`` keys stripped.

    The engine attaches private markers like ``_sentinel_has_image`` so it can
    prune old screenshots; these must not appear in the JSON body sent to a
    provider's API.
    """
    cleaned = []
    for m in messages:
        if not isinstance(m, dict):
            cleaned.append(m)
            continue
        cleaned.append({k: v for k, v in m.items() if not (isinstance(k, str) and k.startswith("_sentinel_"))})
    return cleaned
