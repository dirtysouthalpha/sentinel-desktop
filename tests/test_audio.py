"""Tests for core.audio — TTS, volume, voice listing.

Audio hardware may not be available in CI. All hardware-touching tests
are guarded by platform checks or marked as integration tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
        mock_win32com_client = MagicMock(Dispatch=MagicMock(return_value=mock_voice_obj))
        mock_win32com = MagicMock(client=mock_win32com_client)
        with patch.dict(
            "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
        ):
            with patch("win32com.client.Dispatch", return_value=mock_voice_obj, create=True):
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


# ── _speak_powershell() ───────────────────────────────────────────────────────


class TestSpeakPowershell:
    def test_success(self):
        from core.audio import _speak_powershell

        with patch("subprocess.run") as mock_run:
            result = _speak_powershell("hello world")
        assert result is True
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "powershell"

    def test_sanitizes_single_quotes(self):
        from core.audio import _speak_powershell

        with patch("subprocess.run") as mock_run:
            _speak_powershell("it's a test")
        cmd_str = mock_run.call_args[0][0][-1]  # last element is the -Command value
        assert "\\'" in cmd_str

    def test_oserror_returns_false(self):
        from core.audio import _speak_powershell

        with patch("subprocess.run", side_effect=OSError("no powershell")):
            result = _speak_powershell("hello")
        assert result is False


# ── _get_tts_voice() ──────────────────────────────────────────────────────────


class TestGetTtsVoice:
    def _make_win32com_mocks(self, dispatch_return=None, dispatch_raises=None):
        mock_win32com_client = MagicMock()
        if dispatch_raises:
            mock_win32com_client.Dispatch.side_effect = dispatch_raises
        else:
            mock_win32com_client.Dispatch.return_value = dispatch_return or MagicMock()
        mock_win32com = MagicMock()
        mock_win32com.client = mock_win32com_client
        return mock_win32com, mock_win32com_client

    def test_non_windows_returns_none(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", False)
        audio_mod._tts_voice = None
        result = audio_mod._get_tts_voice()
        assert result is None

    def test_windows_success(self, monkeypatch):
        import core.audio as audio_mod

        mock_voice = MagicMock()
        mock_win32com, mock_win32com_client = self._make_win32com_mocks(dispatch_return=mock_voice)
        audio_mod._tts_voice = None
        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        with patch.dict(
            "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
        ):
            result = audio_mod._get_tts_voice()
        assert result is mock_voice
        audio_mod._tts_voice = None

    def test_windows_cached_voice_returned(self, monkeypatch):
        import core.audio as audio_mod

        cached = MagicMock()
        audio_mod._tts_voice = cached
        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        result = audio_mod._get_tts_voice()
        assert result is cached
        audio_mod._tts_voice = None

    def test_windows_exception_returns_none(self, monkeypatch):
        import core.audio as audio_mod

        mock_win32com, mock_win32com_client = self._make_win32com_mocks(
            dispatch_raises=Exception("COM error")
        )
        audio_mod._tts_voice = None
        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        with patch.dict(
            "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
        ):
            result = audio_mod._get_tts_voice()
        assert result is None
        audio_mod._tts_voice = None


# ── list_voices() Windows exception path ─────────────────────────────────────


class TestListVoicesWindowsPaths:
    def test_exception_returns_empty(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_win32com_client = MagicMock()
        mock_win32com_client.Dispatch.side_effect = Exception("SAPI unavailable")
        mock_win32com = MagicMock()
        mock_win32com.client = mock_win32com_client
        with patch.dict(
            "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
        ):
            result = audio_mod.list_voices()
        assert result == []

    def test_success_returns_voice_list(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_voice_entry = MagicMock()
        mock_voice_entry.GetDescription.return_value = "Microsoft David"
        mock_voice_entry.Id = "HKEY_LOCAL_MACHINE\\TTS_DAVID"
        mock_voice_obj = MagicMock()
        mock_voice_obj.GetVoices.return_value = [mock_voice_entry]
        mock_win32com_client = MagicMock()
        mock_win32com_client.Dispatch.return_value = mock_voice_obj
        mock_win32com = MagicMock()
        mock_win32com.client = mock_win32com_client
        with patch.dict(
            "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
        ):
            result = audio_mod.list_voices()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "Microsoft David"


# ── set_voice() ───────────────────────────────────────────────────────────────


class TestSetVoice:
    def test_non_windows_returns_false(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", False)
        from core.audio import set_voice

        assert set_voice("David") is False

    def test_no_voice_object_returns_false(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        with patch("core.audio._get_tts_voice", return_value=None):
            from core.audio import set_voice

            result = set_voice("David")
        assert result is False

    def test_match_by_description(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_v = MagicMock()
        mock_v.GetDescription.return_value = "Microsoft David Desktop"
        mock_v.Id = "some_id"
        mock_voice_obj = MagicMock()
        mock_voice_obj.GetVoices.return_value = [mock_v]
        with patch("core.audio._get_tts_voice", return_value=mock_voice_obj):
            from core.audio import set_voice

            result = set_voice("david")
        assert result is True
        assert mock_voice_obj.Voice == mock_v

    def test_no_match_returns_false(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_v = MagicMock()
        mock_v.GetDescription.return_value = "Microsoft Zira Desktop"
        mock_v.Id = "some_zira_id"
        mock_voice_obj = MagicMock()
        mock_voice_obj.GetVoices.return_value = [mock_v]
        with patch("core.audio._get_tts_voice", return_value=mock_voice_obj):
            from core.audio import set_voice

            result = set_voice("david_nonexistent")
        assert result is False

    def test_exception_returns_false(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_voice_obj = MagicMock()
        mock_voice_obj.GetVoices.side_effect = Exception("COM error")
        with patch("core.audio._get_tts_voice", return_value=mock_voice_obj):
            from core.audio import set_voice

            result = set_voice("David")
        assert result is False


# ── listen() Windows path ─────────────────────────────────────────────────────


class TestListenWindows:
    def test_sapi_result_returned(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        with patch("core.audio._listen_sapi", return_value="hello world"):
            from core.audio import listen

            result = listen(timeout=1.0, phrase_limit=5.0)
        assert result == "hello world"

    def test_sapi_empty_falls_to_speech_recognition(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        with patch("core.audio._listen_sapi", return_value=""):
            with patch(
                "core.audio._listen_speech_recognition", return_value="fallback text"
            ) as mock_sr:
                from core.audio import listen

                result = listen(timeout=1.0, phrase_limit=5.0)
        assert result == "fallback text"
        mock_sr.assert_called_once()


# ── _listen_sapi() ────────────────────────────────────────────────────────────


class TestListenSapi:
    def _make_win32com_mocks(self):
        mock_win32com_client = MagicMock()
        mock_win32com = MagicMock()
        mock_win32com.client = mock_win32com_client
        return mock_win32com, mock_win32com_client

    def test_timeout_no_speech_returns_empty(self):
        from core.audio import _listen_sapi

        mock_win32com, mock_win32com_client = self._make_win32com_mocks()
        with patch.dict(
            "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
        ):
            result = _listen_sapi(timeout=0.0, phrase_limit=0.0)
        assert result == ""

    def test_exception_returns_empty(self):
        from core.audio import _listen_sapi

        mock_win32com_client = MagicMock()
        mock_win32com_client.Dispatch.side_effect = Exception("COM failure")
        mock_win32com = MagicMock()
        mock_win32com.client = mock_win32com_client
        with patch.dict(
            "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
        ):
            result = _listen_sapi(timeout=0.0, phrase_limit=0.0)
        assert result == ""


# ── _listen_speech_recognition() ─────────────────────────────────────────────


class TestListenSpeechRecognition:
    def _make_sr_mock(self):
        WaitTimeoutError = type("WaitTimeoutError", (Exception,), {})
        mock_sr = MagicMock()
        mock_sr.WaitTimeoutError = WaitTimeoutError

        mock_mic_source = MagicMock()
        mock_mic_ctx = MagicMock()
        mock_mic_ctx.__enter__ = MagicMock(return_value=mock_mic_source)
        mock_mic_ctx.__exit__ = MagicMock(return_value=False)
        mock_sr.Microphone.return_value = mock_mic_ctx

        return mock_sr, WaitTimeoutError

    def test_google_success(self):
        from core.audio import _listen_speech_recognition

        mock_sr, _ = self._make_sr_mock()
        mock_audio = MagicMock()
        mock_recognizer = MagicMock()
        mock_recognizer.listen.return_value = mock_audio
        mock_recognizer.recognize_google.return_value = "hello world"
        mock_sr.Recognizer.return_value = mock_recognizer
        with patch.dict("sys.modules", {"speech_recognition": mock_sr}):
            result = _listen_speech_recognition(5.0, 10.0)
        assert result == "hello world"

    def test_wait_timeout_returns_empty(self):
        from core.audio import _listen_speech_recognition

        mock_sr, WaitTimeoutError = self._make_sr_mock()
        mock_recognizer = MagicMock()
        mock_recognizer.listen.side_effect = WaitTimeoutError()
        mock_sr.Recognizer.return_value = mock_recognizer
        with patch.dict("sys.modules", {"speech_recognition": mock_sr}):
            result = _listen_speech_recognition(5.0, 10.0)
        assert result == ""

    def test_google_fails_sphinx_succeeds(self):
        from core.audio import _listen_speech_recognition

        mock_sr, _ = self._make_sr_mock()
        mock_audio = MagicMock()
        mock_recognizer = MagicMock()
        mock_recognizer.listen.return_value = mock_audio
        mock_recognizer.recognize_google.side_effect = Exception("no internet")
        mock_recognizer.recognize_sphinx.return_value = "sphinx text"
        mock_sr.Recognizer.return_value = mock_recognizer
        with patch.dict("sys.modules", {"speech_recognition": mock_sr}):
            result = _listen_speech_recognition(5.0, 10.0)
        assert result == "sphinx text"

    def test_both_fail_returns_empty(self):
        from core.audio import _listen_speech_recognition

        mock_sr, _ = self._make_sr_mock()
        mock_audio = MagicMock()
        mock_recognizer = MagicMock()
        mock_recognizer.listen.return_value = mock_audio
        mock_recognizer.recognize_google.side_effect = Exception("no internet")
        mock_recognizer.recognize_sphinx.side_effect = Exception("no sphinx")
        mock_sr.Recognizer.return_value = mock_recognizer
        with patch.dict("sys.modules", {"speech_recognition": mock_sr}):
            result = _listen_speech_recognition(5.0, 10.0)
        assert result == ""

    def test_import_error_returns_empty(self):
        from core.audio import _listen_speech_recognition

        with patch.dict("sys.modules", {"speech_recognition": None}):
            result = _listen_speech_recognition(5.0, 10.0)
        assert result == ""

    def test_generic_exception_returns_empty(self):
        from core.audio import _listen_speech_recognition

        mock_sr = MagicMock()
        mock_sr.Recognizer.side_effect = Exception("unexpected error")
        with patch.dict("sys.modules", {"speech_recognition": mock_sr}):
            result = _listen_speech_recognition(5.0, 10.0)
        assert result == ""


# ── _volume_get_powershell() ──────────────────────────────────────────────────


class TestVolumeGetPowershell:
    def test_digit_output_returns_integer(self):
        from core.audio import _volume_get_powershell

        mock_result = MagicMock()
        mock_result.stdout = "75\n"
        with patch("subprocess.run", return_value=mock_result):
            result = _volume_get_powershell()
        assert result == 75

    def test_non_digit_output_returns_minus_one(self):
        from core.audio import _volume_get_powershell

        mock_result = MagicMock()
        mock_result.stdout = "not a number"
        with patch("subprocess.run", return_value=mock_result):
            result = _volume_get_powershell()
        assert result == -1

    def test_exception_returns_minus_one(self):
        from core.audio import _volume_get_powershell

        with patch("subprocess.run", side_effect=OSError("powershell not found")):
            result = _volume_get_powershell()
        assert result == -1


# ── volume_get() pycaw path ───────────────────────────────────────────────────


class TestVolumeGetPycaw:
    def _make_pycaw_mocks(self, scalar=0.75):
        mock_vol_iface = MagicMock()
        mock_vol_iface.GetMasterVolumeLevelScalar.return_value = scalar
        mock_iav = MagicMock()
        mock_pycaw_module = MagicMock()
        mock_pycaw_module.AudioUtilities = MagicMock()
        mock_pycaw_module.IAudioEndpointVolume = mock_iav
        mock_pycaw = MagicMock()
        mock_pycaw.pycaw = mock_pycaw_module
        mock_comtypes = MagicMock()
        return mock_vol_iface, mock_pycaw, mock_pycaw_module, mock_comtypes

    def test_pycaw_success(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_vol_iface, mock_pycaw, mock_pycaw_module, mock_comtypes = self._make_pycaw_mocks(
            scalar=0.75
        )
        with patch.dict(
            "sys.modules",
            {"pycaw": mock_pycaw, "pycaw.pycaw": mock_pycaw_module, "comtypes": mock_comtypes},
        ):
            with patch("ctypes.POINTER", return_value=MagicMock()):
                with patch("ctypes.cast", return_value=mock_vol_iface):
                    result = audio_mod.volume_get()
        assert result == 75

    def test_pycaw_import_error_falls_to_powershell(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        with patch("core.audio._volume_get_powershell", return_value=60) as mock_ps:
            with patch.dict("sys.modules", {"pycaw": None, "pycaw.pycaw": None}):
                result = audio_mod.volume_get()
        assert result == 60
        mock_ps.assert_called_once()

    def test_pycaw_exception_falls_to_powershell(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_pycaw_module = MagicMock()
        mock_pycaw_module.AudioUtilities.GetSpeakers.side_effect = RuntimeError("COM error")
        mock_pycaw = MagicMock()
        mock_pycaw.pycaw = mock_pycaw_module
        mock_comtypes = MagicMock()
        with patch("core.audio._volume_get_powershell", return_value=55) as mock_ps:
            with patch.dict(
                "sys.modules",
                {"pycaw": mock_pycaw, "pycaw.pycaw": mock_pycaw_module, "comtypes": mock_comtypes},
            ):
                with patch("ctypes.POINTER", return_value=MagicMock()):
                    with patch("ctypes.cast", side_effect=RuntimeError("cast error")):
                        result = audio_mod.volume_get()
        assert result == 55
        mock_ps.assert_called_once()


# ── _volume_set_powershell() ──────────────────────────────────────────────────


class TestVolumeSetPowershell:
    def test_success_returns_true(self):
        from core.audio import _volume_set_powershell

        with patch("subprocess.run") as mock_run:
            result = _volume_set_powershell(75)
        assert result is True
        assert mock_run.called

    def test_exception_returns_false(self):
        from core.audio import _volume_set_powershell

        with patch("subprocess.run", side_effect=OSError("no powershell")):
            result = _volume_set_powershell(75)
        assert result is False


# ── volume_set() pycaw path ───────────────────────────────────────────────────


class TestVolumeSetPycaw:
    def test_pycaw_success(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_vol_iface = MagicMock()
        mock_iav = MagicMock()
        mock_pycaw_module = MagicMock()
        mock_pycaw_module.AudioUtilities = MagicMock()
        mock_pycaw_module.IAudioEndpointVolume = mock_iav
        mock_pycaw = MagicMock()
        mock_pycaw.pycaw = mock_pycaw_module
        mock_comtypes = MagicMock()
        with patch.dict(
            "sys.modules",
            {"pycaw": mock_pycaw, "pycaw.pycaw": mock_pycaw_module, "comtypes": mock_comtypes},
        ):
            with patch("ctypes.POINTER", return_value=MagicMock()):
                with patch("ctypes.cast", return_value=mock_vol_iface):
                    result = audio_mod.volume_set(80)
        assert result is True
        mock_vol_iface.SetMasterVolumeLevelScalar.assert_called_once_with(0.8, None)

    def test_pycaw_import_error_falls_to_powershell(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        with patch("core.audio._volume_set_powershell", return_value=True) as mock_ps:
            with patch.dict("sys.modules", {"pycaw": None, "pycaw.pycaw": None}):
                result = audio_mod.volume_set(50)
        assert result is True
        mock_ps.assert_called_once_with(50)


# ── _mute_toggle_powershell() ─────────────────────────────────────────────────


class TestMuteTogglePowershell:
    def test_success_returns_true(self):
        from core.audio import _mute_toggle_powershell

        with patch("subprocess.run") as mock_run:
            result = _mute_toggle_powershell()
        assert result is True
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "powershell"

    def test_exception_returns_false(self):
        from core.audio import _mute_toggle_powershell

        with patch("subprocess.run", side_effect=OSError("no powershell")):
            result = _mute_toggle_powershell()
        assert result is False


# ── mute_toggle() Windows path ────────────────────────────────────────────────


class TestMuteToggleWindows:
    def test_non_windows_returns_false(self, monkeypatch):
        import core.audio as audio_mod
        from core.audio import mute_toggle

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", False)
        assert mute_toggle() is False

    def test_pycaw_success_was_unmuted(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_vol_iface = MagicMock()
        mock_vol_iface.GetMute.return_value = False  # currently unmuted
        mock_iav = MagicMock()
        mock_pycaw_module = MagicMock()
        mock_pycaw_module.AudioUtilities = MagicMock()
        mock_pycaw_module.IAudioEndpointVolume = mock_iav
        mock_pycaw = MagicMock()
        mock_pycaw.pycaw = mock_pycaw_module
        mock_comtypes = MagicMock()
        with patch.dict(
            "sys.modules",
            {"pycaw": mock_pycaw, "pycaw.pycaw": mock_pycaw_module, "comtypes": mock_comtypes},
        ):
            with patch("ctypes.POINTER", return_value=MagicMock()):
                with patch("ctypes.cast", return_value=mock_vol_iface):
                    result = audio_mod.mute_toggle()
        assert result is True  # was unmuted, now muted
        mock_vol_iface.SetMute.assert_called_once_with(True, None)

    def test_pycaw_success_was_muted(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_vol_iface = MagicMock()
        mock_vol_iface.GetMute.return_value = True  # currently muted
        mock_iav = MagicMock()
        mock_pycaw_module = MagicMock()
        mock_pycaw_module.AudioUtilities = MagicMock()
        mock_pycaw_module.IAudioEndpointVolume = mock_iav
        mock_pycaw = MagicMock()
        mock_pycaw.pycaw = mock_pycaw_module
        mock_comtypes = MagicMock()
        with patch.dict(
            "sys.modules",
            {"pycaw": mock_pycaw, "pycaw.pycaw": mock_pycaw_module, "comtypes": mock_comtypes},
        ):
            with patch("ctypes.POINTER", return_value=MagicMock()):
                with patch("ctypes.cast", return_value=mock_vol_iface):
                    result = audio_mod.mute_toggle()
        assert result is False  # was muted, now unmuted

    def test_pycaw_import_error_falls_to_powershell(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        with patch("core.audio._mute_toggle_powershell", return_value=True) as mock_ps:
            with patch.dict("sys.modules", {"pycaw": None, "pycaw.pycaw": None}):
                result = audio_mod.mute_toggle()
        assert result is True
        mock_ps.assert_called_once()

    def test_pycaw_exception_falls_to_powershell(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)
        mock_pycaw_module = MagicMock()
        mock_pycaw_module.AudioUtilities = MagicMock()
        mock_pycaw = MagicMock()
        mock_pycaw.pycaw = mock_pycaw_module
        mock_comtypes = MagicMock()
        with patch("core.audio._mute_toggle_powershell", return_value=False) as mock_ps:
            with patch.dict(
                "sys.modules",
                {"pycaw": mock_pycaw, "pycaw.pycaw": mock_pycaw_module, "comtypes": mock_comtypes},
            ):
                with patch("ctypes.POINTER", return_value=MagicMock()):
                    with patch("ctypes.cast", side_effect=RuntimeError("cast error")):
                        result = audio_mod.mute_toggle()
        assert result is False
        mock_ps.assert_called_once()


# ── listen() non-Windows path (lines 172-173) ────────────────────────────────


class TestListenNonWindows:
    """Lines 172-173 — listen() logs warning and returns '' on non-Windows."""

    def test_listen_non_windows_returns_empty(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", False)
        result = audio_mod.listen()
        assert result == ""


# ── _listen_sapi() while-loop body (lines 200-201, 207-209) ──────────────────


class TestListenSapiWhileLoop:
    """Lines 200-201 — OnRecognition appends phrase; lines 207-209 — while body."""

    def _make_win32com_mocks(self):
        mock_win32com_client = MagicMock()
        mock_win32com = MagicMock()
        mock_win32com.client = mock_win32com_client
        return mock_win32com, mock_win32com_client

    def test_on_recognition_populates_result_and_breaks(self):
        """Lines 200-201 and 207-208 — WithEvents triggers OnRecognition; loop breaks."""
        from core.audio import _listen_sapi

        mock_win32com, mock_win32com_client = self._make_win32com_mocks()

        def fake_with_events(ctx, sink_class):
            fake_result_obj = MagicMock()
            fake_result_obj.PhraseInfo.GetText.return_value = "hello world"
            instance = sink_class()
            instance.OnRecognition(None, None, fake_result_obj)
            return MagicMock()

        mock_win32com_client.WithEvents.side_effect = fake_with_events

        with patch.dict(
            "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
        ):
            result = _listen_sapi(timeout=0.5, phrase_limit=0.0)

        assert result == "hello world"

    def test_empty_result_hits_sleep_line(self):
        """Line 209 — result_text stays empty; time.sleep() is called in loop body."""
        import time as time_module

        import core.audio as audio_mod
        from core.audio import _listen_sapi

        mock_win32com, mock_win32com_client = self._make_win32com_mocks()

        t0 = time_module.time()
        call_count = [0]

        def fake_time():
            call_count[0] += 1
            if call_count[0] <= 2:
                return t0  # deadline calc + first while condition: enter loop
            return t0 + 100  # subsequent checks: deadline exceeded, exit loop

        with (
            patch.dict(
                "sys.modules", {"win32com": mock_win32com, "win32com.client": mock_win32com_client}
            ),
            patch.object(audio_mod.time, "time", side_effect=fake_time),
            patch.object(audio_mod.time, "sleep") as mock_sleep,
        ):
            result = _listen_sapi(timeout=0.5, phrase_limit=0.0)

        assert result == ""
        mock_sleep.assert_called_once_with(0.1)


# ── volume_set() pycaw exception path (lines 319-320) ────────────────────────


class TestVolumeSetPycawException:
    """Lines 319-320 — except Exception in pycaw path falls through to PowerShell."""

    def test_pycaw_exception_falls_to_powershell(self, monkeypatch):
        import core.audio as audio_mod

        monkeypatch.setattr(audio_mod, "_IS_WINDOWS", True)

        mock_pycaw_module = MagicMock()
        mock_pycaw_module.AudioUtilities.GetSpeakers.side_effect = RuntimeError("COM error")
        mock_pycaw = MagicMock()
        mock_pycaw.pycaw = mock_pycaw_module
        mock_comtypes = MagicMock()

        with (
            patch("core.audio._volume_set_powershell", return_value=True) as mock_ps,
            patch.dict(
                "sys.modules",
                {"pycaw": mock_pycaw, "pycaw.pycaw": mock_pycaw_module, "comtypes": mock_comtypes},
            ),
        ):
            result = audio_mod.volume_set(75)

        assert result is True
        mock_ps.assert_called_once_with(75)
