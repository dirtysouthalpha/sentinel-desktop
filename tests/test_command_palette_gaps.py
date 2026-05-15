"""Gap tests for command_palette.py — helper functions with error handling."""

from unittest.mock import MagicMock

from core.command_palette import (
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
