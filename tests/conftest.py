"""Shared pytest fixtures, sys.path setup, and headless-friendly stubs.

Many of the modules under test transitively import ``pyautogui``, which on
import tries to open an X display. On CI / headless servers there is no
display and the process crashes. We register lightweight stubs in
``sys.modules`` before any test imports run so the modules load cleanly.
"""

import sys
import types
from pathlib import Path

# 1) Make sure the project root is importable as `core`, `gui`, `api`, etc.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# 2) Stub display-dependent libraries so they don't try to connect to X.
def _install_headless_stubs() -> None:
    if "pyautogui" not in sys.modules:
        pyautogui = types.ModuleType("pyautogui")

        def _noop(*_a, **_kw):
            return None

        def _size():
            return (1920, 1080)

        def _position():
            return (0, 0)

        def _screenshot(*_a, **_kw):
            # Lazy PIL import — only when something actually tries to capture.
            from PIL import Image

            return Image.new("RGB", (10, 10))

        pyautogui.PAUSE = 0.1
        pyautogui.FAILSAFE = True
        pyautogui.size = _size
        pyautogui.position = _position
        pyautogui.screenshot = _screenshot
        for name in (
            "click",
            "doubleClick",
            "rightClick",
            "moveTo",
            "drag",
            "scroll",
            "typewrite",
            "write",
            "press",
            "hotkey",
        ):
            setattr(pyautogui, name, _noop)
        sys.modules["pyautogui"] = pyautogui

    if "mouseinfo" not in sys.modules:
        sys.modules["mouseinfo"] = types.ModuleType("mouseinfo")


_install_headless_stubs()
