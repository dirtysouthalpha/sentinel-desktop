"""Clipboard read/write."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_clipboard: Any = None

try:
    import pyperclip  # type: ignore[import-untyped]

    _PyperclipException: type[Exception] = pyperclip.PyperclipException
except ImportError:
    pyperclip = None  # type: ignore[assignment]
    _PyperclipException = OSError


def _get_clipboard() -> Any | None:
    global _clipboard
    if _clipboard is None:
        if pyperclip is None:
            logger.warning("pyperclip not installed — clipboard unavailable")
            return None
        _clipboard = pyperclip
    return _clipboard


def clipboard_read() -> str:
    cb = _get_clipboard()
    if cb is None:
        return ""
    try:
        return cb.paste()
    except Exception as exc:
        logger.warning("clipboard_read failed: %s", exc)
        return ""


def clipboard_write(text: str) -> bool:
    cb = _get_clipboard()
    if cb is None:
        return False
    try:
        cb.copy(text)
        return True
    except Exception as exc:
        logger.warning("clipboard_write failed: %s", exc)
        return False
