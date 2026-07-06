import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.commands.media as media_mod
from core.commands.media import MediaCommands


class TestMediaCommands:
    def setup_method(self):
        self.cmds = MediaCommands()
        self.mock_pag = MagicMock()

    def test_playback_play(self):
        with patch.object(media_mod, "PYAUTOGUI_OK", True):
            with patch.object(media_mod, "pyautogui", self.mock_pag):
                result = self.cmds.playback("play")
                assert result.success is True
                self.mock_pag.press.assert_called_once_with("playpause")

    def test_playback_next(self):
        with patch.object(media_mod, "PYAUTOGUI_OK", True):
            with patch.object(media_mod, "pyautogui", self.mock_pag):
                result = self.cmds.playback("next")
                assert result.success is True
                self.mock_pag.press.assert_called_once_with("nexttrack")

    def test_playback_prev(self):
        with patch.object(media_mod, "PYAUTOGUI_OK", True):
            with patch.object(media_mod, "pyautogui", self.mock_pag):
                result = self.cmds.playback("prev")
                assert result.success is True
                self.mock_pag.press.assert_called_once_with("prevtrack")

    def test_playback_invalid(self):
        with patch.object(media_mod, "PYAUTOGUI_OK", True):
            with patch.object(media_mod, "pyautogui", self.mock_pag):
                result = self.cmds.playback("fastforward")
                assert result.success is False

    def test_volume_mute(self):
        with patch.object(media_mod, "PYAUTOGUI_OK", True):
            with patch.object(media_mod, "pyautogui", self.mock_pag):
                result = self.cmds.volume("mute")
                assert result.success is True
                self.mock_pag.press.assert_called_once_with("volumemute")

    def test_volume_up(self):
        with patch.object(media_mod, "PYAUTOGUI_OK", True):
            with patch.object(media_mod, "pyautogui", self.mock_pag):
                result = self.cmds.volume("up")
                assert result.success is True
                assert self.mock_pag.press.call_count == 5

    def test_volume_unavailable(self):
        with patch.object(media_mod, "PYAUTOGUI_OK", False):
            result = self.cmds.volume("mute")
            assert result.success is False

    def test_execute_volume(self):
        with patch.object(self.cmds, "volume") as mock_vol:
            mock_vol.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("volume up")
            mock_vol.assert_called_once_with("up")

    def test_execute_play(self):
        with patch.object(self.cmds, "playback") as mock_pb:
            mock_pb.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("play")
            mock_pb.assert_called_once_with("play")

    def test_execute_next_track(self):
        with patch.object(self.cmds, "playback") as mock_pb:
            mock_pb.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("next track")
            mock_pb.assert_called_once_with("next")
