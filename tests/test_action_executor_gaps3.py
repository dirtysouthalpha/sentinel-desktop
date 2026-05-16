"""Gap tests for action_executor.py — approval callback rejection, pre_action_callback
failure (async), handler exceptions (async + sync), click error paths, click_text stealth/
UIA fallback failures, set_text click+type fallback, click_image stealth, type_text
clipboard fallback, drag stealth path, and various error-only handler branches."""

import asyncio
from unittest.mock import MagicMock

import pytest

import core.desktop as desktop_mod
from core.action_executor import ActionExecutor

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


class FakeDesktop:
    """Minimal desktop stub that records calls."""

    def __init__(self):
        self.calls = []

    def click(self, *a, **kw):
        self.calls.append(("click", a, kw))

    def type_text(self, text, **_):
        self.calls.append(("type_text", text))

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))

    def scroll(self, *a, **kw):
        self.calls.append(("scroll", a, kw))

    def drag(self, *a, **kw):
        self.calls.append(("drag", a, kw))

    def click_image(self, template_path, confidence=0.8):
        self.calls.append(("click_image", template_path, confidence))
        return True


@pytest.fixture
def fake_executor(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    return ActionExecutor


def _make_executor(**kw):
    """Create an ActionExecutor with FakeDesktop patched in."""
    original = desktop_mod.DesktopEngine
    desktop_mod.DesktopEngine = FakeDesktop
    try:
        ex = ActionExecutor(**kw)
    finally:
        desktop_mod.DesktopEngine = original
    return ex


# ===================================================================
# 1. Lines 122-130: approval_callback rejection in execute()
# ===================================================================


class TestApprovalCallbackRejection:
    """Async approval_callback returning False should reject action."""

    def test_rejected_action_returns_error(self, fake_executor):
        async def reject(_action):
            return False

        ex = fake_executor(approval_callback=reject)
        result = asyncio.get_event_loop().run_until_complete(
            ex.execute({"action": "click", "x": 10, "y": 20})
        )
        assert result["success"] is False
        assert result["error"] == "rejected"
        assert "rejected" in result["output"].lower()

    def test_rejected_action_is_logged(self, fake_executor):
        async def reject(_action):
            return False

        ex = fake_executor(approval_callback=reject)
        asyncio.get_event_loop().run_until_complete(ex.execute({"action": "click", "x": 1, "y": 2}))
        assert len(ex.log) == 1
        assert ex.log[0]["success"] is False


# ===================================================================
# 2. Lines 134-137: pre_action_callback failure in execute() (async)
# ===================================================================


class TestPreActionCallbackFailureAsync:
    """In async execute(), a failing pre_action_callback should not block dispatch."""

    def test_pre_action_callback_exception_logged_but_action_succeeds(self, fake_executor):
        def boom(_a):
            raise RuntimeError("overlay crashed")

        ex = fake_executor(pre_action_callback=boom)
        result = asyncio.get_event_loop().run_until_complete(
            ex.execute({"action": "click", "x": 5, "y": 5})
        )
        assert result["success"] is True


# ===================================================================
# 3. Lines 155-157: handler exception in execute() (async path)
# ===================================================================


class TestHandlerExceptionAsync:
    """When a handler raises during async execute(), an error result is returned."""

    def test_handler_exception_returns_error_result(self, fake_executor):
        # Give the instance its own dispatch table to avoid polluting the class.
        ex = fake_executor()
        ex._dispatch_table = dict(ex._dispatch_table)
        ex._dispatch_table["note"] = lambda self, **kw: (_ for _ in ()).throw(
            RuntimeError("handler exploded")
        )
        result = asyncio.get_event_loop().run_until_complete(
            ex.execute({"action": "note", "text": "boom"})
        )
        assert result["success"] is False
        assert "RuntimeError" in result["error"]


# ===================================================================
# 4. Lines 190-192: handler exception in execute_sync()
# ===================================================================


class TestHandlerExceptionSync:
    """When a handler raises during execute_sync(), an error result is returned."""

    def test_handler_exception_returns_error_result(self, fake_executor):
        # Give the instance its own dispatch table to avoid polluting the class.
        ex = fake_executor()
        ex._dispatch_table = dict(ex._dispatch_table)
        ex._dispatch_table["note"] = lambda self, **kw: (_ for _ in ()).throw(
            OSError("sync handler exploded")
        )
        result = ex.execute_sync({"action": "note", "text": "boom"})
        assert result["success"] is False
        assert "OSError" in result["error"]


# ===================================================================
# 5. Lines 235-236: click error path (stealth + physical failure)
# ===================================================================


class TestClickErrorPath:
    """Both stealth and physical click fail -> error result."""

    def test_click_exception_returns_click_failed(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)
        monkeypatch.setattr(ae_mod.stealth_input, "post_click", MagicMock(return_value=False))

        # Make FakeDesktop.click raise
        def click_boom(*a, **kw):
            raise RuntimeError("mouse broken")

        ex = fake_executor()
        ex._desktop.click = click_boom
        result = ex._click(x=10, y=20)
        assert result["success"] is False
        assert result["error"] == "click_failed"
        assert "click error" in result["output"]


# ===================================================================
# 6. Line 269: click_text stealth fallback
# ===================================================================


class TestClickTextStealthFallback:
    """OCR finds text, stealth PostMessage succeeds -> returns stealth result."""

    def test_stealth_click_text_success(self, monkeypatch):
        import core.action_executor as ae_mod
        from core import ocr as ocr_mod

        monkeypatch.setattr(ocr_mod, "find_text", lambda text, fuzzy=True: (100, 200))
        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)
        monkeypatch.setattr(ae_mod.stealth_input, "post_click", MagicMock(return_value=True))

        ex = _make_executor(stealth=True)
        result = ex._click_text(text="Submit")
        assert result["success"] is True
        assert "stealth" in result["output"]
        assert result["position"] == [100, 200]


