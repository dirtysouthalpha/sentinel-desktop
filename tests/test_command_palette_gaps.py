"""Gap tests for command_palette.py — helper functions with error handling."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock tkinter before importing command_palette to avoid ModuleNotFoundError on Linux
mock_askstring = MagicMock()
mock_simpledialog = MagicMock()
mock_simpledialog.askstring = mock_askstring
mock_tkinter = MagicMock()
mock_tkinter.simpledialog = mock_simpledialog
sys.modules["tkinter"] = mock_tkinter
sys.modules["tkinter.simpledialog"] = mock_simpledialog

from core.command_palette import (
    _run_it_script,
    _run_powershell_dialog,
    _run_script_dialog,
    _show_script_library,
    _start_recording,
    _stop_recording,
)


class TestStartRecording:
    """_start_recording handles exceptions gracefully."""

    def test_no_engine_does_nothing(self):
        app = MagicMock(spec=[])
        _start_recording(app)

    def test_recorder_error_is_caught(self):
        app = MagicMock()
        app.engine.recorder.start_recording.side_effect = RuntimeError("boom")
        _start_recording(app)

    def test_success_calls_recorder(self):
        app = MagicMock()
        _start_recording(app)
        app.engine.recorder.start_recording.assert_called_once_with("")

    def test_recorder_panel_called_when_present(self):
        app = MagicMock()
        _start_recording(app)
        app.recorder_panel._on_record_click.assert_called_once()


class TestStopRecording:
    """_stop_recording handles exceptions gracefully."""

    def test_no_engine_does_nothing(self):
        app = MagicMock(spec=[])
        _stop_recording(app)

    def test_recorder_error_is_caught(self):
        app = MagicMock()
        app.engine.recorder.stop_recording.side_effect = RuntimeError("boom")
        _stop_recording(app)

    def test_success_calls_recorder(self):
        app = MagicMock()
        _stop_recording(app)
        app.engine.recorder.stop_recording.assert_called_once()


class TestRunScriptDialog:
    """_run_script_dialog handles exceptions gracefully."""

    def test_no_recorder_panel_does_nothing(self):
        app = MagicMock(spec=[])
        _run_script_dialog(app)

    def test_panel_error_is_caught(self):
        app = MagicMock()
        app.recorder_panel._on_play_click.side_effect = RuntimeError("boom")
        _run_script_dialog(app)

    def test_success_calls_play_click(self):
        app = MagicMock()
        _run_script_dialog(app)
        app.recorder_panel._on_play_click.assert_called_once()


class TestShowScriptLibrary:
    """_show_script_library handles exceptions gracefully."""

    def test_no_recorder_panel_does_nothing(self):
        app = MagicMock(spec=[])
        _show_script_library(app)

    def test_panel_error_is_caught(self):
        app = MagicMock()
        app.recorder_panel._on_library_click.side_effect = RuntimeError("boom")
        _show_script_library(app)

    def test_success_calls_library_click(self):
        app = MagicMock()
        _show_script_library(app)
        app.recorder_panel._on_library_click.assert_called_once()


# ---------------------------------------------------------------------------
# _run_powershell_dialog  (lines 475-508)
# ---------------------------------------------------------------------------


class TestRunPowershellDialog:
    """Cover lines 475-503: PowerShell command dialog and result/error display."""

    def setup_method(self):
        """Reset mock before each test."""
        mock_askstring.reset_mock()

    def test_no_cmd_returned_does_nothing(self):
        """If askstring returns None, function returns without touching engine."""
        app = MagicMock()
        app.engine = MagicMock()
        mock_askstring.return_value = None
        _run_powershell_dialog(app)
        app.engine.powershell.run_command.assert_not_called()

    def test_empty_cmd_returned_does_nothing(self):
        """If askstring returns empty string, function returns early."""
        app = MagicMock()
        app.engine = MagicMock()
        mock_askstring.return_value = ""
        _run_powershell_dialog(app)
        app.engine.powershell.run_command.assert_not_called()

    def test_no_engine_does_nothing(self):
        """If app has no engine attribute, function returns after askstring."""
        app = MagicMock(spec=["root"])
        app.root = MagicMock()
        mock_askstring.return_value = "Get-Process"
        _run_powershell_dialog(app)
        # No crash — engine attribute missing so inner block is skipped

    def test_engine_is_none_does_nothing(self):
        """If app.engine is None, function returns after askstring."""
        app = MagicMock()
        app.engine = None
        mock_askstring.return_value = "Get-Process"
        _run_powershell_dialog(app)
        # No crash

    def test_successful_command_displays_result(self):
        """Successful PS command shows stdout via app.root.after."""
        app = MagicMock()
        app.engine = MagicMock()
        result_mock = MagicMock()
        result_mock.stdout = "PID  Name"
        result_mock.stderr = ""
        app.engine.powershell.run_command.return_value = result_mock

        mock_askstring.return_value = "Get-Process"
        _run_powershell_dialog(app)

        # root.after should be called twice: configure + insert
        assert app.root.after.call_count == 2
        # Both calls use delay=0
        for call in app.root.after.call_args_list:
            assert call[0][0] == 0

    def test_successful_command_displays_stderr_fallback(self):
        """When stdout is empty, stderr is shown instead."""
        app = MagicMock()
        app.engine = MagicMock()
        result_mock = MagicMock()
        result_mock.stdout = ""
        result_mock.stderr = "warning output"
        app.engine.powershell.run_command.return_value = result_mock

        mock_askstring.return_value = "Get-Process"
        _run_powershell_dialog(app)

        assert app.root.after.call_count == 2

    def test_error_caught_and_displayed(self):
        """OSError from run_command is caught and error is displayed in chat."""
        app = MagicMock()
        app.engine = MagicMock()
        app.engine.powershell.run_command.side_effect = OSError("access denied")

        mock_askstring.return_value = "Get-Process"
        _run_powershell_dialog(app)

        # Error path also calls root.after twice (configure + insert)
        assert app.root.after.call_count == 2

    def test_runtime_error_caught_and_displayed(self):
        """RuntimeError from run_command is caught and displayed."""
        app = MagicMock()
        app.engine = MagicMock()
        app.engine.powershell.run_command.side_effect = RuntimeError("timeout")

        mock_askstring.return_value = "Write-Host hi"
        _run_powershell_dialog(app)

        assert app.root.after.call_count == 2

    def test_value_error_caught_and_displayed(self):
        """ValueError from run_command is caught and displayed."""
        app = MagicMock()
        app.engine = MagicMock()
        app.engine.powershell.run_command.side_effect = ValueError("bad input")

        mock_askstring.return_value = "test"
        _run_powershell_dialog(app)

        assert app.root.after.call_count == 2

    def test_error_no_chat_display_no_crash(self):
        """Error path when app has no chat_display should not crash."""
        app = MagicMock(spec=["root", "engine", "_t"])
        app.root = MagicMock()
        app.engine = MagicMock()
        app.engine.powershell.run_command.side_effect = OSError("fail")
        app._t = MagicMock(return_value="#e6edf3")

        mock_askstring.return_value = "cmd"
        _run_powershell_dialog(app)
        # Should not crash even without chat_display

    def test_success_no_chat_display_no_crash(self):
        """Success path when app has no chat_display should not crash."""
        app = MagicMock(spec=["root", "engine"])
        app.root = MagicMock()
        app.engine = MagicMock()
        result_mock = MagicMock()
        result_mock.stdout = "ok"
        result_mock.stderr = ""
        app.engine.powershell.run_command.return_value = result_mock

        mock_askstring.return_value = "cmd"
        _run_powershell_dialog(app)
        # Should not crash even without chat_display


# ---------------------------------------------------------------------------
# _run_it_script  (lines 512-535)
# ---------------------------------------------------------------------------


class TestRunItScript:
    """Cover lines 512-535: IT support script runner."""

    def test_script_path_not_found_returns_early(self):
        """If the script JSON file does not exist, return without error."""
        app = MagicMock()
        with patch.object(Path, "exists", return_value=False):
            _run_it_script(app, "nonexistent_script")
        # No engine interaction
        app.engine.assert_not_called()

    def test_no_engine_returns_early(self):
        """If app has no engine attribute, function returns after path check."""
        app = MagicMock(spec=[])
        with patch.object(Path, "exists", return_value=True):
            _run_it_script(app, "disk_cleanup")
        # No crash

    def test_engine_is_none_returns_early(self):
        """If app.engine is None, function returns after path check."""
        app = MagicMock()
        app.engine = None
        with patch.object(Path, "exists", return_value=True):
            _run_it_script(app, "disk_cleanup")
        # No crash

    def test_successful_script_shows_status(self):
        """Successful script run updates notes_label via root.after."""
        app = MagicMock()
        app.engine = MagicMock()

        result_mock = MagicMock()
        result_mock.success = True
        result_mock.steps_completed = 5
        result_mock.steps_total = 5

        with (
            patch.object(Path, "exists", return_value=True),
            patch("core.script_engine.ScriptEngine") as mock_se_cls,
        ):
            mock_se_instance = MagicMock()
            mock_se_instance.run_script.return_value = result_mock
            mock_se_cls.return_value = mock_se_instance

            _run_it_script(app, "disk_cleanup")

        app.root.after.assert_called_once()
        assert app.root.after.call_args[0][0] == 0

    def test_failed_script_shows_error_status(self):
        """Failed script result shows error via notes_label."""
        app = MagicMock()
        app.engine = MagicMock()

        result_mock = MagicMock()
        result_mock.success = False
        result_mock.error = "step 2 failed"

        with (
            patch.object(Path, "exists", return_value=True),
            patch("core.script_engine.ScriptEngine") as mock_se_cls,
        ):
            mock_se_instance = MagicMock()
            mock_se_instance.run_script.return_value = result_mock
            mock_se_cls.return_value = mock_se_instance

            _run_it_script(app, "network_diag")

        app.root.after.assert_called_once()

    def test_runtime_error_caught_and_displayed(self):
        """RuntimeError during script execution is caught and shown."""
        app = MagicMock()
        app.engine = MagicMock()

        with (
            patch.object(Path, "exists", return_value=True),
            patch("core.script_engine.ScriptEngine") as mock_se_cls,
        ):
            mock_se_instance = MagicMock()
            mock_se_instance.run_script.side_effect = RuntimeError("exec error")
            mock_se_cls.return_value = mock_se_instance

            _run_it_script(app, "service_restart")

        app.root.after.assert_called_once()

    def test_os_error_caught_and_displayed(self):
        """OSError during script execution is caught and shown."""
        app = MagicMock()
        app.engine = MagicMock()

        with (
            patch.object(Path, "exists", return_value=True),
            patch("core.script_engine.ScriptEngine") as mock_se_cls,
        ):
            mock_se_instance = MagicMock()
            mock_se_instance.run_script.side_effect = OSError("file missing")
            mock_se_cls.return_value = mock_se_instance

            _run_it_script(app, "event_log_errors")

        app.root.after.assert_called_once()

    def test_value_error_caught_and_displayed(self):
        """ValueError during script execution is caught and shown."""
        app = MagicMock()
        app.engine = MagicMock()

        with (
            patch.object(Path, "exists", return_value=True),
            patch("core.script_engine.ScriptEngine") as mock_se_cls,
        ):
            mock_se_instance = MagicMock()
            mock_se_instance.run_script.side_effect = ValueError("bad json")
            mock_se_cls.return_value = mock_se_instance

            _run_it_script(app, "temp_file_cleanup")

        app.root.after.assert_called_once()

    def test_import_error_caught_and_displayed(self):
        """ImportError during ScriptEngine import is caught and shown."""
        app = MagicMock()
        app.engine = MagicMock()

        with (
            patch.object(Path, "exists", return_value=True),
            patch("core.script_engine.ScriptEngine", side_effect=ImportError("no module")),
        ):
            _run_it_script(app, "software_inventory")

        app.root.after.assert_called_once()

    def test_error_no_notes_label_no_crash(self):
        """Error path when app has no notes_label should not crash."""
        app = MagicMock(spec=["root", "engine"])
        app.root = MagicMock()
        app.engine = MagicMock()

        with (
            patch.object(Path, "exists", return_value=True),
            patch("core.script_engine.ScriptEngine") as mock_se_cls,
        ):
            mock_se_instance = MagicMock()
            mock_se_instance.run_script.side_effect = RuntimeError("boom")
            mock_se_cls.return_value = mock_se_instance

            _run_it_script(app, "system_info_export")
        # Should not crash

    def test_success_no_notes_label_no_crash(self):
        """Success path when app has no notes_label should not crash."""
        app = MagicMock(spec=["root", "engine"])
        app.root = MagicMock()
        app.engine = MagicMock()

        result_mock = MagicMock()
        result_mock.success = True
        result_mock.steps_completed = 3
        result_mock.steps_total = 3

        with (
            patch.object(Path, "exists", return_value=True),
            patch("core.script_engine.ScriptEngine") as mock_se_cls,
        ):
            mock_se_instance = MagicMock()
            mock_se_instance.run_script.return_value = result_mock
            mock_se_cls.return_value = mock_se_instance

            _run_it_script(app, "restore_point_create")
        # Should not crash
