"""Tests for ActionExecutor handler gaps — drag, smart_open, powershell, run_script,
smart_wait variants, OCR-backed handlers, click_control/list_controls/set_text/click_image."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import core.desktop as desktop_mod


class FakeDesktop:
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
    from core.action_executor import ActionExecutor

    return ActionExecutor


# -------------------------------------------------------------------
# _drag
# -------------------------------------------------------------------


class TestDrag:
    def test_drag_routes_to_desktop(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync(
            {"action": "drag", "from_x": 10, "from_y": 20, "to_x": 30, "to_y": 40}
        )
        assert out["success"] is True
        assert any(c[0] == "drag" for c in ex._desktop.calls)

    def test_drag_reports_coordinates(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "drag", "from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4})
        assert "(1,2)" in out["output"]
        assert "(3,4)" in out["output"]


# -------------------------------------------------------------------
# _smart_open
# -------------------------------------------------------------------


class TestSmartOpen:
    def test_success_from_launcher(self, fake_executor, monkeypatch):
        from core import launcher

        monkeypatch.setattr(
            launcher, "smart_open", lambda n: {"success": True, "output": f"Opened {n}"}
        )
        ex = fake_executor()
        out = ex.execute_sync({"action": "smart_open", "name": "notepad"})
        assert out["success"] is True

    def test_fallback_to_powershell(self, fake_executor, monkeypatch):
        from core import launcher
        import shutil

        monkeypatch.setattr(
            launcher, "smart_open", lambda n: {"success": False, "output": "not found"}
        )
        monkeypatch.setattr(shutil, "which", lambda x: "C:\\Windows\\System32\\powershell.exe")
        mock_popen = MagicMock()
        monkeypatch.setattr("subprocess.Popen", mock_popen)
        ex = fake_executor()
        out = ex.execute_sync({"action": "smart_open", "name": "notepad"})
        assert out["success"] is True
        assert out.get("fallback") == "powershell"

    def test_total_failure_returns_original_error(self, fake_executor, monkeypatch):
        from core import launcher

        monkeypatch.setattr(
            launcher, "smart_open", lambda n: {"success": False, "output": "not found"}
        )
        monkeypatch.setattr("subprocess.Popen", MagicMock(side_effect=OSError("denied")))
        ex = fake_executor()
        out = ex.execute_sync({"action": "smart_open", "name": "nonexistent"})
        assert out["success"] is False
        assert "hint" in out


# -------------------------------------------------------------------
# _open_app
# -------------------------------------------------------------------


class TestOpenApp:
    def test_success(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "start_process", lambda p, a=None: 99)
        ex = fake_executor()
        out = ex.execute_sync({"action": "open_app", "path": "notepad.exe"})
        assert out["success"] is True
        assert "99" in out["output"]

    def test_start_returns_none(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "start_process", lambda p, a=None: 0)
        ex = fake_executor()
        out = ex.execute_sync({"action": "open_app", "path": "bad.exe"})
        assert out["success"] is False

    def test_exception_returns_error(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(
            process_manager,
            "start_process",
            lambda p, a=None: (_ for _ in ()).throw(RuntimeError("fail")),
        )
        ex = fake_executor()
        out = ex.execute_sync({"action": "open_app", "path": "crash.exe"})
        assert out["success"] is False
        assert out["error"] == "open_app_failed"


# -------------------------------------------------------------------
# _close_app (actual kill path)
# -------------------------------------------------------------------


class TestCloseAppKill:
    def test_kill_success(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "kill_process", lambda t: True)
        ex = fake_executor()
        out = ex.execute_sync({"action": "close_app", "name": "notepad"})
        assert out["success"] is True

    def test_kill_not_found(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "kill_process", lambda t: False)
        ex = fake_executor()
        out = ex.execute_sync({"action": "close_app", "name": "ghost"})
        assert out["success"] is False

    def test_kill_exception(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(
            process_manager,
            "kill_process",
            lambda t: (_ for _ in ()).throw(RuntimeError("access denied")),
        )
        ex = fake_executor()
        out = ex.execute_sync({"action": "close_app", "name": "protected"})
        assert out["success"] is False
        assert out["error"] == "close_app_failed"


# -------------------------------------------------------------------
# _powershell
# -------------------------------------------------------------------


class TestPowerShell:
    def test_success(self, fake_executor, monkeypatch):
        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.stdout = "Hello World"
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_result.objects = []
        mock_runner.run_command.return_value = mock_result
        monkeypatch.setattr("core.powershell.get_default_runner", lambda: mock_runner)
        ex = fake_executor()
        out = ex.execute_sync({"action": "powershell", "command": "echo hello"})
        assert out["success"] is True
        assert out["exit_code"] == 0

    def test_failure(self, fake_executor, monkeypatch):
        monkeypatch.setattr(
            "core.powershell.get_default_runner",
            MagicMock(side_effect=RuntimeError("no PS")),
        )
        ex = fake_executor()
        out = ex.execute_sync({"action": "powershell", "command": "bad"})
        assert out["success"] is False
        assert out["error"] == "powershell_failed"


# -------------------------------------------------------------------
# _run_script
# -------------------------------------------------------------------


class TestRunScript:
    def test_success(self, fake_executor, monkeypatch):
        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.steps_completed = 5
        mock_result.steps_total = 5
        mock_result.error = None
        mock_engine.run_script.return_value = mock_result
        monkeypatch.setattr("core.script_engine.ScriptEngine", lambda executor: mock_engine)
        ex = fake_executor()
        out = ex.execute_sync({"action": "run_script", "path": "test.json"})
        assert out["success"] is True
        assert out["steps_completed"] == 5

    def test_script_error(self, fake_executor, monkeypatch):
        monkeypatch.setattr(
            "core.script_engine.ScriptEngine",
            MagicMock(side_effect=FileNotFoundError("missing")),
        )
        ex = fake_executor()
        out = ex.execute_sync({"action": "run_script", "path": "nope.json"})
        assert out["success"] is False
        assert out["error"] == "script_failed"


# -------------------------------------------------------------------
# _wait_for_image
# -------------------------------------------------------------------


class TestWaitForImage:
    def test_found(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "wait_for_template", lambda t, to=30.0: (50, 60))
        ex = fake_executor()
        out = ex.execute_sync(
            {"action": "wait_for_image", "template_path": "btn.png", "timeout": 5}
        )
        assert out["success"] is True
        assert out["position"] == [50, 60]

    def test_timeout(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "wait_for_template", lambda t, to=30.0: None)
        ex = fake_executor()
        out = ex.execute_sync({"action": "wait_for_image", "template_path": "missing.png"})
        assert out["success"] is False
        assert out["error"] == "timeout"


# -------------------------------------------------------------------
# _smart_wait
# -------------------------------------------------------------------


class TestSmartWait:
    def test_success(self, fake_executor, monkeypatch):
        mock_sw = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elapsed = 2.5
        mock_result.frames_checked = 10
        mock_sw.wait_for_change.return_value = mock_result
        monkeypatch.setattr("core.smart_wait.SmartWait", lambda: mock_sw)
        ex = fake_executor()
        out = ex.execute_sync({"action": "smart_wait", "timeout": 5})
        assert out["success"] is True
        assert out["frames_checked"] == 10

    def test_failure_falls_back(self, fake_executor, monkeypatch):
        monkeypatch.setattr(
            "core.smart_wait.SmartWait",
            MagicMock(side_effect=ImportError("no smart_wait")),
        )
        import time

        monkeypatch.setattr(time, "sleep", MagicMock())
        ex = fake_executor()
        out = ex.execute_sync({"action": "smart_wait", "timeout": 3})
        assert out["success"] is False


# -------------------------------------------------------------------
# _wait_for_stable
# -------------------------------------------------------------------


class TestWaitForStable:
    def test_success(self, fake_executor, monkeypatch):
        mock_sw = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elapsed = 3.0
        mock_sw.wait_for_stable.return_value = mock_result
        monkeypatch.setattr("core.smart_wait.SmartWait", lambda: mock_sw)
        ex = fake_executor()
        out = ex.execute_sync({"action": "wait_for_stable", "timeout": 5})
        assert out["success"] is True

    def test_failure_falls_back(self, fake_executor, monkeypatch):
        monkeypatch.setattr(
            "core.smart_wait.SmartWait",
            MagicMock(side_effect=RuntimeError("broken")),
        )
        import time

        monkeypatch.setattr(time, "sleep", MagicMock())
        ex = fake_executor()
        out = ex.execute_sync({"action": "wait_for_stable", "timeout": 5})
        assert out["success"] is False


# -------------------------------------------------------------------
# _wait_for_text
# -------------------------------------------------------------------


class TestWaitForText:
    def test_found(self, fake_executor, monkeypatch):
        mock_sw = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elapsed = 1.2
        mock_sw.wait_for_text.return_value = mock_result
        monkeypatch.setattr("core.smart_wait.SmartWait", lambda: mock_sw)
        ex = fake_executor()
        out = ex.execute_sync({"action": "wait_for_text", "text": "Login", "timeout": 5})
        assert out["success"] is True

    def test_failure(self, fake_executor, monkeypatch):
        monkeypatch.setattr(
            "core.smart_wait.SmartWait",
            MagicMock(side_effect=RuntimeError("no OCR")),
        )
        import time

        monkeypatch.setattr(time, "sleep", MagicMock())
        ex = fake_executor()
        out = ex.execute_sync({"action": "wait_for_text", "text": "missing"})
        assert out["success"] is False
        assert out["error"] == "wait_for_text_failed"


# -------------------------------------------------------------------
# _read_text
# -------------------------------------------------------------------


class TestReadText:
    def test_success(self, fake_executor, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "read_screen_text", lambda: "Hello World")
        monkeypatch.setattr(ocr, "looks_low_confidence", lambda t: False)
        ex = fake_executor()
        out = ex.execute_sync({"action": "read_text", "scope": "all"})
        assert out["success"] is True
        assert out["output"] == "Hello World"

    def test_failure(self, fake_executor, monkeypatch):
        from core import ocr

        monkeypatch.setattr(
            ocr, "read_screen_text", lambda: (_ for _ in ()).throw(RuntimeError("ocr fail"))
        )
        ex = fake_executor()
        out = ex.execute_sync({"action": "read_text", "scope": "all"})
        assert out["success"] is False
        assert out["error"] == "read_text_failed"


# -------------------------------------------------------------------
# _read_window
# -------------------------------------------------------------------


class TestReadWindow:
    def test_success(self, fake_executor, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "read_window_text", lambda t: "Window content")
        monkeypatch.setattr(ocr, "looks_low_confidence", lambda t: False)
        ex = fake_executor()
        out = ex.execute_sync({"action": "read_window", "title": "Notepad"})
        assert out["success"] is True
        assert "Window content" in out["output"]

    def test_window_not_found(self, fake_executor, monkeypatch):
        from core import ocr

        monkeypatch.setattr(ocr, "read_window_text", lambda t: "")
        ex = fake_executor()
        out = ex.execute_sync({"action": "read_window", "title": "Ghost"})
        assert out["success"] is False

    def test_failure(self, fake_executor, monkeypatch):
        from core import ocr

        monkeypatch.setattr(
            ocr,
            "read_window_text",
            lambda t: (_ for _ in ()).throw(RuntimeError("err")),
        )
        ex = fake_executor()
        out = ex.execute_sync({"action": "read_window", "title": "Crash"})
        assert out["success"] is False
        assert out["error"] == "read_window_failed"


# -------------------------------------------------------------------
# _click_control
# -------------------------------------------------------------------


class TestClickControl:
    def test_uia_found(self, fake_executor, monkeypatch):
        from core import ui_tree

        monkeypatch.setattr(ui_tree, "click_control", lambda **kw: (100, 200))
        ex = fake_executor()
        out = ex.execute_sync({"action": "click_control", "name": "OK Button"})
        assert out["success"] is True
        assert out["position"] == [100, 200]

    def test_uia_not_found_ocr_fallback(self, fake_executor, monkeypatch):
        from core import ocr, ui_tree

        monkeypatch.setattr(ui_tree, "click_control", lambda **kw: None)
        monkeypatch.setattr(ocr, "find_text", lambda t, fuzzy=True: (50, 60))
        ex = fake_executor()
        out = ex.execute_sync({"action": "click_control", "name": "Label"})
        assert out["success"] is True
        assert out.get("fallback") == "ocr"

    def test_no_match_at_all(self, fake_executor, monkeypatch):
        from core import ocr, ui_tree

        monkeypatch.setattr(ui_tree, "click_control", lambda **kw: None)
        monkeypatch.setattr(ocr, "find_text", lambda t, fuzzy=True: None)
        ex = fake_executor()
        out = ex.execute_sync({"action": "click_control", "name": "Invisible"})
        assert out["success"] is False
        assert out["error"] == "control_not_found"


# -------------------------------------------------------------------
# _list_controls
# -------------------------------------------------------------------


class TestListControls:
    def test_success(self, fake_executor, monkeypatch):
        from core import ui_tree

        controls = [
            {
                "name": "Button1",
                "control_type": "Button",
                "automation_id": "btn1",
                "x": 10,
                "y": 20,
                "width": 80,
                "height": 30,
                "is_offscreen": False,
                "is_enabled": True,
            }
        ]
        monkeypatch.setattr(ui_tree, "list_controls", lambda **kw: controls)
        ex = fake_executor()
        out = ex.execute_sync({"action": "list_controls"})
        assert out["success"] is True
        assert out["count"] == 1

    def test_no_controls(self, fake_executor, monkeypatch):
        from core import ui_tree

        monkeypatch.setattr(ui_tree, "list_controls", lambda **kw: [])
        ex = fake_executor()
        out = ex.execute_sync({"action": "list_controls"})
        assert out["success"] is False
        assert out["error"] == "uia_unavailable"


# -------------------------------------------------------------------
# _set_text (non-sensitive path)
# -------------------------------------------------------------------


class TestSetText:
    def test_blocked_by_sensitive(self, fake_executor):
        ex = fake_executor()
        out = ex.execute_sync({"action": "set_text", "text": "my secret key", "name": "field"})
        assert out["success"] is False
        assert out["error"] == "sensitive_field"

    def test_uia_set_value(self, fake_executor, monkeypatch):
        from core import ui_tree

        monkeypatch.setattr(ui_tree, "set_text", lambda *a, **kw: True)
        ex = fake_executor()
        out = ex.execute_sync({"action": "set_text", "text": "hello", "name": "input"})
        assert out["success"] is True

    def test_uia_not_found_click_type_fallback(self, fake_executor, monkeypatch):
        import time

        from core import ui_tree

        monkeypatch.setattr(ui_tree, "set_text", lambda *a, **kw: False)
        monkeypatch.setattr(
            ui_tree,
            "list_controls",
            lambda **kw: [
                {
                    "name": "field",
                    "control_type": "Edit",
                    "x": 10,
                    "y": 20,
                    "width": 80,
                    "height": 30,
                    "is_offscreen": False,
                }
            ],
        )
        monkeypatch.setattr(time, "sleep", MagicMock())
        ex = fake_executor()
        out = ex.execute_sync({"action": "set_text", "text": "hello world", "name": "field"})
        assert out["success"] is True
        assert out.get("fallback") == "click_and_type"

    def test_no_match(self, fake_executor, monkeypatch):
        from core import ui_tree

        monkeypatch.setattr(ui_tree, "set_text", lambda *a, **kw: False)
        monkeypatch.setattr(ui_tree, "list_controls", lambda **kw: [])
        ex = fake_executor()
        out = ex.execute_sync({"action": "set_text", "text": "hello world", "name": "missing"})
        assert out["success"] is False
        assert out["error"] == "control_not_found"


# -------------------------------------------------------------------
# _click_image
# -------------------------------------------------------------------


class TestClickImage:
    def test_found_and_clicked(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        monkeypatch.setattr(ae_mod, "find_template", lambda t, c=0.8: (100, 200))
        monkeypatch.setattr(ae_mod, "stealth_input", MagicMock(is_available=lambda: False))
        ex = fake_executor()
        out = ex.execute_sync({"action": "click_image", "template_path": "btn.png"})
        assert out["success"] is True

    def test_not_found(self, fake_executor, monkeypatch):
        import core.action_executor as ae_mod

        fake_desktop_inst = MagicMock()
        fake_desktop_inst.click_image.return_value = False
        monkeypatch.setattr(ae_mod, "find_template", lambda t, c=0.8: None)
        monkeypatch.setattr(ae_mod, "stealth_input", MagicMock(is_available=lambda: False))
        ex = fake_executor()
        ex._desktop = fake_desktop_inst
        out = ex._click_image(template_path="missing.png")
        assert out["success"] is False


# -------------------------------------------------------------------
# async execute
# -------------------------------------------------------------------


class TestAsyncExecute:
    def test_async_execute_runs_handler(self, fake_executor):
        ex = fake_executor()
        result = asyncio.run(ex.execute({"action": "note", "text": "async test"}))
        assert result["success"] is True
        assert result["output"] == "async test"

    def test_async_execute_unknown_action(self, fake_executor):
        ex = fake_executor()
        result = asyncio.run(ex.execute({"action": "teleport"}))
        assert result["success"] is False


# -------------------------------------------------------------------
# _kill_process handler
# -------------------------------------------------------------------


class TestKillProcessHandler:
    def test_kill_by_pid_success(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "kill_process", lambda t: True)
        ex = fake_executor()
        out = ex.execute_sync({"action": "kill_process", "pid": 1234})
        assert out["success"] is True

    def test_kill_by_name_success(self, fake_executor, monkeypatch):
        from core import process_manager

        monkeypatch.setattr(process_manager, "kill_process", lambda t: True)
        ex = fake_executor()
        out = ex.execute_sync({"action": "kill_process", "name": "notepad.exe"})
        assert out["success"] is True
