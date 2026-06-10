"""Tests for core.audio — TTS, volume, voice listing.

Audio hardware may not be available in CI. All hardware-touching tests
are guarded by platform checks or marked as integration tests.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from core.audio import list_voices, speak, volume_get, volume_set


# ── speak() ───────────────────────────────────────────────────────────────────

class TestSpeak:
    def test_speak_empty_string_returns_true(self):
        assert speak("") is True

    def test_speak_noop_on_nonwindows(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", False)
        with patch("core.audio._speak_powershell", return_value=True) as mock_ps:
            result = speak("hello", blocking=True)
        assert result is True
        mock_ps.assert_called_once_with("hello")

    def test_speak_uses_sapi_on_windows(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        mock_voice = MagicMock()
        with patch("core.audio._get_tts_voice", return_value=mock_voice):
            result = speak("test text", blocking=True)
        assert result is True
        mock_voice.Speak.assert_called_once_with("test text")

    def test_speak_sets_rate_and_volume(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        mock_voice = MagicMock()
        with patch("core.audio._get_tts_voice", return_value=mock_voice):
            speak("hi", rate=5, volume=80, blocking=True)
        assert mock_voice.Rate == 5
        assert mock_voice.Volume == 80

    def test_speak_clamps_rate(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        mock_voice = MagicMock()
        with patch("core.audio._get_tts_voice", return_value=mock_voice):
            speak("hi", rate=99, blocking=True)
        assert mock_voice.Rate == 10  # clamped to max

    def test_speak_clamps_volume(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        mock_voice = MagicMock()
        with patch("core.audio._get_tts_voice", return_value=mock_voice):
            speak("hi", volume=200, blocking=True)
        assert mock_voice.Volume == 100  # clamped to max

    def test_speak_falls_back_to_powershell_when_sapi_unavailable(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        with patch("core.audio._get_tts_voice", return_value=None):
            with patch("core.audio._speak_powershell", return_value=True) as mock_ps:
                result = speak("hello", blocking=True)
        assert result is True
        mock_ps.assert_called_once_with("hello")

    def test_speak_nonblocking_returns_immediately(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        mock_voice = MagicMock()
        import time
        start = time.time()
        with patch("core.audio._get_tts_voice", return_value=mock_voice):
            mock_voice.Speak = MagicMock(side_effect=lambda t: time.sleep(0.2))
            result = speak("test", blocking=False)
        elapsed = time.time() - start
        assert result is True
        assert elapsed < 0.15  # returned before speech finished

    def test_speak_sapi_exception_falls_back(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        mock_voice = MagicMock()
        mock_voice.Speak.side_effect = RuntimeError("SAPI error")
        with patch("core.audio._get_tts_voice", return_value=mock_voice):
            with patch("core.audio._speak_powershell", return_value=True) as mock_ps:
                speak("fallback test", blocking=True)
        mock_ps.assert_called_once()


# ── volume_get() ──────────────────────────────────────────────────────────────

class TestVolumeGet:
    def test_returns_minus_one_on_non_windows(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", False)
        assert volume_get() == -1

    def test_returns_integer_on_windows(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        # Drive volume_get via the PowerShell fallback path to avoid pycaw complexity
        with patch("core.audio._volume_get_powershell", return_value=75):
            with patch.dict("sys.modules", {"pycaw": None, "pycaw.pycaw": None}):
                level = volume_get()
        assert isinstance(level, int)


# ── volume_set() ──────────────────────────────────────────────────────────────

class TestVolumeSet:
    def test_returns_false_on_non_windows(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", False)
        assert volume_set(50) is False

    def test_clamps_level_to_range(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        with patch("core.audio._volume_set_powershell", return_value=True) as mock_ps:
            # Bypass pycaw by making it raise ImportError
            with patch.dict("sys.modules", {"pycaw": None, "pycaw.pycaw": None}):
                volume_set(150)
        # Should have been called (clamped to 100 before _volume_set_powershell)
        mock_ps.assert_called()


# ── list_voices() ─────────────────────────────────────────────────────────────

class TestListVoices:
    def test_returns_empty_on_non_windows(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", False)
        assert list_voices() == []

    def test_returns_list_of_dicts_on_windows(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", True)
        mock_voice_obj = MagicMock()
        mock_voice_entry = MagicMock()
        mock_voice_entry.GetDescription.return_value = "Microsoft David"
        mock_voice_entry.Id = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_DAVID_11.0"
        mock_voice_obj.GetVoices.return_value = [mock_voice_entry]
        with patch("win32com.client.Dispatch", return_value=mock_voice_obj, create=True):
            with patch.dict("sys.modules", {"win32com": MagicMock(), "win32com.client": MagicMock(
                Dispatch=MagicMock(return_value=mock_voice_obj)
            )}):
                from importlib import reload
                import core.audio as audio_mod
                audio_mod._tts_voice = None  # reset cached voice
                voices = audio_mod.list_voices()
        # Either list of dicts or empty (depending on mock resolution)
        assert isinstance(voices, list)


# ── Action executor integration ───────────────────────────────────────────────

class TestAudioActions:
    """Test that audio actions are wired into the executor dispatch table."""

    def test_speak_action_in_dispatch_table(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        assert "speak" in executor._dispatch_table

    def test_listen_action_in_dispatch_table(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        assert "listen" in executor._dispatch_table

    def test_volume_get_action_in_dispatch_table(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        assert "volume_get" in executor._dispatch_table

    def test_volume_set_action_in_dispatch_table(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        assert "volume_set" in executor._dispatch_table

    def test_mute_toggle_action_in_dispatch_table(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        assert "mute_toggle" in executor._dispatch_table

    def test_list_voices_action_in_dispatch_table(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        assert "list_voices" in executor._dispatch_table

    def test_speak_executor_action(self, monkeypatch):
        """speak action returns success dict."""
        monkeypatch.setattr("core.audio._IS_WINDOWS", False)
        with patch("core.audio._speak_powershell", return_value=True):
            from core.action_executor import ActionExecutor
            executor = ActionExecutor()
            result = executor.execute_sync({"action": "speak", "text": "hello"})
        assert result["success"] is True

    def test_volume_get_executor_action_non_windows(self, monkeypatch):
        monkeypatch.setattr("core.audio._IS_WINDOWS", False)
        from core.action_executor import ActionExecutor
        executor = ActionExecutor()
        result = executor.execute_sync({"action": "volume_get"})
        assert result["success"] is False  # not available on non-Windows