# ===================================================================
# 7. Lines 285-301: click_text UIA fallback failure paths
# ===================================================================


class TestClickTextUIAFallbackFailure:
    """OCR finds nothing; UIA click_control raises -> falls through to text_not_found."""

    def test_uia_click_raises_then_text_not_found(self, monkeypatch):
        from core import ocr as ocr_mod
        from core import ui_tree as ui_tree_mod

        monkeypatch.setattr(ocr_mod, "find_text", lambda text, fuzzy=True: None)
        monkeypatch.setattr(
            ui_tree_mod, "click_control", MagicMock(side_effect=RuntimeError("UIA crashed"))
        )
        ex = _make_executor()
        result = ex._click_text(text="Missing")
        assert result["success"] is False
        assert result["error"] == "text_not_found"

    def test_uia_click_returns_none_text_not_found(self, monkeypatch):
        """OCR finds nothing, UIA click returns None -> text_not_found."""
        from core import ocr as ocr_mod
        from core import ui_tree as ui_tree_mod

        monkeypatch.setattr(ocr_mod, "find_text", lambda text, fuzzy=True: None)
        monkeypatch.setattr(ui_tree_mod, "click_control", MagicMock(return_value=None))
        ex = _make_executor()
        result = ex._click_text(text="Invisible")
        assert result["success"] is False
        assert result["error"] == "text_not_found"

    def test_outer_exception_returns_click_text_failed(self, monkeypatch):
        """OCR itself raises -> outer except catches click_text_failed."""
        from core import ocr as ocr_mod

        monkeypatch.setattr(ocr_mod, "find_text", MagicMock(side_effect=OSError("ocr engine down")))
        ex = _make_executor()
        result = ex._click_text(text="Anything")
        assert result["success"] is False
        assert result["error"] == "click_text_failed"

    def test_uia_click_success(self, monkeypatch):
        """OCR finds nothing, UIA succeeds with a position."""
        from core import ocr as ocr_mod
        from core import ui_tree as ui_tree_mod

        monkeypatch.setattr(ocr_mod, "find_text", lambda text, fuzzy=True: None)
        monkeypatch.setattr(ui_tree_mod, "click_control", MagicMock(return_value=(50, 60)))
        ex = _make_executor()
        result = ex._click_text(text="OK")
        assert result["success"] is True
        assert result.get("fallback") == "uia"
        assert result["position"] == [50, 60]


