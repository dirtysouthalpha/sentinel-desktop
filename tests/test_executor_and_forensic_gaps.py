"""Gap tests for action_executor _focus_window, _wait_for_stable, _smart_open,
_click_control OCR fallback, forensic_log get_summary, and checkpoint stat race."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.action_executor import ActionExecutor
from core.forensic_log import ForensicLog

# ── _focus_window ──────────────────────────────────────────────────────────


class TestFocusWindowExactMatch:
    """Exact title match returns success."""

    @patch("core.action_executor.wm")
    def test_exact_match_returns_success(self, mock_wm):
        mock_wm.focus_window.return_value = True
        ex = ActionExecutor()
        result = ex._focus_window(title="Notepad")
        assert result["success"] is True
        assert "Notepad" in result["output"]
        mock_wm.focus_window.assert_called_once_with("Notepad")


class TestFocusWindowPartialMatch:
    """When exact focus fails, partial match is attempted."""

    @patch("core.action_executor.wm")
    def test_partial_needle_in_haystack(self, mock_wm):
        mock_wm.focus_window.side_effect = [False, True]
        mock_wm.list_windows.return_value = [
            {"title": "Document - Notepad"},
            {"title": "Chrome"},
        ]
        ex = ActionExecutor()
        result = ex._focus_window(title="Notepad")
        assert result["success"] is True
        assert result["matched_title"] == "Document - Notepad"

    @patch("core.action_executor.wm")
    def test_partial_haystack_in_needle(self, mock_wm):
        """Short window title is substring of search term."""
        mock_wm.focus_window.side_effect = [False, True]
        mock_wm.list_windows.return_value = [
            {"title": "Code"},
        ]
        ex = ActionExecutor()
        result = ex._focus_window(title="Visual Studio Code")
        assert result["success"] is True

    @patch("core.action_executor.wm")
    def test_no_match_returns_not_found(self, mock_wm):
        mock_wm.focus_window.return_value = False
        mock_wm.list_windows.return_value = [
            {"title": "Chrome"},
            {"title": "Explorer"},
        ]
        ex = ActionExecutor()
        result = ex._focus_window(title="Notepad")
        assert result["success"] is False
        assert result["error"] == "window_not_found"

    @patch("core.action_executor.wm")
    def test_partial_match_focus_also_fails(self, mock_wm):
        """Partial match found but focusing it also fails."""
        mock_wm.focus_window.return_value = False
        mock_wm.list_windows.return_value = [
            {"title": "Document - Notepad"},
        ]
        ex = ActionExecutor()
        result = ex._focus_window(title="Notepad")
        assert result["success"] is False

    @patch("core.action_executor.wm")
    def test_wm_raises_exception(self, mock_wm):
        mock_wm.focus_window.side_effect = RuntimeError("access denied")
        ex = ActionExecutor()
        result = ex._focus_window(title="Notepad")
        assert result["success"] is False
        assert "access denied" in result["output"]


# ── _wait_for_stable ───────────────────────────────────────────────────────


class TestWaitForStableFallback:
    """When SmartWait raises, fallback to 3s sleep."""

    @patch("time.sleep")
    @patch("core.action_executor.SmartWait", create=True)
    def test_import_fails_returns_fallback(self, mock_sw_cls, _mock_sleep):
        with patch.dict("sys.modules", {"core.smart_wait": None}):
            ex = ActionExecutor()
            result = ex._wait_for_stable(timeout=5, stable_time=1)
            assert result["success"] is False
            assert "error" in result


# ── _smart_open fallback chain ─────────────────────────────────────────────


class TestSmartOpenPowerShellFallback:
    """When launcher.smart_open fails, PowerShell Start-Process is tried."""

    @patch("core.action_executor.launcher")
    @patch("subprocess.Popen")
    @patch("shutil.which", return_value="C:\\Windows\\System32\\powershell.exe")
    def test_powershell_fallback_success(self, mock_which, mock_popen, mock_launcher):
        mock_launcher.smart_open.return_value = {"success": False, "error": "not found"}
        mock_popen.return_value = MagicMock()
        ex = ActionExecutor()
        result = ex._smart_open(name="notepad.exe")
        assert result["success"] is True
        assert result.get("fallback") == "powershell"

    @patch("core.action_executor.launcher")
    @patch("subprocess.Popen")
    @patch("shutil.which", return_value="C:\\Windows\\System32\\powershell.exe")
    def test_powershell_also_fails_returns_hint(self, mock_which, mock_popen, mock_launcher):
        mock_launcher.smart_open.return_value = {"success": False, "error": "not found"}
        mock_popen.side_effect = OSError("denied")
        ex = ActionExecutor()
        result = ex._smart_open(name="missing_app")
        assert result["success"] is False
        assert "hint" in result


# ── _click_control OCR fallback ────────────────────────────────────────────


class TestClickControlOcrFallback:
    """When UIAutomation finds nothing, OCR text click is attempted."""

    @patch("core.action_executor.ocr")
    @patch("core.action_executor.ui_tree")
    def test_ocr_fallback_click(self, mock_ui_tree, mock_ocr):
        mock_ui_tree.click_control.return_value = None
        mock_ocr.find_text.return_value = (100, 200)
        ex = ActionExecutor()
        ex._desktop = MagicMock()
        result = ex._click_control(name="Submit", button="left")
        assert result["success"] is True
        assert result.get("fallback") == "ocr"
        ex._desktop.click.assert_called_once()

    @patch("core.action_executor.ocr")
    @patch("core.action_executor.ui_tree")
    def test_ocr_fallback_with_offset(self, mock_ui_tree, mock_ocr):
        mock_ui_tree.click_control.return_value = None
        mock_ocr.find_text.return_value = (100, 200)
        ex = ActionExecutor(click_offset=(10, 20))
        ex._desktop = MagicMock()
        ex._click_control(name="Submit")
        ex._desktop.click.assert_called_once_with(110, 220, button="left")

    @patch("core.action_executor.ocr")
    @patch("core.action_executor.ui_tree")
    def test_ocr_no_text_found(self, mock_ui_tree, mock_ocr):
        mock_ui_tree.click_control.return_value = None
        mock_ocr.find_text.return_value = None
        ex = ActionExecutor()
        result = ex._click_control(name="Missing")
        assert result["success"] is False
        assert result["error"] == "control_not_found"

    @patch("core.action_executor.ocr")
    @patch("core.action_executor.ui_tree")
    def test_no_name_skips_ocr(self, mock_ui_tree, mock_ocr):
        mock_ui_tree.click_control.return_value = None
        ex = ActionExecutor()
        result = ex._click_control(automation_id="btn1")
        assert result["success"] is False
        mock_ocr.find_text.assert_not_called()


# ── forensic_log get_summary ───────────────────────────────────────────────


class TestForensicGetSummary:
    """get_summary formatting with mixed event types and optional summary."""

    def test_no_run_returns_empty_message(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        assert fl.get_summary() == "No forensic run recorded."

    def test_basic_summary_with_events(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Test goal", "openai", "gpt-4o")
        fl.log_step(1, "click", "Btn", {}, "success")
        fl.log_step(2, "click", "Btn", {}, "error: element not found")
        fl.log_step(3, "override", "Btn", {}, "override applied")
        summary = fl.get_summary()
        assert "Test goal" in summary
        assert "openai" in summary
        assert "gpt-4o" in summary
        # "success" → action, "error: ..." → error, "override applied" → action
        assert "actions=2" in summary
        assert "errors=1" in summary

    def test_summary_with_summary_text(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.end_run("success", "All steps completed", 5)
        summary = fl.get_summary()
        assert "All steps completed" in summary

    def test_summary_without_summary_text(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.end_run("success", "", 3)
        summary = fl.get_summary()
        assert "Summary:" not in summary

    def test_status_displayed(self):
        fl = ForensicLog(log_dir=tempfile.mkdtemp())
        fl.start_run("Goal", "openai", "gpt-4o")
        fl.end_run("error", "Failed", 2)
        summary = fl.get_summary()
        assert "[error]" in summary


# ── checkpoint stat race condition ─────────────────────────────────────────


class TestCheckpointStatRace:
    """Files deleted between glob and stat are skipped."""

    def test_discover_skips_unstatable_files(self, tmp_path):
        from core.checkpoint import _discover_checkpoint_files

        good = tmp_path / "good.json"
        good.write_text("{}")
        bad = tmp_path / "deleted.json"
        bad.write_text("{}")

        original_stat = Path.stat

        def fake_stat(self, **kwargs):
            if self.name == "deleted.json":
                raise OSError("file gone")
            return original_stat(self, **kwargs)

        with patch.object(Path, "stat", fake_stat):
            files = _discover_checkpoint_files(str(tmp_path))
        assert len(files) == 1
        assert files[0].name == "good.json"
