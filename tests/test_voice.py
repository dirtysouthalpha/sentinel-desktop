import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.commands.voice import VoiceCommands


class TestVoiceCommands:
    def setup_method(self):
        self.cmds = VoiceCommands()

    @patch("src.commands.voice.subprocess.Popen")
    def test_speak(self, mock_popen):
        self.cmds.tts_engine = "espeak"
        result = self.cmds.speak("hello world")
        assert result.success is True

    def test_speak_no_engine(self):
        self.cmds.tts_engine = "none"
        result = self.cmds.speak("hello")
        assert result.success is False

    def test_listen_no_engine(self):
        self.cmds.stt_engine = "none"
        result = self.cmds.listen()
        assert result.success is False

    def test_listen_with_engine(self):
        self.cmds.stt_engine = "whisper"
        result = self.cmds.listen()
        assert result.success is True

    def test_status(self):
        result = self.cmds.status()
        assert result.success is True
        assert "TTS" in result.message
        assert "STT" in result.message

    def test_execute_speak(self):
        with patch.object(self.cmds, "speak") as mock_speak:
            mock_speak.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("speak hello")
            mock_speak.assert_called_once()

    def test_execute_listen(self):
        with patch.object(self.cmds, "listen") as mock_listen:
            mock_listen.return_value = MagicMock(success=True, message="ok")
            self.cmds.execute("listen")
            mock_listen.assert_called_once()

    def test_execute_status(self):
        result = self.cmds.execute("voice status")
        assert result.success is True

    def test_execute_unknown(self):
        result = self.cmds.execute("sing")
        assert result.success is False
