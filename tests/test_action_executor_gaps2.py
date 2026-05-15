"""Gap tests for action_executor.py — _sanitize_params, _contains_sensitive,
_dry_run_result, _log_entry, and sync handler paths."""

from unittest.mock import patch

import core.desktop as desktop_mod
from core.action_executor import (
    _contains_sensitive,
    _dry_run_result,
    _sanitize_params,
)


class FakeDesktop:
    def __init__(self):
        self.calls = []

    def click(self, *a, **kw):
        self.calls.append(("click", a, kw))

    def type_text(self, *a, **kw):
        self.calls.append(("type_text", a, kw))

    def press_key(self, *a, **kw):
        self.calls.append(("press_key", a, kw))

    def hotkey(self, *a, **kw):
        self.calls.append(("hotkey", a, kw))

    def scroll(self, *a, **kw):
        self.calls.append(("scroll", a, kw))

    def drag(self, *a, **kw):
        self.calls.append(("drag", a, kw))


def _make_executor(**kw):
    """Create an ActionExecutor with FakeDesktop patched in."""
    from core.action_executor import ActionExecutor

    original = desktop_mod.DesktopEngine
    desktop_mod.DesktopEngine = FakeDesktop
    try:
        ex = ActionExecutor(**kw)
    finally:
        desktop_mod.DesktopEngine = original
    return ex


class TestContainsSensitive:
    """_contains_sensitive detects sensitive keywords."""

    def test_password(self):
        assert _contains_sensitive("my password is x") is True

    def test_api_key(self):
        assert _contains_sensitive("the api_key is abc") is True

    def test_token(self):
        assert _contains_sensitive("bearer token here") is True

    def test_normal_text(self):
        assert _contains_sensitive("hello world") is False

    def test_case_insensitive(self):
        assert _contains_sensitive("SECRET stuff") is True

    def test_ssn(self):
        assert _contains_sensitive("SSN: 123-45-6789") is True


class TestSanitizeParams:
    """_sanitize_params truncates large values."""

    def test_short_string_unchanged(self):
        assert _sanitize_params({"key": "short"}) == {"key": "short"}

    def test_long_string_truncated(self):
        long_val = "x" * 300
        result = _sanitize_params({"data": long_val})
        assert len(result["data"]) < 300
        assert result["data"].endswith("...")

    def test_large_list_summary(self):
        big_list = list(range(1000))
        result = _sanitize_params({"items": big_list})
        assert "len=" in result["items"]

    def test_large_dict_summary(self):
        big_dict = {f"k{i}": f"v{i}" for i in range(200)}
        result = _sanitize_params({"data": big_dict})
        assert "len=" in result["data"]

    def test_small_list_unchanged(self):
        small = [1, 2, 3]
        assert _sanitize_params({"nums": small}) == {"nums": small}


class TestDryRunResult:
    """_dry_run_result returns synthetic success."""

    def test_returns_success(self):
        result = _dry_run_result("click", {"x": 1, "y": 2})
        assert result["success"] is True
        assert result["dry_run"] is True
        assert "click" in result["output"]

    def test_truncates_long_preview(self):
        params = {f"param_{i}": f"val_{i}" * 50 for i in range(5)}
        result = _dry_run_result("action", params)
        assert len(result["output"]) < 500


class TestLogEntry:
    """_log_entry records action results."""

    def test_log_records_success(self):
        ex = _make_executor()
        ex._log_entry("click", {"x": 1, "y": 2}, {"success": True, "output": "ok"})
        assert len(ex.log) == 1
        assert ex.log[0]["action"] == "click"
        assert ex.log[0]["success"] is True

    def test_log_records_failure(self):
        ex = _make_executor()
        ex._log_entry("type_text", {"text": "hi"}, {"success": False, "output": "err"})
        assert ex.log[0]["success"] is False

    def test_log_sanitize_applied(self):
        ex = _make_executor()
        long_text = "x" * 500
        ex._log_entry("type_text", {"text": long_text}, {"success": True})
        assert len(ex.log[0]["params"]["text"]) < 500


class TestWaitHandler:
    """_wait caps and clamps duration."""

    def test_wait_normal(self):
        ex = _make_executor()
        result = ex.execute_sync({"action": "wait", "seconds": 0.01})
        assert result["success"] is True
        assert "0.01s" in result["output"]

    def test_wait_negative_clamped(self):
        ex = _make_executor()
        result = ex.execute_sync({"action": "wait", "seconds": -5})
        assert result["success"] is True
        assert "0.0s" in result["output"]


class TestNoteHandler:
    """_note logs and returns text."""

    def test_note_returns_success(self):
        ex = _make_executor()
        result = ex.execute_sync({"action": "note", "text": "remember this"})
        assert result["success"] is True
        assert result["output"] == "remember this"


class TestFinishHandler:
    """_finish signals done."""

    def test_finish_with_summary(self):
        ex = _make_executor()
        result = ex.execute_sync({"action": "finish", "summary": "all done"})
        assert result["success"] is True
        assert result["done"] is True
        assert result["output"] == "all done"

    def test_finish_without_summary(self):
        ex = _make_executor()
        result = ex.execute_sync({"action": "finish"})
        assert result["success"] is True
        assert result["done"] is True


class TestCloseAppHandler:
    """_close_app with missing target."""

    def test_close_app_no_target(self):
        ex = _make_executor()
        result = ex.execute_sync({"action": "close_app"})
        assert result["success"] is False
        assert result["error"] == "missing_target"