# ===================================================================
# 8. Lines 519-524: set_text click+type fallback
# ===================================================================


class TestSetTextClickTypeFallback:
    """UIA set_text fails; click+type fallback via list_controls match."""

    def test_fallback_by_name_match(self, monkeypatch):
        import time

        from core import ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "set_text", MagicMock(return_value=False))
        monkeypatch.setattr(
            ui_tree_mod,
            "list_controls",
            lambda **kw: [
                {
                    "name": "SearchBox",
                    "control_type": "Edit",
                    "automation_id": "sb1",
                    "x": 10,
                    "y": 20,
                    "width": 200,
                    "height": 30,
                    "is_offscreen": False,
                }
            ],
        )
        monkeypatch.setattr(time, "sleep", MagicMock())
        ex = _make_executor()
        result = ex._set_text(text="hello", name="SearchBox")
        assert result["success"] is True
        assert result.get("fallback") == "click_and_type"

    def test_fallback_by_automation_id_match(self, monkeypatch):
        import time

        from core import ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "set_text", MagicMock(return_value=False))
        monkeypatch.setattr(
            ui_tree_mod,
            "list_controls",
            lambda **kw: [
                {
                    "name": "SomeField",
                    "control_type": "Edit",
                    "automation_id": "email_input",
                    "x": 10,
                    "y": 20,
                    "width": 200,
                    "height": 30,
                    "is_offscreen": False,
                }
            ],
        )
        monkeypatch.setattr(time, "sleep", MagicMock())
        ex = _make_executor()
        result = ex._set_text(text="test@example.com", automation_id="email_input")
        assert result["success"] is True
        assert result.get("fallback") == "click_and_type"

    def test_fallback_by_edit_control_type_no_name_no_id(self, monkeypatch):
        import time

        from core import ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "set_text", MagicMock(return_value=False))
        monkeypatch.setattr(
            ui_tree_mod,
            "list_controls",
            lambda **kw: [
                {
                    "name": "",
                    "control_type": "Edit",
                    "automation_id": "",
                    "x": 10,
                    "y": 20,
                    "width": 200,
                    "height": 30,
                    "is_offscreen": False,
                }
            ],
        )
        monkeypatch.setattr(time, "sleep", MagicMock())
        ex = _make_executor()
        result = ex._set_text(text="hello world")
        assert result["success"] is True
        assert result.get("fallback") == "click_and_type"

    def test_fallback_exception_returns_control_not_found(self, monkeypatch):
        """list_controls raises during fallback -> falls through to control_not_found."""
        from core import ui_tree as ui_tree_mod

        monkeypatch.setattr(ui_tree_mod, "set_text", MagicMock(return_value=False))
        monkeypatch.setattr(
            ui_tree_mod, "list_controls", MagicMock(side_effect=RuntimeError("UIA crashed"))
        )
        ex = _make_executor()
        result = ex._set_text(text="hello", name="Field")
        assert result["success"] is False
        assert result["error"] == "control_not_found"

    def test_outer_exception_returns_set_text_failed(self, monkeypatch):
        """ui_tree.set_text itself raises unexpectedly -> set_text_failed."""
        from core import ui_tree as ui_tree_mod

        monkeypatch.setattr(
            ui_tree_mod, "set_text", MagicMock(side_effect=OSError("access denied"))
        )
        ex = _make_executor()
        result = ex._set_text(text="hello", name="Field")
        assert result["success"] is False
        assert result["error"] == "set_text_failed"


