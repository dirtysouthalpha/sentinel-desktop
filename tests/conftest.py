"""Shared pytest fixtures, sys.path setup, and headless-friendly stubs.

Many of the modules under test transitively import ``pyautogui``, which on
import tries to open an X display. On CI / headless servers there is no
display and the process crashes. We register lightweight stubs in
``sys.modules`` before any test imports run so the modules load cleanly.
"""

import os
import sys
import types
from pathlib import Path

import pytest

# 1) Make sure the project root is importable as `core`, `gui`, `api`, etc.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Humanization safety net: force humanization OFF for the whole test suite.
# Many existing tests assert exact coordinates / timings; humanized curves
# and jitter would break them. Tests that specifically exercise humanization
# set SENTINEL_HUMANIZE locally via monkeypatch. (core/humanize/__init__.py)
os.environ.setdefault("SENTINEL_HUMANIZE", "0")


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
        pyautogui.FAILSAFE_POINTS = [(0, 0)]
        pyautogui.FailSafeException = type("FailSafeException", (Exception,), {})
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

    # mss tries to connect to X display on import — stub it on headless CI
    if "mss" not in sys.modules:
        mss = types.ModuleType("mss")

        class _MssContext:
            """Stub mss context manager for headless testing."""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            @property
            def monitors(self):
                # Return fake monitor data: [virtual desktop, monitor 1]
                return [
                    {"left": 0, "top": 0, "width": 1920, "height": 1080},
                    {"left": 0, "top": 0, "width": 1920, "height": 1080},
                ]

            def grab(self, rect):
                """Return fake screenshot data."""
                _FakeScreenshot = type(
                    "_FakeScreenshot",
                    (),
                    {
                        "size": (rect.get("width", 10), rect.get("height", 10)),
                        "rgb": b"\x00" * (rect.get("width", 10) * rect.get("height", 10) * 3),
                    },
                )
                return _FakeScreenshot()

        mss.mss = _MssContext
        mss.ScreenShotError = type("ScreenShotError", (Exception,), {})
        sys.modules["mss"] = mss

    # pystray tries to connect to X display on import — stub it on headless CI
    if "pystray" not in sys.modules:
        sys.modules["pystray"] = types.ModuleType("pystray")

    # tkinter requires libtk8.6.so — unavailable in headless containers.
    # Stub it and customtkinter so GUI module imports succeed without Tk.
    if "tkinter" not in sys.modules:
        _tk = types.ModuleType("tkinter")

        class _Var:
            def __init__(self, *a, **kw):
                self._value = None

            def get(self):
                return self._value

            def set(self, v):
                self._value = v

            def trace_add(self, *a, **kw):
                pass

        class _Tk:
            def __init__(self, *a, **kw):
                pass

            def mainloop(self):
                pass

            def quit(self):
                pass

            def destroy(self):
                pass

            def after(self, *a, **kw):
                pass

            def after_cancel(self, *a):
                pass

            def bind(self, *a, **kw):
                pass

            def unbind(self, *a, **kw):
                pass

            def configure(self, *a, **kw):
                pass

            config = configure

            def cget(self, key, default=None):
                return default

            def grid(self, *a, **kw):
                pass

            def grid_remove(self, *a, **kw):
                pass

            def grid_forget(self, *a, **kw):
                pass

            def grid_columnconfigure(self, *a, **kw):
                pass

            def grid_rowconfigure(self, *a, **kw):
                pass

            def pack(self, *a, **kw):
                pass

            def pack_forget(self, *a, **kw):
                pass

            def place(self, *a, **kw):
                pass

            def place_forget(self, *a, **kw):
                pass

            def overrideredirect(self, *a, **kw):
                pass

            def attributes(self, *a, **kw):
                pass

            def wm_attributes(self, *a, **kw):
                pass

            def geometry(self, *a, **kw):
                pass

            def title(self, *a, **kw):
                pass

            def lift(self, *a, **kw):
                pass

            def lower(self, *a, **kw):
                pass

            def withdraw(self, *a, **kw):
                pass

            def deiconify(self, *a, **kw):
                pass

            def iconify(self, *a, **kw):
                pass

            def state(self, *a, **kw):
                return "normal"

            def protocol(self, *a, **kw):
                pass

            def focus_set(self, *a, **kw):
                pass

            def focus_force(self, *a, **kw):
                pass

            def update(self, *a, **kw):
                pass

            def update_idletasks(self, *a, **kw):
                pass

            def winfo_id(self):
                return 0

            def winfo_children(self):
                return []

            def winfo_exists(self):
                return True

            def winfo_width(self):
                return 100

            def winfo_height(self):
                return 100

            def winfo_x(self):
                return 0

            def winfo_y(self):
                return 0

            def winfo_rootx(self):
                return 0

            def winfo_rooty(self):
                return 0

            def winfo_screenwidth(self):
                return 1920

            def winfo_screenheight(self):
                return 1080

            def winfo_ismapped(self):
                return True

        # Canvas adds item-creation helpers; each returns a fake item id.
        _canvas_extra = {
            "create_oval": lambda self, *a, **kw: 1,
            "create_text": lambda self, *a, **kw: 2,
            "create_rectangle": lambda self, *a, **kw: 3,
            "create_line": lambda self, *a, **kw: 4,
            "create_polygon": lambda self, *a, **kw: 5,
            "create_arc": lambda self, *a, **kw: 6,
            "create_image": lambda self, *a, **kw: 7,
            "create_window": lambda self, *a, **kw: 8,
            "delete": lambda self, *a, **kw: None,
            "coords": lambda self, *a, **kw: (0, 0, 0, 0),
            "itemconfig": lambda self, *a, **kw: None,
            "itemconfigure": lambda self, *a, **kw: None,
            "move": lambda self, *a, **kw: None,
            "bbox": lambda self, *a, **kw: (0, 0, 0, 0),
            "tag_bind": lambda self, *a, **kw: None,
            "yview": lambda self, *a, **kw: None,
            "xview": lambda self, *a, **kw: None,
        }

        _tk.Tk = _Tk
        _tk.Frame = type("Frame", (_Tk,), {})
        _tk.Toplevel = type("Toplevel", (_Tk,), {})
        _tk.Label = type("Label", (_Tk,), {})
        _tk.Button = type("Button", (_Tk,), {})
        _tk.Entry = type("Entry", (_Tk,), {})
        _tk.Text = type("Text", (_Tk,), {})
        _tk.Canvas = type("Canvas", (_Tk,), _canvas_extra)
        _tk.Scrollbar = type("Scrollbar", (_Tk,), {})
        _tk.Listbox = type("Listbox", (_Tk,), {})
        _tk.Menu = type("Menu", (_Tk,), {})
        _tk.TclError = type("TclError", (Exception,), {})
        _tk.StringVar = type("StringVar", (_Var,), {})
        _tk.IntVar = type("IntVar", (_Var,), {})
        _tk.DoubleVar = type("DoubleVar", (_Var,), {})
        _tk.BooleanVar = type("BooleanVar", (_Var,), {})
        _tk.Variable = _Var
        _tk.BOTTOM = "bottom"
        _tk.TOP = "top"
        _tk.LEFT = "left"
        _tk.RIGHT = "right"
        _tk.BOTH = "both"
        _tk.X = "x"
        _tk.Y = "y"
        _tk.END = "end"
        _tk.NORMAL = "normal"
        _tk.DISABLED = "disabled"
        _tk.HORIZONTAL = "horizontal"
        _tk.VERTICAL = "vertical"
        _tk.NSEW = "nsew"
        _tk.W = "w"
        _tk.E = "e"
        _tk.N = "n"
        _tk.S = "s"
        _tk.CENTER = "center"
        _tk.constants = types.ModuleType("tkinter.constants")
        for _attr in (
            "BOTTOM",
            "TOP",
            "LEFT",
            "RIGHT",
            "BOTH",
            "X",
            "Y",
            "END",
            "NORMAL",
            "DISABLED",
            "HORIZONTAL",
            "VERTICAL",
            "NSEW",
            "W",
            "E",
            "N",
            "S",
            "CENTER",
        ):
            setattr(_tk.constants, _attr, getattr(_tk, _attr))
        sys.modules["tkinter"] = _tk
        sys.modules["tkinter.constants"] = _tk.constants

    if "_tkinter" not in sys.modules:
        sys.modules["_tkinter"] = types.ModuleType("_tkinter")

    if "customtkinter" not in sys.modules:
        _ctk = types.ModuleType("customtkinter")

        class _CTkBase:
            """Stub base for all CTk widgets — accepts any constructor args."""

            def __init__(self, *a, **kw):
                for k, v in kw.items():
                    setattr(self, k, v)

            def grid(self, *a, **kw):
                pass

            def grid_forget(self, *a, **kw):
                pass

            def pack(self, *a, **kw):
                pass

            def pack_forget(self, *a, **kw):
                pass

            def place(self, *a, **kw):
                pass

            def place_forget(self, *a, **kw):
                pass

            def configure(self, *a, **kw):
                pass

            config = configure

            def cget(self, key, default=None):
                return getattr(self, key, default)

            def bind(self, *a, **kw):
                pass

            def unbind(self, *a, **kw):
                pass

            def after(self, *a, **kw):
                return ""

            def after_cancel(self, *a):
                pass

            def destroy(self):
                pass

            # text/entry widget helpers
            def insert(self, *a, **kw):
                pass

            def delete(self, *a, **kw):
                pass

            def get(self, *a, **kw):
                return ""

            def set(self, *a, **kw):
                pass

            def see(self, *a, **kw):
                pass

            def index(self, *a, **kw):
                return "1.0"

            def icursor(self, *a, **kw):
                pass

            def select_range(self, *a, **kw):
                pass

            def focus(self, *a, **kw):
                pass

            def focus_set(self, *a, **kw):
                pass

            def focus_force(self, *a, **kw):
                pass

            def yview(self, *a, **kw):
                pass

            def yview_moveto(self, *a, **kw):
                pass

            def xview(self, *a, **kw):
                pass

            def tag_add(self, *a, **kw):
                pass

            def tag_config(self, *a, **kw):
                pass

            def tag_configure(self, *a, **kw):
                pass

            def tag_remove(self, *a, **kw):
                pass

            def tag_bind(self, *a, **kw):
                pass

            # toplevel/window helpers
            def title(self, *a, **kw):
                pass

            def geometry(self, *a, **kw):
                pass

            def resizable(self, *a, **kw):
                pass

            def minsize(self, *a, **kw):
                pass

            def maxsize(self, *a, **kw):
                pass

            def transient(self, *a, **kw):
                pass

            def grab_set(self, *a, **kw):
                pass

            def grab_release(self, *a, **kw):
                pass

            def wait_window(self, *a, **kw):
                pass

            def protocol(self, *a, **kw):
                pass

            def overrideredirect(self, *a, **kw):
                pass

            def attributes(self, *a, **kw):
                pass

            def wm_attributes(self, *a, **kw):
                pass

            def lift(self, *a, **kw):
                pass

            def lower(self, *a, **kw):
                pass

            def deiconify(self, *a, **kw):
                pass

            def withdraw(self, *a, **kw):
                pass

            def iconify(self, *a, **kw):
                pass

            def state(self, *a, **kw):
                return "normal"

            def winfo_children(self):
                return []

            def winfo_exists(self):
                return True

            def winfo_toplevel(self):
                return self

            def winfo_width(self):
                return 100

            def winfo_height(self):
                return 100

            def winfo_x(self):
                return 0

            def winfo_y(self):
                return 0

            def winfo_rootx(self):
                return 0

            def winfo_rooty(self):
                return 0

            def winfo_reqwidth(self):
                return 100

            def winfo_reqheight(self):
                return 100

            def winfo_screenwidth(self):
                return 1920

            def winfo_screenheight(self):
                return 1080

            def winfo_ismapped(self):
                return True

            def grid_remove(self):
                pass

            def grid_columnconfigure(self, *a, **kw):
                pass

            def grid_rowconfigure(self, *a, **kw):
                pass

            def pack_propagate(self, flag=False):
                pass

            def grid_propagate(self, flag=False):
                pass

            def update_idletasks(self):
                pass

            def update(self):
                pass

        # Provide all commonly-used CTk widget classes
        for _name in (
            "CTk",
            "CTkFrame",
            "CTkLabel",
            "CTkButton",
            "CTkEntry",
            "CTkTextbox",
            "CTkScrollableFrame",
            "CTkOptionMenu",
            "CTkToplevel",
            "CTkCheckBox",
            "CTkComboBox",
            "CTkProgressBar",
            "CTkRadioButton",
            "CTkSlider",
            "CTkSwitch",
            "CTkTabview",
            "CTkImage",
            "CTkCanvas",
            "CTkSegmentedButton",
        ):
            setattr(_ctk, _name, type(_name, (_CTkBase,), {}))

        # CTkFont is a plain callable (not a widget), just accept any kwargs
        _ctk.CTkFont = lambda *a, **kw: None

        _ctk.StringVar = type(
            "StringVar",
            (),
            {
                "__init__": lambda s, *a, **kw: None,
                "get": lambda s: "",
                "set": lambda s, v: None,
                "trace_add": lambda s, *a, **kw: None,
            },
        )
        _ctk.IntVar = type(
            "IntVar",
            (),
            {
                "__init__": lambda s, *a, **kw: None,
                "get": lambda s: 0,
                "set": lambda s, v: None,
                "trace_add": lambda s, *a, **kw: None,
            },
        )
        _ctk.DoubleVar = type(
            "DoubleVar",
            (),
            {
                "__init__": lambda s, *a, **kw: None,
                "get": lambda s: 0.0,
                "set": lambda s, v: None,
                "trace_add": lambda s, *a, **kw: None,
            },
        )
        _ctk.BooleanVar = type(
            "BooleanVar",
            (),
            {
                "__init__": lambda s, *a, **kw: None,
                "get": lambda s: False,
                "set": lambda s, v: None,
                "trace_add": lambda s, *a, **kw: None,
            },
        )
        _ctk.set_appearance_mode = lambda *a, **kw: None
        _ctk.set_default_color_theme = lambda *a, **kw: None
        _ctk.set_widget_scaling = lambda *a, **kw: None
        _ctk.DARK = "Dark"
        _ctk.LIGHT = "Light"
        _ctk.SYSTEM = "System"
        sys.modules["customtkinter"] = _ctk