class TestKillProcessHandler:
    """_kill_process with no target returns error."""

    def test_kill_process_no_target(self):
        ex = _make_executor()
        result = ex.execute_sync({"action": "kill_process"})
        assert result["success"] is False


class TestStartProcessHandler:
    """_start_process with OSError."""

    def test_start_process_oserror(self):
        ex = _make_executor()
        with patch("core.action_executor.pm.start_process", side_effect=OSError("nope")):
            result = ex.execute_sync({"action": "start_process", "path": "foo.exe"})
        assert result["success"] is False
        assert "start_process_failed" in result["error"]


class TestListProcessesHandler:
    """_list_processes returns list."""

    def test_list_processes_success(self):
        ex = _make_executor()
        with patch("core.action_executor.pm.list_processes", return_value=[{"name": "a"}]):
            result = ex.execute_sync({"action": "list_processes"})
        assert result["success"] is True


class TestSystemInfoHandler:
    """_system_info returns info."""

    def test_system_info_success(self):
        ex = _make_executor()
        with patch("core.action_executor.sysinfo.system_info", return_value={"os": "win"}):
            result = ex.execute_sync({"action": "system_info"})
        assert result["success"] is True


class TestReadFileHandler:
    """_read_file handler paths."""

    def test_read_file_success(self):
        ex = _make_executor()
        with patch("core.action_executor.file_ops.read_file", return_value="content"):
            result = ex.execute_sync({"action": "read_file", "path": "test.txt"})
        assert result["success"] is True
        assert result["output"] == "content"

    def test_read_file_not_found(self):
        ex = _make_executor()
        with patch("core.action_executor.file_ops.read_file", return_value=None):
            result = ex.execute_sync({"action": "read_file", "path": "missing.txt"})
        assert result["success"] is False
        assert result["error"] == "file_not_found"


class TestWriteFileHandler:
    """_write_file handler paths."""

    def test_write_file_success(self):
        ex = _make_executor()
        with patch("core.action_executor.file_ops.write_file", return_value=True):
            result = ex.execute_sync({"action": "write_file", "path": "f.txt", "content": "hi"})
        assert result["success"] is True

    def test_write_file_oserror(self):
        ex = _make_executor()
        with patch("core.action_executor.file_ops.write_file", side_effect=OSError("disk full")):
            result = ex.execute_sync({"action": "write_file", "path": "f.txt", "content": "hi"})
        assert result["success"] is False


class TestListDirectoryHandler:
    """_list_directory handler paths."""

    def test_list_directory_success(self):
        ex = _make_executor()
        with patch("core.action_executor.file_ops.list_directory", return_value=["a.txt"]):
            result = ex.execute_sync({"action": "list_directory", "path": "."})
        assert result["success"] is True

    def test_list_directory_not_found(self):
        ex = _make_executor()
        with patch("core.action_executor.file_ops.list_directory", return_value=None):
            result = ex.execute_sync({"action": "list_directory", "path": "missing"})
        assert result["success"] is False
        assert result["error"] == "dir_not_found"


class TestClipboardReadHandler:
    """_clipboard_read handler paths."""

    def test_clipboard_read_success(self):
        ex = _make_executor()
        with patch("core.action_executor.clip.clipboard_read", return_value="copied"):
            result = ex.execute_sync({"action": "clipboard_read"})
        assert result["success"] is True
        assert result["output"] == "copied"

    def test_clipboard_read_none(self):
        ex = _make_executor()
        with patch("core.action_executor.clip.clipboard_read", return_value=None):
            result = ex.execute_sync({"action": "clipboard_read"})
        assert result["success"] is False


class TestClipboardWriteHandler:
    """_clipboard_write handler paths."""

    def test_clipboard_write_success(self):
        ex = _make_executor()
        with patch("core.action_executor.clip.clipboard_write", return_value=True):
            result = ex.execute_sync({"action": "clipboard_write", "text": "hi"})
        assert result["success"] is True


class TestScrollHandler:
    """_scroll handler."""

    def test_scroll_success(self):
        ex = _make_executor()
        result = ex.execute_sync({"action": "scroll", "amount": 3})
        assert result["success"] is True
        assert "3" in result["output"]


class TestScreenshotHandler:
    """_screenshot handler."""

    def test_screenshot_capture_error(self):
        ex = _make_executor()
        with patch(
            "core.action_executor.capture_to_base64", side_effect=RuntimeError("no display")
        ):
            result = ex.execute_sync({"action": "screenshot"})
        assert result["success"] is False
        assert result["error"] == "capture_failed"


class TestFindImageHandler:
    """_find_image handler paths."""

    def test_find_image_found(self):
        ex = _make_executor()
        with patch("core.action_executor.find_template", return_value=(10, 20)):
            result = ex.execute_sync({"action": "find_image", "template_path": "btn.png"})
        assert result["success"] is True
        assert result["position"] == [10, 20]

    def test_find_image_not_found(self):
        ex = _make_executor()
        with patch("core.action_executor.find_template", return_value=None):
            result = ex.execute_sync({"action": "find_image", "template_path": "btn.png"})
        assert result["success"] is False
        assert result["error"] == "image_not_found"


class TestDispatchTableCompleteness:
    """Every STATE_CHANGING_ACTIONS has a dispatch entry."""

    def test_all_state_changing_have_handler(self):
        from core.action_executor import STATE_CHANGING_ACTIONS

        ex = _make_executor()
        for action in STATE_CHANGING_ACTIONS:
            assert action in ex._dispatch_table, f"{action} missing from dispatch"