# ===================================================================
# 9. Lines 565-570: click_image stealth path
# ===================================================================


class TestClickImageStealthPath:
    """Stealth mode: find_template succeeds + post_click succeeds -> stealth result."""

    def test_stealth_click_image_success(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "find_template", lambda t, c=0.8: (150, 250))
        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)
        monkeypatch.setattr(ae_mod.stealth_input, "post_click", MagicMock(return_value=True))

        ex = _make_executor(stealth=True)
        result = ex._click_image(template_path="btn.png")
        assert result["success"] is True
        assert "stealth" in result["output"]

    def test_stealth_find_fails_physical_fallback(self, monkeypatch):
        """Stealth mode but find_template returns None -> physical fallback."""
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "find_template", lambda t, c=0.8: None)
        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)

        ex = _make_executor(stealth=True)
        # FakeDesktop.click_image returns True
        result = ex._click_image(template_path="btn.png")
        assert result["success"] is True
        assert "stealth" not in result["output"]

    def test_click_image_exception(self, monkeypatch):
        """find_template raises and desktop.click_image also raises -> click_image_failed."""
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "find_template", MagicMock(side_effect=RuntimeError("corrupt")))
        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: False)

        ex = _make_executor()
        # FakeDesktop.click_image normally returns True; make it raise too so
        # the exception path in _click_image is hit.
        ex._desktop.click_image = MagicMock(side_effect=RuntimeError("no desktop"))
        result = ex._click_image(template_path="bad.png")
        assert result["success"] is False
        assert result["error"] == "click_image_failed"


# ===================================================================
# 10. Lines 597-613: type_text pyautogui failure + clipboard fallback
# ===================================================================


class TestTypeTextClipboardFallback:
    """When desktop.type_text fails, clipboard fallback is attempted."""

    def test_pyautogui_fails_clipboard_succeeds(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: False)

        ex = _make_executor()
        # Make FakeDesktop.type_text raise
        ex._desktop.type_text = MagicMock(side_effect=RuntimeError("pyautogui broke"))

        mock_pyperclip = MagicMock()
        mock_pyperclip.copy = MagicMock()
        monkeypatch.setitem(__import__("sys").modules, "pyperclip", mock_pyperclip)

        result = ex._type_text(text="hello world")
        assert result["success"] is True
        assert result.get("fallback") == "clipboard"
        mock_pyperclip.copy.assert_called_once_with("hello world")

    def test_pyautogui_and_clipboard_both_fail(self, monkeypatch):
        """Both pyautogui and clipboard fail -> type_failed error."""
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: False)

        ex = _make_executor()
        ex._desktop.type_text = MagicMock(side_effect=RuntimeError("pyautogui broke"))
        ex._desktop.hotkey = MagicMock(side_effect=RuntimeError("hotkey broke"))

        mock_pyperclip = MagicMock()
        mock_pyperclip.copy = MagicMock(side_effect=RuntimeError("no clipboard"))
        monkeypatch.setitem(__import__("sys").modules, "pyperclip", mock_pyperclip)

        result = ex._type_text(text="hello")
        assert result["success"] is False
        assert result["error"] == "type_failed"


# ===================================================================
# 11. Lines 659-687: drag stealth path
# ===================================================================


