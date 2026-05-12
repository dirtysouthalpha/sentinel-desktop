"""
Sentinel Desktop v3.0 — Action Recorder

Records user / agent actions into replayable Script objects that can be
serialized to JSON, parameterized, and shared.

Thread-safe: all mutable state is guarded by a threading.Lock so the
recorder can safely be called from the agent loop thread while the UI
reads state from the main thread.
"""

import base64
import json
import time
import hashlib
import os
import glob
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Script data model
# ---------------------------------------------------------------------------

class Script:
    """Represents a recorded (or loaded) automation script."""

    def __init__(
        self,
        name: str = "Untitled Script",
        description: str = "",
        author: str = "sentinel-desktop",
        created: Optional[str] = None,
        version: str = "3.0",
        tags: Optional[List[str]] = None,
        parameters: Optional[List[Dict[str, str]]] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.author = author
        self.created = created or datetime.now(timezone.utc).isoformat()
        self.version = version
        self.tags: List[str] = tags or []
        self.parameters: List[Dict[str, str]] = parameters or []
        self.steps: List[Dict[str, Any]] = steps or []

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return the script as a plain dict matching the canonical JSON schema."""
        return {
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "created": self.created,
            "version": self.version,
            "tags": list(self.tags),
            "parameters": list(self.parameters),
            "steps": list(self.steps),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    # -- persistence -------------------------------------------------------

    def save(self, path: str) -> None:
        """Write the script JSON to *path*, creating parent dirs as needed."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "Script":
        """Load a Script from a JSON file on disk."""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(
            name=data.get("name", "Untitled Script"),
            description=data.get("description", ""),
            author=data.get("author", "sentinel-desktop"),
            created=data.get("created", ""),
            version=data.get("version", "3.0"),
            tags=data.get("tags", []),
            parameters=data.get("parameters", []),
            steps=data.get("steps", []),
        )


# ---------------------------------------------------------------------------
# Action Recorder
# ---------------------------------------------------------------------------

class ActionRecorder:
    """
    Hooks into the agent loop to capture each action + result into a
    replayable Script.

    Usage::

        rec = ActionRecorder()
        rec.start_recording("Fill in the login form and submit")
        rec.capture_action(action_dict, result_dict)
        rec.capture_action(action_dict, result_dict)
        script = rec.stop_recording()
        script.save("login_flow.json")
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recording: bool = False
        self._goal: str = ""
        self._steps: List[Dict[str, Any]] = []
        self._start_time: float = 0.0
        self._last_action_time: float = 0.0

    # -- public API --------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        """True when a recording session is active."""
        with self._lock:
            return self._recording

    def start_recording(self, goal_description: str = "") -> None:
        """
        Begin a new recording session.

        Parameters
        ----------
        goal_description:
            Optional human-readable goal (e.g. "Submit an expense report").
            Used to auto-generate the script name / description later.
        """
        with self._lock:
            if self._recording:
                raise RuntimeError("Recording is already in progress.")
            self._recording = True
            self._goal = goal_description.strip()
            self._steps = []
            self._start_time = time.monotonic()
            self._last_action_time = self._start_time

    def capture_action(self, action: Dict[str, Any], result: Dict[str, Any]) -> None:
        """
        Record a single action + its result captured from the agent loop.

        Parameters
        ----------
        action:
            Dict with at least ``"type"`` (str) and optional ``"params"`` (dict).
            Example: ``{"type": "click", "params": {"x": 100, "y": 200}}``
        result:
            Dict with result metadata.  May contain ``"screenshot"`` (raw
            bytes or base64 string), ``"summary"``, etc.
        """
        now = time.monotonic()
        with self._lock:
            if not self._recording:
                return

            duration_ms = int((now - self._last_action_time) * 1000)
            self._last_action_time = now

            action_type = action.get("type", "unknown")
            params = action.get("params", {})
            timestamp = datetime.now(timezone.utc).isoformat()

            # Derive a short human-friendly summary of the result
            result_summary = result.get("summary", "")
            if not result_summary:
                result_summary = self._summarise_result(action_type, params, result)

            # Screenshot hash — first 8 hex chars of base64-encoded MD5
            screenshot_hash = self._compute_screenshot_hash(result.get("screenshot"))

            step: Dict[str, Any] = {
                "timestamp": timestamp,
                "action": action_type,
                "params": dict(params),
                "description": self._describe_step(action_type, params, result_summary),
                "result_summary": result_summary,
                "screenshot_hash": screenshot_hash,
                "duration_ms": duration_ms,
                "wait_after_ms": 500,  # sensible default, caller can tweak
            }
            self._steps.append(step)

    def stop_recording(self) -> Script:
        """
        Stop recording and return a fully-populated :class:`Script`.

        The method auto-detects repeated text values across steps and
        promotes them to script parameters, and generates a natural
        language description of the recorded flow.
        """
        with self._lock:
            if not self._recording:
                raise RuntimeError("No recording in progress.")
            self._recording = False

            steps = list(self._steps)
            goal = self._goal

        # --- Build Script object (outside lock) ----------------------------
        parameters = self._detect_parameters(steps)
        description = self.generate_description(steps) if not goal else goal

        script = Script(
            name=self._generate_name(goal),
            description=description,
            steps=self._finalise_steps(steps),
            parameters=parameters,
        )
        return script

    # -- persistence helpers -----------------------------------------------

    @staticmethod
    def save_script(script: Script, path: str) -> None:
        """Convenience: save *script* to *path*."""
        script.save(path)

    @staticmethod
    def load_script(path: str) -> Script:
        """Convenience: load a Script from *path*."""
        return Script.load(path)

    @staticmethod
    def list_scripts(directory: str) -> List[Dict[str, Any]]:
        """
        Scan *directory* for ``.json`` files and return a list of dicts
        ``{"name": ..., "description": ..., "tags": [...], "path": ...}``.
        """
        results: List[Dict[str, Any]] = []
        pattern = os.path.join(directory, "*.json")
        for filepath in sorted(glob.glob(pattern)):
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, dict):
                    continue
                results.append({
                    "name": data.get("name", os.path.basename(filepath)),
                    "description": data.get("description", ""),
                    "tags": data.get("tags", []),
                    "path": filepath,
                })
            except (json.JSONDecodeError, OSError):
                continue
        return results

    # -- description generation --------------------------------------------

    @staticmethod
    def generate_description(steps: List[Dict[str, Any]]) -> str:
        """
        Auto-generate a natural-language description from recorded steps.

        Produces a single sentence or short paragraph such as:
        "Automates 5 steps: click on 'File' menu, type 'budget.xlsx' into
        the filename field, click 'Save', …"
        """
        if not steps:
            return "Empty recording — no actions captured."

        action_parts: List[str] = []
        for idx, step in enumerate(steps):
            action = step.get("action", "unknown")
            params = step.get("params", {})
            desc = step.get("description", "")

            if desc:
                fragment = desc
            else:
                fragment = ActionRecorder._describe_step_static(action, params)

            action_parts.append(fragment)

        count = len(action_parts)
        if count == 1:
            body = action_parts[0]
        elif count == 2:
            body = f"{action_parts[0]} and {action_parts[1]}"
        else:
            body = ", ".join(action_parts[:-1]) + f", and {action_parts[-1]}"

        return f"Automates {count} step{'s' if count != 1 else ''}: {body}."

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _compute_screenshot_hash(screenshot: Any) -> str:
        """Return first 8 hex characters of the base64-encoded MD5 digest."""
        if screenshot is None:
            return ""
        raw = screenshot if isinstance(screenshot, bytes) else str(screenshot).encode("utf-8")
        md5_digest = hashlib.md5(raw).digest()
        b64 = base64.b64encode(md5_digest).decode("ascii")
        return b64[:8]

    @staticmethod
    def _summarise_result(action_type: str, params: Dict[str, Any],
                          result: Dict[str, Any]) -> str:
        """Build a very short result summary when none is provided."""
        status = result.get("status", result.get("success", "done"))
        element = params.get("text", params.get("label", params.get("selector", "")))
        if element:
            return f"{action_type} on '{element}' — {status}"
        return f"{action_type} — {status}"

    @staticmethod
    def _describe_step(action_type: str, params: Dict[str, Any],
                       result_summary: str) -> str:
        """One-line human description of a single step."""
        verbs = {
            "click": "Click",
            "double_click": "Double-click",
            "right_click": "Right-click",
            "type": "Type",
            "key_press": "Press",
            "scroll": "Scroll",
            "hover": "Hover over",
            "drag": "Drag to",
            "screenshot": "Take screenshot",
            "wait": "Wait",
            "navigate": "Navigate to",
            "select": "Select",
            "copy": "Copy",
            "paste": "Paste",
            "focus": "Focus on",
        }
        verb = verbs.get(action_type, action_type.replace("_", " ").capitalize())

        target = (
            params.get("text")
            or params.get("label")
            or params.get("selector")
            or params.get("url")
            or params.get("key")
            or ""
        )

        if target:
            return f"{verb} '{target}'"
        if params.get("x") is not None and params.get("y") is not None:
            return f"{verb} at ({params['x']}, {params['y']})"
        return verb

    @staticmethod
    def _describe_step_static(action_type: str, params: Dict[str, Any]) -> str:
        return ActionRecorder._describe_step(action_type, params, "")

    @staticmethod
    def _generate_name(goal: str) -> str:
        """Derive a script name from the goal description."""
        if not goal:
            return f"script_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        # Take the first few words and slugify
        words = goal.split()[:6]
        slug = "_".join(w.lower().strip(".,;:!?") for w in words if w)
        slug = "".join(c if c.isalnum() or c == "_" else "_" for c in slug)
        return slug or "untitled_script"

    @staticmethod
    def _detect_parameters(steps: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Auto-detect repeated text values across steps and suggest
        parameterizing them.

        If the same string appears in two or more steps (inside ``params``
        values), it is promoted to a script parameter.
        """
        text_counts: Dict[str, int] = {}
        for step in steps:
            for val in step.get("params", {}).values():
                if isinstance(val, str) and len(val) >= 2:
                    text_counts[val] = text_counts.get(val, 0) + 1

        parameters: List[Dict[str, str]] = []
        for text, count in sorted(text_counts.items(), key=lambda kv: -kv[1]):
            if count >= 2:
                param_name = (
                    text.lower()
                    .replace(" ", "_")
                    .replace("'", "")
                    .replace('"', "")[:32]
                )
                param_name = "".join(c if c.isalnum() or c == "_" else "" for c in param_name)
                if param_name and not any(p["name"] == param_name for p in parameters):
                    parameters.append({
                        "name": param_name,
                        "type": "string",
                        "default": text,
                        "prompt": f"Enter value for '{param_name}'",
                    })
        return parameters

    @staticmethod
    def _finalise_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Strip internal-only fields so the serialized JSON matches the
        canonical schema (``action``, ``params``, ``description``,
        ``wait_after_ms``, ``screenshot_hash``).
        """
        out: List[Dict[str, Any]] = []
        for step in steps:
            out.append({
                "action": step.get("action", "unknown"),
                "params": step.get("params", {}),
                "description": step.get("description", ""),
                "wait_after_ms": step.get("wait_after_ms", 500),
                "screenshot_hash": step.get("screenshot_hash", ""),
            })
        return out
