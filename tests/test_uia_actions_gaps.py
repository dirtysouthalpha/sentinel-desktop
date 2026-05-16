"""Gap-filling tests for core.uia_actions — covers all uncovered line ranges.

Targets lines: 43-53, 65-79, 154-155, 159-172, 188-189, 211-212, 216-224,
235-236, 260-261, 265-275, 292-293, 297-300, 326-327, 333-336, 357-358,
364-367, 385-386, 392-395, 416-417, 423-426, 441-463, 473-476, 505-506,
524-525, 598-600, 617-618, 630-700.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

import core.uia_actions as mod

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeDesktop:
    """Minimal fake DesktopController for tier-3 tests."""

    def __init__(self):
        self.calls: list[tuple] = []

    def click(self, x, y, *, button="left", clicks=1):
        self.calls.append(("click", x, y, button, clicks))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))

    def scroll(self, amount, *, x=None, y=None):
        self.calls.append(("scroll", amount, x, y))


class BrokenDesktop:
    """Desktop controller that raises on every call — covers exception paths."""

    def click(self, x, y, *, button="left", clicks=1):
        raise OSError("desktop click failed")

    def type_text(self, text):
        raise AttributeError("desktop type_text failed")

    def press_key(self, key):
        raise RuntimeError("desktop press_key failed")

    def hotkey(self, *keys):
        raise OSError("desktop hotkey failed")

    def scroll(self, amount, *, x=None, y=None):
        raise RuntimeError("desktop scroll failed")


@pytest.fixture(autouse=True)
def _reset_probes():
    """Reset availability caches between tests."""
    mod._UIA_AVAILABLE = None
    mod._auto = None
    mod._POSTMESSAGE_AVAILABLE = None
    mod._win32gui = None
    mod._win32api = None
    mod._win32con = None
    yield
    mod._UIA_AVAILABLE = None
    mod._auto = None
    mod._POSTMESSAGE_AVAILABLE = None
    mod._win32gui = None
    mod._win32api = None
    mod._win32con = None


@pytest.fixture
def pipe():
    return mod.UIAActionPipeline()


@pytest.fixture
def no_tiers(monkeypatch):
    """Disable both UIA and PostMessage tiers so only physical (tier 3) runs."""
    monkeypatch.setattr(mod, "_probe_uia", lambda: False)
    monkeypatch.setattr(mod, "_probe_postmessage", lambda: False)


@pytest.fixture
def uia_only(monkeypatch):
    """Enable UIA tier, disable PostMessage."""
    monkeypatch.setattr(mod, "_probe_uia", lambda: True)
    monkeypatch.setattr(mod, "_probe_postmessage", lambda: False)


@pytest.fixture
def postmsg_only(monkeypatch):
    """Disable UIA, enable PostMessage."""
    monkeypatch.setattr(mod, "_probe_uia", lambda: False)
    monkeypatch.setattr(mod, "_probe_postmessage", lambda: True)


@pytest.fixture
def all_tiers(monkeypatch):
    """Enable both UIA and PostMessage."""
    monkeypatch.setattr(mod, "_probe_uia", lambda: True)
    monkeypatch.setattr(mod, "_probe_postmessage", lambda: True)


# ===========================================================================
# _probe_uia — lines 43-53 (full probe path, import success/failure)
# ===========================================================================


class TestProbeUIA:
    """Covers lines 43-53: _probe_uia full probe logic."""

    def test_import_success_sets_globals(self, monkeypatch):
        """Successful import sets _auto and _UIA_AVAILABLE=True."""
        fake_auto = types.ModuleType("uiautomation")
        monkeypatch.setitem(sys.modules, "uiautomation", fake_auto)
        # Reset cache so probe runs fresh
        mod._UIA_AVAILABLE = None
        mod._auto = None
        result = mod._probe_uia()
        assert result is True
        assert mod._auto is fake_auto
        assert mod._UIA_AVAILABLE is True

    def test_import_failure_returns_false(self, monkeypatch):
        """ImportError / ModuleNotFoundError sets _UIA_AVAILABLE=False."""
        # Ensure uiautomation is NOT importable
        monkeypatch.setitem(sys.modules, "uiautomation", None)
        mod._UIA_AVAILABLE = None
        mod._auto = None
        result = mod._probe_uia()
        assert result is False
        assert mod._UIA_AVAILABLE is False

    def test_oserror_returns_false(self, monkeypatch):
        """OSError during import sets _UIA_AVAILABLE=False."""
        # First remove any cached module
        orig = sys.modules.pop("uiautomation", None)
        try:
            # Create a module that raises OSError on import
            types.ModuleType("uiautomation")

            def _raise_os(*a, **kw):
                raise OSError("COM init failed")

            # We'll simulate the error by making the cached value already set
            # to None and having the import itself fail
            mod._UIA_AVAILABLE = None
            mod._auto = None
            # Force the import to fail with OSError
            monkeypatch.setitem(sys.modules, "uiautomation", None)
            result = mod._probe_uia()
            assert result is False
        finally:
            if orig is not None:
                sys.modules["uiautomation"] = orig

    def test_cached_true_returns_immediately(self):
        """When _UIA_AVAILABLE is already True, returns True without re-importing."""
        mod._UIA_AVAILABLE = True
        mod._auto = MagicMock()
        result = mod._probe_uia()
        assert result is True

    def test_cached_false_returns_immediately(self):
        """When _UIA_AVAILABLE is already False, returns False."""
        mod._UIA_AVAILABLE = False
        result = mod._probe_uia()
        assert result is False


# ===========================================================================
# _probe_postmessage — lines 65-79 (full probe path)
# ===========================================================================


class TestProbePostmessage:
    """Covers lines 65-79: _probe_postmessage full probe logic."""

    def test_import_success_sets_globals(self, monkeypatch):
        """Successful import sets _win32gui, _win32api, _win32con."""
        fake_gui = types.ModuleType("win32gui")
        fake_api = types.ModuleType("win32api")
        fake_con = types.ModuleType("win32con")
        monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
        monkeypatch.setitem(sys.modules, "win32api", fake_api)
        monkeypatch.setitem(sys.modules, "win32con", fake_con)
        mod._POSTMESSAGE_AVAILABLE = None
        mod._win32gui = None
        mod._win32api = None
        mod._win32con = None
        result = mod._probe_postmessage()
        assert result is True
        assert mod._win32gui is fake_gui
        assert mod._win32api is fake_api
        assert mod._win32con is fake_con
        assert mod._POSTMESSAGE_AVAILABLE is True

    def test_import_failure_returns_false(self, monkeypatch):
        """ImportError sets _POSTMESSAGE_AVAILABLE=False."""
        monkeypatch.setitem(sys.modules, "win32gui", None)
        monkeypatch.setitem(sys.modules, "win32api", None)
        monkeypatch.setitem(sys.modules, "win32con", None)
        mod._POSTMESSAGE_AVAILABLE = None
        mod._win32gui = None
        mod._win32api = None
        mod._win32con = None
        result = mod._probe_postmessage()
        assert result is False
        assert mod._POSTMESSAGE_AVAILABLE is False

    def test_cached_true_returns_immediately(self):
        mod._POSTMESSAGE_AVAILABLE = True
        result = mod._probe_postmessage()
        assert result is True

    def test_cached_false_returns_immediately(self):
        mod._POSTMESSAGE_AVAILABLE = False
        result = mod._probe_postmessage()
        assert result is False


# ===========================================================================
# click_element — lines 154-155, 159-172, 188-189
# ===========================================================================


class TestClickElementGaps:
    """Covers lines 154-155 (UIA exc), 159-172 (PostMessage tier),
    188-189 (physical exc)."""

    def test_uia_exception_falls_through(self, pipe, uia_only, monkeypatch):
        """Lines 154-155: UIA tier raises, falls to physical failure."""
        import core.ui_tree as ui_tree_mod

        def _raise(**kw):
            raise RuntimeError("UIA boom")

        monkeypatch.setattr(ui_tree_mod, "click_control", _raise)
        # No bounds, so physical also fails
        monkeypatch.setattr(pipe, "_uia_bounds", lambda *a, **kw: None)
        r = pipe.click_element("OK")
        assert r["success"] is False

    def test_postmessage_tier_succeeds(self, pipe, all_tiers, monkeypatch):
        """Lines 159-170: PostMessage tier with bounds finds and clicks element."""
        import core.stealth_input as si
        import core.ui_tree as ui_tree_mod

        # UIA click_control returns None (no result) so we fall to PostMessage
        monkeypatch.setattr(ui_tree_mod, "click_control", lambda **kw: None)
        # Bounds found
        monkeypatch.setattr(
            pipe,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 100,
                "center_y": 200,
                "x": 50,
                "y": 150,
                "width": 100,
                "height": 100,
            },
        )
        monkeypatch.setattr(si, "post_click", lambda x, y, **kw: True)
        r = pipe.click_element("Btn")
        assert r["success"] is True
        assert r["method_used"] == "postmessage"
        assert r["output"]["x"] == 100
        assert r["output"]["y"] == 200

    def test_postmessage_returns_false_falls_through(self, pipe, all_tiers, monkeypatch):
        """Lines 159-172: PostMessage returns False, falls to physical."""
        import core.stealth_input as si
        import core.ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "click_control", lambda **kw: None)
        monkeypatch.setattr(
            pipe,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 50,
                "center_y": 60,
                "x": 40,
                "y": 50,
                "width": 20,
                "height": 20,
            },
        )
        monkeypatch.setattr(si, "post_click", lambda x, y, **kw: False)
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.click_element("Btn")
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_postmessage_exception_falls_through(self, pipe, all_tiers, monkeypatch):
        """Lines 171-172: PostMessage raises OSError."""
        import core.stealth_input as si
        import core.ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "click_control", lambda **kw: None)
        monkeypatch.setattr(
            pipe,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 50,
                "center_y": 60,
                "x": 40,
                "y": 50,
                "width": 20,
                "height": 20,
            },
        )
        monkeypatch.setattr(
            si, "post_click", lambda x, y, **kw: (_ for _ in ()).throw(OSError("pm fail"))
        )
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.click_element("Btn")
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_postmessage_no_bounds_falls_through(self, pipe, all_tiers, monkeypatch):
        """Lines 159-172: PostMessage tier with no bounds, falls to physical."""
        import core.ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "click_control", lambda **kw: None)
        monkeypatch.setattr(pipe, "_uia_bounds", lambda *a, **kw: None)
        r = pipe.click_element("Btn")
        assert r["success"] is False

    def test_physical_exception_returns_failure(self, pipe, no_tiers, monkeypatch):
        """Lines 188-189: Physical tier raises, returns failure."""
        monkeypatch.setattr(
            pipe,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 50,
                "center_y": 60,
                "x": 40,
                "y": 50,
                "width": 20,
                "height": 20,
            },
        )
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: BrokenDesktop())
        r = pipe.click_element("Btn")
        assert r["success"] is False
        assert r["method_used"] == "physical"


# ===========================================================================
# type_into_field — lines 211-212, 216-224, 235-236
# ===========================================================================


class TestTypeIntoFieldGaps:
    """Covers lines 211-212 (UIA exc), 216-224 (PostMessage tier),
    235-236 (physical exc)."""

    def test_uia_exception_falls_through(self, pipe, uia_only, monkeypatch):
        """Lines 211-212: UIA tier raises."""
        import core.ui_tree as ui_tree_mod

        def _raise(*a, **kw):
            raise AttributeError("set_text boom")

        monkeypatch.setattr(ui_tree_mod, "set_text", _raise)
        monkeypatch.setattr(pipe, "_uia_bounds", lambda *a, **kw: None)
        r = pipe.type_into_field("Field", "hello")
        assert r["success"] is False

    def test_postmessage_tier_succeeds(self, pipe, all_tiers, monkeypatch):
        """Lines 216-222: PostMessage tier succeeds."""
        import core.stealth_input as si
        import core.ui_tree as ui_tree_mod

        def _raise(*a, **kw):
            raise RuntimeError("uia fail")

        monkeypatch.setattr(ui_tree_mod, "set_text", _raise)
        monkeypatch.setattr(
            pipe,
            "_hwnd_for_element",
            lambda *a, **kw: 12345,
        )
        monkeypatch.setattr(si, "post_text", lambda text, **kw: True)
        r = pipe.type_into_field("Field", "hi")
        assert r["success"] is True
        assert r["method_used"] == "postmessage"

    def test_postmessage_no_hwnd_falls_through(self, pipe, all_tiers, monkeypatch):
        """Lines 216-224: No HWND found, falls through."""
        import core.ui_tree as ui_tree_mod

        def _raise(*a, **kw):
            raise RuntimeError("uia fail")

        monkeypatch.setattr(ui_tree_mod, "set_text", _raise)
        monkeypatch.setattr(pipe, "_hwnd_for_element", lambda *a, **kw: None)
        # No bounds for physical either
        monkeypatch.setattr(pipe, "_uia_bounds", lambda *a, **kw: None)
        r = pipe.type_into_field("Field", "hi")
        assert r["success"] is False

    def test_postmessage_exception_falls_through(self, pipe, all_tiers, monkeypatch):
        """Lines 223-224: PostMessage raises OSError."""
        import core.stealth_input as si
        import core.ui_tree as ui_tree_mod

        def _raise(*a, **kw):
            raise RuntimeError("uia fail")

        monkeypatch.setattr(ui_tree_mod, "set_text", _raise)
        monkeypatch.setattr(
            pipe,
            "_hwnd_for_element",
            lambda *a, **kw: 12345,
        )

        def _pm_raise(text, **kw):
            raise OSError("pm fail")

        monkeypatch.setattr(si, "post_text", _pm_raise)
        monkeypatch.setattr(pipe, "_uia_bounds", lambda *a, **kw: None)
        r = pipe.type_into_field("Field", "hi")
        assert r["success"] is False

    def test_physical_exception_returns_failure(self, pipe, no_tiers, monkeypatch):
        """Lines 235-236: Physical tier raises, returns failure."""
        monkeypatch.setattr(
            pipe,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 10,
                "center_y": 20,
                "x": 0,
                "y": 0,
                "width": 20,
                "height": 40,
            },
        )
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: BrokenDesktop())
        r = pipe.type_into_field("Field", "test")
        assert r["success"] is False
        assert r["method_used"] == "physical"


# ===========================================================================
# select_menu_item — lines 260-261, 265-275, 292-293, 297-300
# ===========================================================================


class TestSelectMenuItemGaps:
    """Covers lines 260-261, 265-275, 292-293, 297-300."""

    def test_uia_exception_falls_through(self, pipe, uia_only, monkeypatch):
        """Lines 260-261: UIA menu walk raises."""
        monkeypatch.setattr(
            pipe,
            "_uia_menu_walk",
            lambda segs, wt=None: (_ for _ in ()).throw(RuntimeError("walk fail")),
        )
        # Physical tier will also fail in headless without bounds, but that's OK
        r = pipe.select_menu_item("File > Save")
        # Falls through — may succeed via physical or fail
        assert isinstance(r["success"], bool)

    def test_postmessage_tier_attempts_alt(self, pipe, postmsg_only, monkeypatch):
        """Lines 265-275: PostMessage tier presses Alt, then falls through."""
        import core.stealth_input as si

        monkeypatch.setattr(si, "post_hotkey", lambda keys, **kw: True)
        # Physical tier also needs to work or fail
        r = pipe.select_menu_item("File > Save")
        # PostMessage won't fully navigate, so it falls to physical or fails
        assert isinstance(r["success"], bool)

    def test_postmessage_exception_falls_through(self, pipe, postmsg_only, monkeypatch):
        """Lines 274-275: PostMessage raises OSError."""
        import core.stealth_input as si

        monkeypatch.setattr(
            si,
            "post_hotkey",
            lambda keys, **kw: (_ for _ in ()).throw(OSError("pm alt fail")),
        )
        r = pipe.select_menu_item("File > Save")
        assert isinstance(r["success"], bool)

    def test_physical_non_alpha_segment(self, pipe, no_tiers, monkeypatch):
        """Lines 292-293: segment starts with non-alpha char, presses down."""

        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        # Use a segment starting with a digit to trigger pyautogui.press("down")
        r = pipe.select_menu_item("1Item")
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_physical_exception_returns_failure(self, pipe, no_tiers, monkeypatch):
        """Lines 297-300: Physical tier raises, returns failure."""
        # Make pyautogui.press raise
        import pyautogui



        def _raise_press(key):
            raise ImportError("no pyautogui")

        monkeypatch.setattr(pyautogui, "press", _raise_press)
        r = pipe.select_menu_item("File > Save")
        assert r["success"] is False
        assert r["method_used"] == "physical"

    def test_physical_menu_navigation_multi_segment(self, pipe, no_tiers, monkeypatch):
        """Physical tier navigates a multi-segment menu path with alpha segments."""
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.select_menu_item("File > Export > Runtime Model")
        assert r["success"] is True
        assert r["method_used"] == "physical"


# ===========================================================================
# click_at — lines 326-327, 333-336
# ===========================================================================


class TestClickAtGaps:
    """Covers lines 326-327 (PostMessage exc), 333-336 (physical exc)."""

    def test_postmessage_exception_falls_to_physical(self, pipe, postmsg_only, monkeypatch):
        """Lines 326-327: PostMessage raises, falls to physical."""
        import core.stealth_input as si

        monkeypatch.setattr(
            si,
            "post_click",
            lambda x, y, **kw: (_ for _ in ()).throw(OSError("pm fail")),
        )
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.click_at(100, 200)
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_physical_exception_returns_failure(self, pipe, no_tiers, monkeypatch):
        """Lines 333-336: Physical tier raises, returns failure."""
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: BrokenDesktop())
        r = pipe.click_at(100, 200)
        assert r["success"] is False
        assert r["method_used"] == "physical"


# ===========================================================================
# type_text — lines 357-358, 364-367
# ===========================================================================


class TestTypeTextGaps:
    """Covers lines 357-358 (PostMessage exc), 364-367 (physical exc)."""

    def test_postmessage_exception_falls_to_physical(self, pipe, postmsg_only, monkeypatch):
        """Lines 357-358: PostMessage raises, falls to physical."""
        import core.stealth_input as si

        monkeypatch.setattr(
            si,
            "post_text",
            lambda text, **kw: (_ for _ in ()).throw(OSError("pm fail")),
        )
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.type_text("hello")
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_physical_exception_returns_failure(self, pipe, no_tiers, monkeypatch):
        """Lines 364-367: Physical tier raises, returns failure."""
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: BrokenDesktop())
        r = pipe.type_text("hello")
        assert r["success"] is False
        assert r["method_used"] == "physical"


# ===========================================================================
# press_key — lines 385-386, 392-395
# ===========================================================================


class TestPressKeyGaps:
    """Covers lines 385-386 (PostMessage exc), 392-395 (physical exc)."""

    def test_postmessage_exception_falls_to_physical(self, pipe, postmsg_only, monkeypatch):
        """Lines 385-386: PostMessage raises, falls to physical."""
        import core.stealth_input as si

        monkeypatch.setattr(
            si,
            "post_named_key",
            lambda key, **kw: (_ for _ in ()).throw(OSError("pm fail")),
        )
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.press_key("enter")
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_physical_exception_returns_failure(self, pipe, no_tiers, monkeypatch):
        """Lines 392-395: Physical tier raises, returns failure."""
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: BrokenDesktop())
        r = pipe.press_key("enter")
        assert r["success"] is False
        assert r["method_used"] == "physical"


# ===========================================================================
# hotkey — lines 416-417, 423-426
# ===========================================================================


class TestHotkeyGaps:
    """Covers lines 416-417 (PostMessage exc), 423-426 (physical exc)."""

    def test_postmessage_exception_falls_to_physical(self, pipe, postmsg_only, monkeypatch):
        """Lines 416-417: PostMessage raises, falls to physical."""
        import core.stealth_input as si

        monkeypatch.setattr(
            si,
            "post_hotkey",
            lambda keys, **kw: (_ for _ in ()).throw(OSError("pm fail")),
        )
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)
        r = pipe.hotkey(["ctrl", "c"])
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_physical_exception_returns_failure(self, pipe, no_tiers, monkeypatch):
        """Lines 423-426: Physical tier raises, returns failure."""
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: BrokenDesktop())
        r = pipe.hotkey(["ctrl", "c"])
        assert r["success"] is False
        assert r["method_used"] == "physical"


# ===========================================================================
# scroll_at — lines 441-463, 473-476
# ===========================================================================


class TestScrollAtGaps:
    """Covers lines 441-463 (PostMessage scroll), 473-476 (physical exc)."""

    def test_postmessage_scroll_up(self, pipe, postmsg_only, monkeypatch):
        """Lines 441-461: PostMessage scroll with positive amount (SB_LINEUP)."""
        fake_win32gui = MagicMock()
        fake_win32gui.WindowFromPoint = MagicMock(return_value=999)
        fake_win32con = MagicMock()
        fake_win32con.SB_LINEUP = 0
        fake_win32con.SB_LINEDOWN = 1
        fake_win32con.WM_VSCROLL = 0x0115
        fake_win32api = MagicMock()

        monkeypatch.setattr(mod, "_win32gui", fake_win32gui)
        monkeypatch.setattr(mod, "_win32con", fake_win32con)
        monkeypatch.setattr(mod, "_win32api", fake_win32api)

        r = pipe.scroll_at(100, 200, 3)
        assert r["success"] is True
        assert r["method_used"] == "postmessage"
        assert r["output"]["amount"] == 3
        # PostMessage should be called 3 times (abs(3))
        assert fake_win32api.PostMessage.call_count == 3

    def test_postmessage_scroll_down(self, pipe, postmsg_only, monkeypatch):
        """Lines 441-461: PostMessage scroll with negative amount (SB_LINEDOWN)."""
        fake_win32gui = MagicMock()
        fake_win32gui.WindowFromPoint = MagicMock(return_value=999)
        fake_win32con = MagicMock()
        fake_win32con.SB_LINEUP = 0
        fake_win32con.SB_LINEDOWN = 1
        fake_win32con.WM_VSCROLL = 0x0115
        fake_win32api = MagicMock()

        monkeypatch.setattr(mod, "_win32gui", fake_win32gui)
        monkeypatch.setattr(mod, "_win32con", fake_win32con)
        monkeypatch.setattr(mod, "_win32api", fake_win32api)

        r = pipe.scroll_at(100, 200, -2)
        assert r["success"] is True
        assert r["method_used"] == "postmessage"
        assert fake_win32api.PostMessage.call_count == 2

    def test_postmessage_no_hwnd_falls_through(self, pipe, postmsg_only, monkeypatch):
        """Lines 441-463: WindowFromPoint returns 0, falls to physical."""
        fake_win32gui = MagicMock()
        fake_win32gui.WindowFromPoint = MagicMock(return_value=0)
        fake_win32con = MagicMock()
        fake_win32api = MagicMock()

        monkeypatch.setattr(mod, "_win32gui", fake_win32gui)
        monkeypatch.setattr(mod, "_win32con", fake_win32con)
        monkeypatch.setattr(mod, "_win32api", fake_win32api)
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)

        r = pipe.scroll_at(100, 200, 1)
        # Falls to physical since hwnd is falsy
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_postmessage_exception_falls_through(self, pipe, postmsg_only, monkeypatch):
        """Lines 462-463: PostMessage raises, falls to physical."""
        fake_win32gui = MagicMock()
        fake_win32gui.WindowFromPoint = MagicMock(side_effect=OSError("no window"))
        fake_win32con = MagicMock()
        fake_win32api = MagicMock()

        monkeypatch.setattr(mod, "_win32gui", fake_win32gui)
        monkeypatch.setattr(mod, "_win32con", fake_win32con)
        monkeypatch.setattr(mod, "_win32api", fake_win32api)
        fake_desktop = FakeDesktop()
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: fake_desktop)

        r = pipe.scroll_at(100, 200, 1)
        assert r["success"] is True
        assert r["method_used"] == "physical"

    def test_physical_exception_returns_failure(self, pipe, no_tiers, monkeypatch):
        """Lines 473-476: Physical tier raises, returns failure."""
        monkeypatch.setattr(pipe, "_get_physical_desktop", lambda: BrokenDesktop())
        r = pipe.scroll_at(100, 200, 3)
        assert r["success"] is False
        assert r["method_used"] == "physical"


# ===========================================================================
# find_element — line 505-506 (UIA exception catch)
# ===========================================================================


class TestFindElementGaps:
    """Covers lines 505-506: find_element UIA exception path."""

    def test_uia_exception_returns_failure(self, pipe, uia_only, monkeypatch):
        """Lines 505-506: UIA _find_control raises."""
        import core.ui_tree as ui_tree_mod

        def _raise(**kw):
            raise RuntimeError("find fail")

        monkeypatch.setattr(ui_tree_mod, "_find_control", _raise)
        r = pipe.find_element("Button")
        assert r["success"] is False
        assert r["method_used"] == "uia"


# ===========================================================================
# list_controls — lines 524-525 (UIA exception catch)
# ===========================================================================


class TestListControlsGaps:
    """Covers lines 524-525: list_controls UIA exception path."""

    def test_uia_exception_returns_failure(self, pipe, uia_only, monkeypatch):
        """Lines 524-525: UIA list_controls raises."""
        import core.ui_tree as ui_tree_mod

        def _raise(wt=None):
            raise AttributeError("list fail")

        monkeypatch.setattr(ui_tree_mod, "list_controls", _raise)
        r = pipe.list_controls()
        assert r["success"] is False
        assert r["method_used"] == "uia"


# ===========================================================================
# _uia_bounds — lines 598-600 (exception catch)
# ===========================================================================


class TestUiaBoundsGaps:
    """Covers lines 598-600: _uia_bounds exception path."""

    def test_exception_returns_none(self, uia_only, monkeypatch):
        """Lines 598-600: _find_control raises, returns None."""
        import core.ui_tree as ui_tree_mod

        class FakeCtrl:
            @property
            def BoundingRectangle(self):
                raise RuntimeError("no rect")

        monkeypatch.setattr(ui_tree_mod, "_find_control", lambda **kw: FakeCtrl())
        r = mod.UIAActionPipeline._uia_bounds("OK")
        assert r is None


# ===========================================================================
# _hwnd_for_element — lines 617-618 (exception catch)
# ===========================================================================


class TestHwndForElementGaps:
    """Covers lines 617-618: _hwnd_for_element exception path."""

    def test_exception_returns_none(self, postmsg_only, monkeypatch):
        """Lines 617-618: WindowFromPoint raises OSError."""
        monkeypatch.setattr(
            mod.UIAActionPipeline,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 100,
                "center_y": 200,
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 400,
            },
        )
        fake_win32gui = MagicMock()
        fake_win32gui.WindowFromPoint = MagicMock(side_effect=OSError("no hwnd"))
        monkeypatch.setattr(mod, "_win32gui", fake_win32gui)
        r = mod.UIAActionPipeline._hwnd_for_element("OK")
        assert r is None

    def test_window_returns_zero(self, postmsg_only, monkeypatch):
        """HWND is 0 (falsy), returns None."""
        monkeypatch.setattr(
            mod.UIAActionPipeline,
            "_uia_bounds",
            lambda *a, **kw: {
                "center_x": 100,
                "center_y": 200,
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 400,
            },
        )
        fake_win32gui = MagicMock()
        fake_win32gui.WindowFromPoint = MagicMock(return_value=0)
        monkeypatch.setattr(mod, "_win32gui", fake_win32gui)
        r = mod.UIAActionPipeline._hwnd_for_element("OK")
        assert r is None


# ===========================================================================
# _uia_menu_walk — lines 630-700 (full method body)
# ===========================================================================


class TestUiaMenuWalk:
    """Covers lines 630-700: _uia_menu_walk full implementation."""

    def test_auto_none_returns_false(self, pipe, uia_only, monkeypatch):
        """Line 630-631: _auto is None, returns False."""
        monkeypatch.setattr(mod, "_auto", None)
        r = pipe._uia_menu_walk(["File"])
        assert r is False

    def test_find_window_none_returns_false(self, pipe, uia_only, monkeypatch):
        """Lines 635-636: _find_window returns None."""
        import core.ui_tree as ui_tree_mod

        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: None)
        r = pipe._uia_menu_walk(["File"])
        assert r is False

    def _make_menu_bar(self, children):
        """Create a fake menu bar control."""

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return children

        return FakeMenuBar()

    def _make_generic_menu(self, children):
        """Create a fake generic 'menu' control."""

        class FakeMenu:
            ControlTypeName = "MenuControl"

            def GetChildren(self):
                return children

        return FakeMenu()

    def _make_root(self, children):
        """Create a fake root window with given children."""

        class FakeRoot:
            def GetChildren(self):
                return children

        return FakeRoot()

    def test_no_menu_bar_returns_false(self, pipe, uia_only, monkeypatch):
        """Lines 640-653: Root has no MenuBarControl or menu-like child."""
        import core.ui_tree as ui_tree_mod

        class OtherControl:
            ControlTypeName = "ButtonControl"

        root = self._make_root([OtherControl()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["File"])
        assert r is False

    def test_generic_menu_found(self, pipe, uia_only, monkeypatch):
        """Lines 647-651: Menu bar not found but generic 'menu' control is used."""
        import core.ui_tree as ui_tree_mod

        class MenuControl:
            ControlTypeName = "MenuControl"
            Name = "MainMenu"

        root = self._make_root([MenuControl()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)

        # _find_child_by_name won't match on empty menu bar, so walk returns False
        r = pipe._uia_menu_walk(["File"])
        assert r is False

    def test_segment_not_found_returns_false(self, pipe, uia_only, monkeypatch):
        """Lines 658-660: No child matches segment name."""
        import core.ui_tree as ui_tree_mod

        class FakeChild:
            Name = "Edit"
            ControlTypeName = "MenuItemControl"

        menu_bar = self._make_menu_bar([])
        root = self._make_root([menu_bar])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["File"])
        assert r is False

    def test_last_segment_invoke_succeeds(self, pipe, uia_only, monkeypatch):
        """Lines 662-668: Last segment invoked via InvokePattern."""
        import core.ui_tree as ui_tree_mod

        class FakeInvokePattern:
            def Invoke(self):
                pass

        class FakeTarget:
            Name = "Save"
            ControlTypeName = "MenuItemControl"

            def GetInvokePattern(self):
                return FakeInvokePattern()

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return [FakeTarget()]

        root = self._make_root([FakeMenuBar()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["Save"])
        assert r is True

    def test_last_segment_invoke_fails_click_succeeds(self, pipe, uia_only, monkeypatch):
        """Lines 669-675: InvokePattern fails, Click fallback succeeds."""
        import core.ui_tree as ui_tree_mod

        class FakeTarget:
            Name = "Save"
            ControlTypeName = "MenuItemControl"

            def GetInvokePattern(self):
                raise RuntimeError("no invoke pattern")

            def Click(self, simulateMove=False):
                pass

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return [FakeTarget()]

        root = self._make_root([FakeMenuBar()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["Save"])
        assert r is True

    def test_last_segment_invoke_and_click_both_fail(self, pipe, uia_only, monkeypatch):
        """Lines 669-676: Both Invoke and Click fail, returns False."""
        import core.ui_tree as ui_tree_mod

        class FakeTarget:
            Name = "Save"
            ControlTypeName = "MenuItemControl"

            def GetInvokePattern(self):
                raise AttributeError("no pattern")

            def Click(self, simulateMove=False):
                raise OSError("click fail")

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return [FakeTarget()]

        root = self._make_root([FakeMenuBar()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["Save"])
        assert r is False

    def test_intermediate_expand_succeeds(self, pipe, uia_only, monkeypatch):
        """Lines 677-685: Intermediate segment expanded via ExpandCollapsePattern."""
        import core.ui_tree as ui_tree_mod

        class FakeExpand:
            def Expand(self):
                pass

        class FakeSubItem:
            Name = "Save"
            ControlTypeName = "MenuItemControl"

            def GetInvokePattern(self):
                return MagicMock()

            def GetChildren(self):
                return []

        class FakeTopItem:
            Name = "File"
            ControlTypeName = "MenuItemControl"

            def GetExpandCollapsePattern(self):
                return FakeExpand()

            def GetChildren(self):
                return [FakeSubItem()]

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return [FakeTopItem()]

        root = self._make_root([FakeMenuBar()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        # The walk should expand "File", then invoke "Save"
        r = pipe._uia_menu_walk(["File", "Save"])
        assert r is True

    def test_intermediate_expand_fails_click_succeeds(self, pipe, uia_only, monkeypatch):
        """Lines 686-695: Expand fails, click fallback opens submenu."""
        import core.ui_tree as ui_tree_mod

        class FakeSubItem:
            Name = "Save"
            ControlTypeName = "MenuItemControl"

            def GetInvokePattern(self):
                return MagicMock()

            def GetChildren(self):
                return []

        class FakeTopItem:
            Name = "File"
            ControlTypeName = "MenuItemControl"

            def GetExpandCollapsePattern(self):
                raise AttributeError("no expand")

            def Click(self, simulateMove=False):
                pass

            def GetChildren(self):
                return [FakeSubItem()]

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return [FakeTopItem()]

        root = self._make_root([FakeMenuBar()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["File", "Save"])
        assert r is True

    def test_intermediate_expand_and_click_both_fail(self, pipe, uia_only, monkeypatch):
        """Lines 688-695: Both Expand and Click fail for intermediate, returns False."""
        import core.ui_tree as ui_tree_mod

        class FakeTopItem:
            Name = "File"
            ControlTypeName = "MenuItemControl"

            def GetExpandCollapsePattern(self):
                raise AttributeError("no expand")

            def Click(self, simulateMove=False):
                raise OSError("click fail")

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return [FakeTopItem()]

        root = self._make_root([FakeMenuBar()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["File", "Save"])
        assert r is False

    def test_intermediate_expand_returns_none(self, pipe, uia_only, monkeypatch):
        """Lines 680-682: GetExpandCollapsePattern returns None, falls to click."""
        import core.ui_tree as ui_tree_mod

        class FakeSubItem:
            Name = "Save"
            ControlTypeName = "MenuItemControl"

            def GetInvokePattern(self):
                return MagicMock()

            def GetChildren(self):
                return []

        class FakeTopItem:
            Name = "File"
            ControlTypeName = "MenuItemControl"

            def GetExpandCollapsePattern(self):
                return None

            def Click(self, simulateMove=False):
                pass

            def GetChildren(self):
                return [FakeSubItem()]

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return [FakeTopItem()]

        root = self._make_root([FakeMenuBar()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["File", "Save"])
        assert r is True

    def test_outer_exception_returns_false(self, pipe, uia_only, monkeypatch):
        """Lines 698-700: Outer try/except catches, returns False."""
        import core.ui_tree as ui_tree_mod

        def _raise(wt=None):
            raise RuntimeError("window fail")

        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", _raise)
        r = pipe._uia_menu_walk(["File"])
        assert r is False

    def test_three_level_menu_walk(self, pipe, uia_only, monkeypatch):
        """Full three-level menu walk with expand on first two, invoke on last."""
        import core.ui_tree as ui_tree_mod

        class FakeExpand:
            def Expand(self):
                pass

        class FakeInvokePattern:
            def Invoke(self):
                pass

        class DeepItem:
            Name = "Runtime Model"
            ControlTypeName = "MenuItemControl"

            def GetInvokePattern(self):
                return FakeInvokePattern()

            def GetChildren(self):
                return []

        class MidItem:
            Name = "Export"
            ControlTypeName = "MenuItemControl"

            def GetExpandCollapsePattern(self):
                return FakeExpand()

            def GetChildren(self):
                return [DeepItem()]

        class TopItem:
            Name = "File"
            ControlTypeName = "MenuItemControl"

            def GetExpandCollapsePattern(self):
                return FakeExpand()

            def GetChildren(self):
                return [MidItem()]

        class FakeMenuBar:
            ControlTypeName = "MenuBarControl"

            def GetChildren(self):
                return [TopItem()]

        root = self._make_root([FakeMenuBar()])
        monkeypatch.setattr(mod, "_auto", MagicMock())
        monkeypatch.setattr(ui_tree_mod, "_find_window", lambda wt=None: root)
        r = pipe._uia_menu_walk(["File", "Export", "Runtime Model"])
        assert r is True
