"""UI diff detection.

Detects when a page or window content has changed unexpectedly
during automation, so the agent can adapt instead of blindly continuing.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiffResult:
    """Result of comparing two UI states."""

    changed: bool
    change_percent: float = 0.0
    added_text: list[str] = field(default_factory=list)
    removed_text: list[str] = field(default_factory=list)
    description: str = ""


class UIDiffDetector:
    """Compare screenshots or DOM snapshots to detect unexpected changes."""

    def __init__(self, threshold: float = 0.15) -> None:
        """threshold: fraction of pixels that must differ to be "changed"."""
        self._threshold = threshold
        self._last_hash: str = ""
        self._last_text: str = ""

    def check_screenshot(self, screenshot: Any) -> DiffResult:
        """Compare current screenshot to last seen."""
        if screenshot is None:
            return DiffResult(changed=False)

        try:
            if hasattr(screenshot, "convert"):
                img = screenshot.convert("L").resize((100, 100))
                data = list(img.tobytes())
            else:
                return DiffResult(changed=False)

            current_hash = hashlib.md5(bytes(data)).hexdigest()
            if not self._last_hash:
                self._last_hash = current_hash
                return DiffResult(changed=False)

            # Simple hash comparison
            changed = current_hash != self._last_hash
            self._last_hash = current_hash

            return DiffResult(
                changed=changed, description="Screenshot hash changed" if changed else "No change detected"
            )
        except Exception as exc:
            logger.debug("Screenshot diff failed: %s", exc)
            return DiffResult(changed=False)

    def check_text(self, text: str) -> DiffResult:
        """Compare current text content to last seen."""
        if not self._last_text:
            self._last_text = text
            return DiffResult(changed=False)

        old_words = set(self._last_text.split())
        new_words = set(text.split())

        added = new_words - old_words
        removed = old_words - new_words

        total = len(old_words | new_words)
        change_pct = len(added | removed) / total if total > 0 else 0.0

        self._last_text = text

        return DiffResult(
            changed=change_pct > self._threshold,
            change_percent=change_pct,
            added_text=list(added)[:50],
            removed_text=list(removed)[:50],
            description=f"Text changed: +{len(added)} -{len(removed)} words",
        )

    def reset(self) -> None:
        self._last_hash = ""
        self._last_text = ""


__all__ = ["DiffResult", "UIDiffDetector"]
