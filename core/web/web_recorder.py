"""Sentinel Desktop v8.0 — Web action recorder.

Captures browser interactions (navigations, clicks, form fills) into
replayable Sentinel script JSON format. Extends the existing ActionRecorder
pattern with web-specific metadata (URLs, selectors, page titles).

Recorded scripts can be replayed via the existing core/script_engine.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Web actions that the recorder captures.
_WEB_RECORDABLE_ACTIONS: frozenset[str] = frozenset({
    "web_open", "web_click", "web_type", "web_read", "web_extract",
    "web_wait_for", "web_screenshot", "web_eval_js", "web_download",
    "web_upload", "web_tabs",
})


class WebRecording:
    """A recorded sequence of web browser actions.

    Stored as JSON with metadata + action list.
    Compatible with the Sentinel script JSON format.
    """

    def __init__(self, name: str = "", goal: str = "") -> None:
        self.name = name
        self.goal = goal
        self.created_at: str = datetime.utcnow().isoformat()
        self.actions: list[dict[str, Any]] = []

    def add_action(
        self,
        action: dict[str, Any],
        result: dict[str, Any] | None = None,
        page_url: str | None = None,
        page_title: str | None = None,
    ) -> None:
        """Record a web action.

        Args:
            action: The action dict (must have 'action' key).
            result: The execution result dict.
            page_url: Current page URL at time of action.
            page_title: Current page title at time of action.
        """
        entry: dict[str, Any] = {
            "action": action.get("action", "unknown"),
            "params": {k: v for k, v in action.items() if k != "action"},
            "timestamp": datetime.utcnow().isoformat(),
        }

        if result is not None:
            entry["result_success"] = result.get("success", False)

        if page_url:
            entry["page_url"] = page_url
        if page_title:
            entry["page_title"] = page_title

        self.actions.append(entry)

    @property
    def step_count(self) -> int:
        """Number of recorded actions."""
        return len(self.actions)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict compatible with Sentinel script format."""
        return {
            "version": "2.0",
            "type": "web_recording",
            "name": self.name,
            "goal": self.goal,
            "created_at": self.created_at,
            "steps_total": self.step_count,
            "actions": self.actions,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def save(self, path: str | Path) -> None:
        """Save recording to a JSON file.

        Args:
            path: File path to write to.
        """
        filepath = Path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(self.to_json(), encoding="utf-8")
        logger.info("Saved web recording to %s (%d steps)", filepath, self.step_count)

    @classmethod
    def load(cls, path: str | Path) -> WebRecording:
        """Load a recording from a JSON file.

        Args:
            path: File path to load from.

        Returns:
            WebRecording instance.
        """
        filepath = Path(path)
        data = json.loads(filepath.read_text(encoding="utf-8"))

        recording = cls(name=data.get("name", ""), goal=data.get("goal", ""))
        recording.created_at = data.get("created_at", "")
        recording.actions = data.get("actions", [])
        return recording

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WebRecording:
        """Create from a dict (e.g. loaded from JSON).

        Args:
            data: Dict with recording data.

        Returns:
            WebRecording instance.
        """
        recording = cls(name=data.get("name", ""), goal=data.get("goal", ""))
        recording.created_at = data.get("created_at", "")
        recording.actions = data.get("actions", [])
        return recording


class WebRecorder:
    """Records browser interactions into a WebRecording.

    Usage::

        recorder = WebRecorder()
        recorder.start("Login to firewall", goal="Configure firewall rules")
        recorder.capture({"action": "web_open", "url": "https://192.168.1.1"})
        recorder.capture({"action": "web_type", "text": "admin", "selector": "#user"})
        recording = recorder.stop()
        recording.save("recordings/firewall_login.json")

    The recorder filters to only web actions — native desktop actions
    are ignored.
    """

    def __init__(self) -> None:
        self._recording: WebRecording | None = None
        self._active: bool = False

    @property
    def is_recording(self) -> bool:
        """Whether the recorder is currently capturing actions."""
        return self._active

    @property
    def current_recording(self) -> WebRecording | None:
        """The current recording (None if not recording)."""
        return self._recording

    def start(self, name: str = "", goal: str = "") -> None:
        """Start recording.

        Args:
            name: Recording name.
            goal: What the recording accomplishes.
        """
        self._recording = WebRecording(name=name, goal=goal)
        self._active = True
        logger.info("Web recording started: %s", name or "(unnamed)")

    def capture(
        self,
        action: dict[str, Any],
        result: dict[str, Any] | None = None,
        page_url: str | None = None,
        page_title: str | None = None,
    ) -> bool:
        """Capture an action if it's a web action and recording is active.

        Args:
            action: Action dict with 'action' key.
            result: Execution result.
            page_url: Current page URL.
            page_title: Current page title.

        Returns:
            True if the action was recorded.
        """
        if not self._active or self._recording is None:
            return False

        action_name = action.get("action", "")
        if action_name not in _WEB_RECORDABLE_ACTIONS:
            return False

        self._recording.add_action(
            action, result, page_url=page_url, page_title=page_title,
        )
        return True

    def stop(self) -> WebRecording | None:
        """Stop recording and return the recording.

        Returns:
            The completed WebRecording, or None if not recording.
        """
        if not self._active or self._recording is None:
            return None

        self._active = False
        recording = self._recording
        self._recording = None
        logger.info("Web recording stopped: %d steps", recording.step_count)
        return recording
