"""
Sentinel Desktop v30.0.0 - NL Workflow Builder.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

ACTION_MAP = {
    "open": "launch", "launch": "launch", "start": "launch",
    "click": "click", "press": "key_press", "type": "type_text",
    "enter": "key_press", "wait": "wait", "screenshot": "screenshot",
    "scroll": "scroll", "close": "close_window", "copy": "copy",
    "paste": "paste", "search": "search", "navigate": "navigate",
}

SEPARATORS = [",", ";", " then ", " after that ", " next ", ". "]

def _split_steps(description):
    parts = [description]
    for sep in SEPARATORS:
        new_parts = []
        for p in parts:
            new_parts.extend(p.split(sep))
        parts = new_parts
    return [p.strip() for p in parts if p.strip()]

def _parse_step(text):
    words = text.lower().split()
    if not words:
        return None
    action = None
    action_idx = -1
    for i, w in enumerate(words):
        if w in ACTION_MAP:
            action = ACTION_MAP[w]
            action_idx = i
            break
    if not action:
        return None
    target = " ".join(words[action_idx + 1:]) if action_idx + 1 < len(words) else ""
    if action == "key_press":
        km = {"enter": "Return", "escape": "Escape", "tab": "Tab", "space": "space"}
        target = km.get(target.lower(), target)
    return {"action": action, "target": target, "description": text, "delay_after": 0.5}

def generate_workflow(description):
    if not description or not description.strip():
        return {"success": False, "error": "Description must not be empty"}
    if len(description) > 5000:
        return {"success": False, "error": "Description too long"}
    parts = _split_steps(description)
    steps = []
    for p in parts:
        s = _parse_step(p)
        if s:
            steps.append(s)
    if not steps:
        return {"success": False, "error": "Could not extract any actions"}
    return {"success": True, "name": description[:60], "description": description, "steps": steps, "step_count": len(steps), "generated": True}