_install_headless_stubs()


@pytest.fixture(autouse=True)
def _restore_headless_stubs():
    """Re-install headless stubs if a test deleted them from sys.modules.

    Some tests (e.g. popup_handler key-send tests) temporarily replace or
    delete ``pyautogui`` / ``mouseinfo`` from ``sys.modules``.  Without this
    guard, later tests that ``import pyautogui`` trigger the real X11 module
    load and crash on headless CI.
    """
    yield
    _install_headless_stubs()


def pytest_sessionstart():
    """Clean up stale .pytest_tmp directory at session start.

    Pytest 8.x uses .pytest_tmp for tmp_path fixture. If a previous run was
    interrupted (e.g., by user, crash, timeout), the directory may remain,
    causing FileExistsError on subsequent runs. Clean it up proactively.
    """
    import shutil
    import warnings

    pytest_tmp = Path(__file__).resolve().parent.parent / ".pytest_tmp"
    if pytest_tmp.exists():
        try:
            # Use ignore_errors to handle symlinks and locked files gracefully
            shutil.rmtree(pytest_tmp, ignore_errors=True)
        except OSError as e:
            # If cleanup fails (permission issues, etc.), warn but don't block tests
            warnings.warn(f"Failed to clean up .pytest_tmp: {e}", stacklevel=2)
    # Recreate the directory so pytest can use it for tmp_path fixtures
    pytest_tmp.mkdir(parents=True, exist_ok=True)
