"""Sentinel Desktop — Shared utility functions used across multiple core modules."""

import logging
import platform
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def is_windows() -> bool:
    """Return True when running on Microsoft Windows."""
    return platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Shared availability checks for optional dependencies
# ---------------------------------------------------------------------------


_TESSERACT_OK: bool | None = None
_pytesseract = None  # pytesseract module ref


def have_tesseract() -> bool:
    """Lazily probe for pytesseract + Tesseract binary.

    Returns True if both pytesseract package and Tesseract binary are available,
    False otherwise. Caches the result for efficiency.

    This is a shared utility used by multiple modules (ocr, mfa_detection,
    popup_handler) to avoid duplication of the availability check logic.
    """
    global _TESSERACT_OK, _pytesseract
    if _TESSERACT_OK is not None:
        return _TESSERACT_OK
    try:
        import pytesseract  # type: ignore

        pytesseract.get_tesseract_version()
        _pytesseract = pytesseract
        _TESSERACT_OK = True
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        logger.debug("Tesseract/OCR unavailable (%s)", exc)
        _TESSERACT_OK = False
    return _TESSERACT_OK


_UIA_OK: bool | None = None
_auto = None  # uiautomation module ref


def have_uia() -> bool:
    """Lazily probe for the uiautomation package and COM availability.

    Returns True if uiautomation package is available and running on Windows,
    False otherwise. Caches the result for efficiency.

    This is a shared utility used by multiple modules (mfa_detection, ui_tree)
    to avoid duplication of the availability check logic.
    """
    global _UIA_OK, _auto
    if _UIA_OK is not None:
        return _UIA_OK
    if platform.system() != "Windows":
        _UIA_OK = False
        return False
    try:
        import uiautomation as auto  # type: ignore

        _auto = auto
        _UIA_OK = True
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        logger.debug("UIAutomation unavailable (%s)", exc)
        _UIA_OK = False
    return _UIA_OK


def get_uia_auto():
    """Return the uiautomation module reference if available, else None.

    This provides access to the uiautomation module for functions that need
    to call its methods directly. Call have_uia() first to ensure availability.
    """
    return _auto


def get_tesseract():
    """Return the pytesseract module reference if available, else None.

    This provides access to the pytesseract module for functions that need
    to call its methods directly. Call have_tesseract() first to ensure availability.
    """
    return _pytesseract
