"""Browser action recorder.

Watches user actions (or agent actions) and records them as a
reusable workflow that can be replayed with different parameters.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RecordedAction:
    """A single recorded browser action."""

    action: str  # click, fill, navigate, wait, type, select
    selector: str = ""
    text: str = ""
    url: str = ""
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Recording:
    """A complete recording session — can be saved as a workflow."""

    name: str
    base_url: str = ""
    actions: list[RecordedAction] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    parameters: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["actions"] = [a.to_dict() for a in self.actions]
        return d

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Recording:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        actions = [RecordedAction(**a) for a in data.pop("actions", [])]
        return cls(actions=actions, **data)


class BrowserRecorder:
    """Records browser actions for replay."""

    def __init__(self) -> None:
        self._recording: Recording | None = None
        self._active = False

    def start_recording(self, name: str, base_url: str = "") -> None:
        self._recording = Recording(name=name, base_url=base_url)
        self._active = True
        logger.info("Recording started: %s", name)

    def record(self, action: str, **kwargs: Any) -> None:
        if not self._active or not self._recording:
            return
        self._recording.actions.append(RecordedAction(
            action=action,
            timestamp=time.time(),
            **kwargs,
        ))

    def record_click(self, selector: str, **meta: Any) -> None:
        self.record("click", selector=selector, metadata=meta)

    def record_fill(self, selector: str, value: str, **meta: Any) -> None:
        self.record("fill", selector=selector, text=value, metadata=meta)

    def record_navigate(self, url: str) -> None:
        self.record("navigate", url=url)

    def record_wait(self, selector: str) -> None:
        self.record("wait", selector=selector)

    def record_type(self, selector: str, text: str) -> None:
        self.record("type", selector=selector, text=text)

    def record_select(self, selector: str, value: str) -> None:
        self.record("select", selector=selector, text=value)

    def stop_recording(self) -> Recording | None:
        self._active = False
        return self._recording

    def save_recording(self, path: str | Path) -> None:
        if self._recording:
            self._recording.save(path)

    @property
    def is_recording(self) -> bool:
        return self._active


class BrowserReplayer:
    """Replays recorded browser actions."""

    def __init__(self, browser: Any) -> None:
        """browser should be a BrowserController instance."""
        self._browser = browser

    def replay(self, recording: Recording, parameters: dict[str, str] | None = None) -> bool:
        """Execute a recorded sequence, substituting parameters."""
        if parameters is None:
            parameters = {}

        logger.info("Replaying recording: %s (%d actions)", recording.name, len(recording.actions))

        # Navigate to start URL
        if recording.base_url:
            url = recording.base_url
            for key, value in parameters.items():
                url = url.replace("{{" + key + "}}", value)
            if not self._browser.navigate(url):
                logger.error("Failed to navigate to %s", url)
                return False

        for action in recording.actions:
            if not self._replay_action(action, parameters):
                logger.warning("Action failed: %s", action.action)
                return False

        logger.info("Replay completed: %s", recording.name)
        return True

    def _replay_action(self, action: RecordedAction, parameters: dict[str, str]) -> bool:
        """Replay a single action with parameter substitution."""
        # Substitute parameters in text/selector/url
        selector = action.selector
        text = action.text
        for key, value in parameters.items():
            selector = selector.replace("{{" + key + "}}", value)
            text = text.replace("{{" + key + "}}", value)

        if action.action == "click":
            return self._browser.click(selector)
        elif action.action == "fill":
            return self._browser.fill(selector, text)
        elif action.action == "navigate":
            url = action.url
            for key, value in parameters.items():
                url = url.replace("{{" + key + "}}", value)
            return self._browser.navigate(url)
        elif action.action == "wait":
            return self._browser.wait_for_element(selector)
        elif action.action == "type":
            return self._browser.type_text(selector, text)
        elif action.action == "select":
            return self._browser.select_option(selector, text)
        else:
            logger.warning("Unknown action type: %s", action.action)
            return True


__all__ = ["RecordedAction", "Recording", "BrowserRecorder", "BrowserReplayer"]