class TestDragStealthPath:
    """Stealth drag uses PostMessage mouse_down/move/up simulation."""

    def test_stealth_drag_success(self, monkeypatch):
        """Stealth drag with PostMessage succeeds."""
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)

        mock_win32gui = MagicMock()
        mock_win32gui.WindowFromPoint.return_value = 12345
        mock_win32gui.ScreenToClient.side_effect = [
            (10, 20),  # source client coords
            (30, 40),  # dest client coords
        ]
        mock_win32api = MagicMock()
        mock_win32con = MagicMock()
        mock_win32con.MK_LBUTTON = 1
        mock_win32con.WM_LBUTTONDOWN = 0x0201
        mock_win32con.WM_LBUTTONUP = 0x0202
        mock_win32con.WM_MOUSEMOVE = 0x0200
        mock_win32con.MK_RBUTTON = 2

        import time as _time

        monkeypatch.setattr(_time, "sleep", MagicMock())

        monkeypatch.setitem(__import__("sys").modules, "win32gui", mock_win32gui)
        monkeypatch.setitem(__import__("sys").modules, "win32api", mock_win32api)
        monkeypatch.setitem(__import__("sys").modules, "win32con", mock_win32con)

        ex = _make_executor(stealth=True)
        result = ex._drag(from_x=10, from_y=20, to_x=30, to_y=40, duration=0.02)
        assert result["success"] is True
        assert "stealth" in result["output"]
        mock_win32api.PostMessage.assert_called()

    def test_stealth_drag_failure_falls_back_to_physical(self, monkeypatch):
        """Stealth drag fails (OSError) -> physical drag succeeds."""
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)

        # win32gui.WindowFromPoint raises -> stealth fails, physical fallback
        mock_win32gui = MagicMock()
        mock_win32gui.WindowFromPoint.side_effect = OSError("no window")
        mock_win32con = MagicMock()
        mock_win32api = MagicMock()

        monkeypatch.setitem(__import__("sys").modules, "win32gui", mock_win32gui)
        monkeypatch.setitem(__import__("sys").modules, "win32con", mock_win32con)
        monkeypatch.setitem(__import__("sys").modules, "win32api", mock_win32api)

        ex = _make_executor(stealth=True)
        result = ex._drag(from_x=10, from_y=20, to_x=30, to_y=40, duration=0.01)
        assert result["success"] is True
        assert "stealth" not in result["output"]
        # Physical drag was called on FakeDesktop
        assert any(c[0] == "drag" for c in ex._desktop.calls)

    def test_physical_drag_failure(self, monkeypatch):
        """Both stealth (unavailable) and physical drag fail."""
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: False)

        ex = _make_executor()
        ex._desktop.drag = MagicMock(side_effect=OSError("mouse broken"))

        result = ex._drag(from_x=10, from_y=20, to_x=30, to_y=40)
        assert result["success"] is False
        assert result["error"] == "drag_failed"


# ===================================================================
# Additional uncovered lines
# ===================================================================


class TestPressKeyStealth:
    """Stealth mode: post_named_key succeeds -> stealth result."""

    def test_stealth_press_key(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)
        monkeypatch.setattr(ae_mod.stealth_input, "post_named_key", MagicMock(return_value=True))

        ex = _make_executor(stealth=True)
        result = ex._press_key(key="enter")
        assert result["success"] is True
        assert "stealth" in result["output"]

    def test_press_key_exception(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: False)

        ex = _make_executor()
        ex._desktop.press_key = MagicMock(side_effect=RuntimeError("key error"))

        result = ex._press_key(key="enter")
        assert result["success"] is False
        assert result["error"] == "press_key_failed"


class TestHotkeyStealth:
    """Stealth mode: post_hotkey succeeds -> stealth result."""

    def test_stealth_hotkey(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)
        monkeypatch.setattr(ae_mod.stealth_input, "post_hotkey", MagicMock(return_value=True))

        ex = _make_executor(stealth=True)
        result = ex._hotkey(keys=["ctrl", "c"])
        assert result["success"] is True
        assert "stealth" in result["output"]

    def test_hotkey_key_error(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: False)

        ex = _make_executor()
        ex._desktop.hotkey = MagicMock(side_effect=KeyError("bad key"))

        result = ex._hotkey(keys=["ctrl", "x"])
        assert result["success"] is False
        assert result["error"] == "hotkey_failed"


class TestTypeTextStealth:
    """Stealth mode: post_text succeeds -> stealth result."""

    def test_stealth_type_text(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod.stealth_input, "is_available", lambda: True)
        monkeypatch.setattr(ae_mod.stealth_input, "post_text", MagicMock(return_value=True))

        ex = _make_executor(stealth=True)
        result = ex._type_text(text="hello")
        assert result["success"] is True
        assert "stealth" in result["output"]


