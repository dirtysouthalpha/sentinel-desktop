"""Tests for core/sound.py — notification sound playback."""

import sys
from unittest.mock import MagicMock, patch

from core.sound import _play, play_file, play_sound


def _mock_winsound():
    """Create a fresh winsound mock with standard constants."""
    mock = MagicMock()
    mock.Beep = MagicMock()
    mock.PlaySound = MagicMock()
    mock.SND_FILENAME = 0x00020000
    mock.SND_NODEFAULT = 0x0002
    mock.SND_ASYNC = 0x0001
    return mock


class TestPlaySound:
    @patch("core.sound._play")
    def test_blocking_calls_play_directly(self, mock_play):
        play_sound("complete", blocking=True)
        mock_play.assert_called_once_with("complete")

    @patch("core.sound._play")
    def test_non_blocking_spawns_thread(self, mock_play):
        play_sound("complete", blocking=False)
        import time

        time.sleep(0.2)
        mock_play.assert_called_once_with("complete")

    @patch("core.sound._play")
    def test_default_sound_type(self, mock_play):
        play_sound(blocking=True)
        mock_play.assert_called_once_with("complete")


class TestPlay:
    @patch("core.sound._IS_WINDOWS", False)
    def test_non_windows_prints_bel(self, capsys):
        _play("complete")
        captured = capsys.readouterr()
        assert "\a" in captured.out

    def test_windows_plays_default_beep(self):
        mock_ws = _mock_winsound()
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                _play("approval")
                mock_ws.Beep.assert_called_once_with(1000, 100)

    def test_windows_mfa_double_beep(self):
        mock_ws = _mock_winsound()
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                _play("mfa")
                assert mock_ws.Beep.call_count == 2

    def test_windows_complete_two_tone(self):
        mock_ws = _mock_winsound()
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                _play("complete")
                assert mock_ws.Beep.call_count == 2
                calls = mock_ws.Beep.call_args_list
                assert calls[0][0] == (600, 100)
                assert calls[1][0] == (900, 150)

    def test_windows_error_descending(self):
        mock_ws = _mock_winsound()
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                _play("error")
                assert mock_ws.Beep.call_count == 2

    def test_windows_unknown_type_uses_default(self):
        mock_ws = _mock_winsound()
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                _play("unknown_sound")
                mock_ws.Beep.assert_called_once_with(800, 200)

    def test_exception_is_caught(self):
        mock_ws = _mock_winsound()
        mock_ws.Beep.side_effect = RuntimeError("boom")
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                _play("click")  # should not raise


class TestPlayFile:
    @patch("core.sound._IS_WINDOWS", False)
    def test_non_windows_is_noop(self):
        play_file("/some/file.wav", blocking=True)

    def test_windows_blocking(self):
        mock_ws = _mock_winsound()
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                play_file("test.wav", blocking=True)
                mock_ws.PlaySound.assert_called_once()
                flags = mock_ws.PlaySound.call_args[0][1]
                assert not (flags & mock_ws.SND_ASYNC)

    def test_windows_non_blocking(self):
        mock_ws = _mock_winsound()
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                play_file("test.wav", blocking=False)
                flags = mock_ws.PlaySound.call_args[0][1]
                assert flags & mock_ws.SND_ASYNC

    def test_exception_is_caught(self):
        mock_ws = _mock_winsound()
        mock_ws.PlaySound.side_effect = RuntimeError("fail")
        with patch.dict(sys.modules, {"winsound": mock_ws}):
            with patch("core.sound._IS_WINDOWS", True):
                play_file("bad.wav", blocking=True)  # should not raise
