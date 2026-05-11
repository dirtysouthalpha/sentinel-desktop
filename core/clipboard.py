"""Clipboard read/write."""
import logging

logger = logging.getLogger(__name__)

_clipboard = None


def _get_clipboard():
    global _clipboard
    if _clipboard is None:
        try:
            import pyperclip
            _clipboard = pyperclip
        except ImportError:
            logger.warning("pyperclip not installed — clipboard unavailable")
            return None
    return _clipboard


def clipboard_read() -> str:
    cb = _get_clipboard()
    if cb is None:
        return ""
    try:
        return cb.paste()
    except Exception as e:
        logger.error("clipboard_read failed: %s", e)
        return ""


def clipboard_write(text: str) -> bool:
    cb = _get_clipboard()
    if cb is None:
        return False
    try:
        cb.copy(text)
        return True
    except Exception as e:
        logger.error("clipboard_write failed: %s", e)
        return False