class TestScrollError:
    """Scroll exception path."""

    def test_scroll_oserror(self, monkeypatch):
        ex = _make_executor()
        ex._desktop.scroll = MagicMock(side_effect=OSError("no wheel"))

        result = ex._scroll(amount=3)
        assert result["success"] is False
        assert result["error"] == "scroll_failed"


class TestCloseWindowError:
    """close_window exception path."""

    def test_close_window_exception(self, monkeypatch):
        from core import window_manager as wm

        monkeypatch.setattr(wm, "close_window", MagicMock(side_effect=RuntimeError("err")))

        ex = _make_executor()
        result = ex._close_window(title="Ghost")
        assert result["success"] is False
        assert result["error"] == "close_window_failed"


class TestListWindowsError:
    """list_windows exception path."""

    def test_list_windows_exception(self, monkeypatch):
        from core import window_manager as wm

        monkeypatch.setattr(wm, "list_windows", MagicMock(side_effect=RuntimeError("err")))

        ex = _make_executor()
        result = ex._list_windows()
        assert result["success"] is False
        assert result["error"] == "list_windows_failed"


class TestListDirectoryError:
    """list_directory exception path."""

    def test_list_directory_exception(self, monkeypatch):
        from core import file_ops

        monkeypatch.setattr(file_ops, "list_directory", MagicMock(side_effect=OSError("disk")))

        ex = _make_executor()
        result = ex._list_directory(path="/bad")
        assert result["success"] is False
        assert result["error"] == "list_directory_failed"


class TestClipboardReadError:
    """clipboard_read OSError path."""

    def test_clipboard_read_oserror(self, monkeypatch):
        from core import clipboard

        monkeypatch.setattr(clipboard, "clipboard_read", MagicMock(side_effect=OSError("err")))

        ex = _make_executor()
        result = ex._clipboard_read()
        assert result["success"] is False
        assert result["error"] == "clipboard_failed"


class TestClipboardWriteError:
    """clipboard_write OSError path."""

    def test_clipboard_write_oserror(self, monkeypatch):
        from core import clipboard

        monkeypatch.setattr(clipboard, "clipboard_write", MagicMock(side_effect=OSError("err")))

        ex = _make_executor()
        result = ex._clipboard_write(text="hello")
        assert result["success"] is False
        assert result["error"] == "clipboard_failed"


class TestSystemInfoError:
    """system_info exception path."""

    def test_system_info_exception(self, monkeypatch):
        from core import system_info

        monkeypatch.setattr(system_info, "system_info", MagicMock(side_effect=RuntimeError("err")))

        ex = _make_executor()
        result = ex._system_info()
        assert result["success"] is False
        assert result["error"] == "system_info_failed"


class TestListProcessesError:
    """list_processes exception path."""

    def test_list_processes_exception(self, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(
            process_manager, "list_processes", MagicMock(side_effect=RuntimeError("err"))
        )

        ex = _make_executor()
        result = ex._list_processes()
        assert result["success"] is False
        assert result["error"] == "list_processes_failed"


class TestWaitError:
    """wait exception path."""

    def test_wait_exception(self, monkeypatch):
        import time

        monkeypatch.setattr(time, "sleep", MagicMock(side_effect=RuntimeError("alarm")))

        ex = _make_executor()
        result = ex._wait(seconds=1.0)
        assert result["success"] is False
        assert result["error"] == "wait_failed"


class TestWaitForImageError:
    """wait_for_image exception path."""

    def test_wait_for_image_exception(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "wait_for_template", MagicMock(side_effect=RuntimeError("err")))

        ex = _make_executor()
        result = ex._wait_for_image(template_path="btn.png", timeout=5)
        assert result["success"] is False
        assert result["error"] == "wait_for_image_failed"


class TestFindImageError:
    """find_image exception path."""

    def test_find_image_exception(self, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "find_template", MagicMock(side_effect=RuntimeError("err")))

        ex = _make_executor()
        result = ex._find_image(template_path="btn.png")
        assert result["success"] is False
        assert result["error"] == "find_image_failed"


class TestKillProcessError:
    """kill_process exception path."""

    def test_kill_process_exception(self, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(
            process_manager, "kill_process", MagicMock(side_effect=RuntimeError("denied"))
        )

        ex = _make_executor()
        result = ex._kill_process(pid=1234)
        assert result["success"] is False
        assert result["error"] == "kill_process_failed"


class TestListControlsError:
    """list_controls exception path."""

    def test_list_controls_exception(self, monkeypatch):
        from core import ui_tree

        monkeypatch.setattr(
            ui_tree, "list_controls", MagicMock(side_effect=RuntimeError("UIA down"))
        )

        ex = _make_executor()
        result = ex._list_controls()
        assert result["success"] is False
        assert result["error"] == "list_controls_failed"


class TestClickControlException:
    """click_control outer exception path."""

    def test_click_control_exception(self, monkeypatch):
        from core import ui_tree

        monkeypatch.setattr(
            ui_tree, "click_control", MagicMock(side_effect=RuntimeError("UIA crash"))
        )

        ex = _make_executor()
        result = ex._click_control(name="Button")
        assert result["success"] is False
        assert result["error"] == "click_control_failed"


class TestClickControlOcrFallbackException:
    """click_control OCR fallback exception path."""

    def test_ocr_fallback_exception(self, monkeypatch):
        from core import ocr, ui_tree

        monkeypatch.setattr(ui_tree, "click_control", MagicMock(return_value=None))
        monkeypatch.setattr(ocr, "find_text", MagicMock(side_effect=RuntimeError("ocr crash")))

        ex = _make_executor()
        result = ex._click_control(name="Button")
        assert result["success"] is False
        assert result["error"] == "control_not_found"


class TestReadTextFocusedWindow:
    """read_text with focused scope (default) reads focused window."""

    def test_focused_scope_with_title(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(
            ocr, "read_focused_window_text_with_title", lambda: ("Hello focused", "Notepad")
        )
        monkeypatch.setattr(ocr, "looks_low_confidence", lambda t: False)

        ex = _make_executor()
        result = ex._read_text()
        assert result["success"] is True
        assert "Notepad" in result["source"]

    def test_focused_scope_no_text(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "read_focused_window_text_with_title", lambda: ("", None))

        ex = _make_executor()
        result = ex._read_text()
        assert result["success"] is False
        assert result["error"] == "ocr_unavailable"

    def test_window_scope(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "read_window_text", lambda t: "Window text")
        monkeypatch.setattr(ocr, "looks_low_confidence", lambda t: False)

        ex = _make_executor()
        result = ex._read_text(window="Chrome")
        assert result["success"] is True
        assert result["source"] == "window 'Chrome'"

    def test_low_confidence_flag(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "read_screen_text", lambda: "g@rbled t3xt")
        monkeypatch.setattr(ocr, "looks_low_confidence", lambda t: True)

        ex = _make_executor()
        result = ex._read_text(scope="all")
        assert result["success"] is True
        assert result.get("low_confidence") is True
        assert "hint" in result


class TestReadWindowLowConfidence:
    """read_window low_confidence flag."""

    def test_low_confidence_flag_set(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "read_window_text", lambda t: "g@rbled")
        monkeypatch.setattr(ocr, "looks_low_confidence", lambda t: True)

        ex = _make_executor()
        result = ex._read_window(title="App")
        assert result["success"] is True
        assert result.get("low_confidence") is True

    def test_read_window_exception(self, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "read_window_text", MagicMock(side_effect=OSError("err")))

        ex = _make_executor()
        result = ex._read_window(title="App")
        assert result["success"] is False
        assert result["error"] == "read_window_failed"
