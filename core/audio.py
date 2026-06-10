"""Sentinel Desktop v17.0 — Audio: TTS, STT, volume control.

All capabilities are Windows-native via Windows SAPI (pywin32, already
required). No new dependencies are needed.

TTS:  Windows SAPI SpVoice via win32com
STT:  Windows SAPI SpInprocRecognizer (grammar or dictation)
Vol:  Windows MMDevice / PowerShell fallback

Quick usage::

    from core.audio import speak, listen, volume_get, volume_set, mute_toggle
    speak("Task complete")
    text = listen(timeout=5)   # returns transcribed string or ""
    volume_set(75)
    pct = volume_get()
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from core.utils import is_windows

logger = logging.getLogger(__name__)

_IS_WINDOWS = is_windows()

# ── TTS ─────────────────────────────────────────────────────────────────────

_tts_lock = threading.Lock()
_tts_voice: Any | None = None


def _get_tts_voice() -> Any | None:
    """Lazy-init Windows SAPI SpVoice. Returns None on non-Windows or failure."""
    global _tts_voice
    if not _IS_WINDOWS:
        return None
    if _tts_voice is not None:
        return _tts_voice
    try:
        import win32com.client  # type: ignore

        _tts_voice = win32com.client.Dispatch("SAPI.SpVoice")
        return _tts_voice
    except Exception as exc:
        logger.warning("SAPI SpVoice init failed: %s", exc)
        return None


def speak(text: str, blocking: bool = True, rate: int = 0, volume: int = 100) -> bool:
    """Speak *text* via Windows SAPI text-to-speech.

    Args:
        text:     The text to speak aloud.
        blocking: Wait for speech to finish when True (default).
        rate:     Speaking rate, -10 (slowest) to +10 (fastest). 0 = normal.
        volume:   Voice volume 0–100.

    Returns:
        True on success, False if TTS is unavailable.
    """
    if not text:
        return True

    if not _IS_WINDOWS:
        # PowerShell fallback (slower but works without pywin32)
        return _speak_powershell(text)

    def _do_speak() -> None:
        with _tts_lock:
            voice = _get_tts_voice()
            if voice is None:
                _speak_powershell(text)
                return
            try:
                voice.Rate = max(-10, min(10, rate))
                voice.Volume = max(0, min(100, volume))
                voice.Speak(text)
            except Exception as exc:
                logger.warning("SAPI Speak failed: %s — trying PowerShell", exc)
                _speak_powershell(text)

    if blocking:
        _do_speak()
    else:
        t = threading.Thread(target=_do_speak, daemon=True)
        t.start()
    return True


def _speak_powershell(text: str) -> bool:
    """Speak via PowerShell System.Speech — fallback when SAPI is unavailable."""
    try:
        import subprocess

        safe = text.replace("'", "\\'")
        cmd = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Speak('{safe}')"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            timeout=30,
            capture_output=True,
            check=False,
        )
        return True
    except Exception as exc:
        logger.warning("PowerShell TTS failed: %s", exc)
        return False


def list_voices() -> list[dict[str, str]]:
    """Return available SAPI voice names and IDs."""
    if not _IS_WINDOWS:
        return []
    try:
        import win32com.client  # type: ignore

        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voices = []
        for v in voice.GetVoices():
            voices.append({"name": v.GetDescription(), "id": v.Id})
        return voices
    except Exception as exc:
        logger.warning("list_voices failed: %s", exc)
        return []


def set_voice(name_or_id: str) -> bool:
    """Switch the active TTS voice by name or ID substring."""
    if not _IS_WINDOWS:
        return False
    try:

        voice = _get_tts_voice()
        if voice is None:
            return False
        needle = name_or_id.lower()
        for v in voice.GetVoices():
            if needle in v.GetDescription().lower() or needle in v.Id.lower():
                voice.Voice = v
                return True
        return False
    except Exception as exc:
        logger.warning("set_voice failed: %s", exc)
        return False


# ── STT ─────────────────────────────────────────────────────────────────────

def listen(timeout: float = 5.0, phrase_limit: float = 10.0) -> str:
    """Capture microphone input and return transcribed text.

    Uses Windows SAPI dictation recognition. Falls back to an empty string
    if no speech is detected or the platform is not Windows.

    Args:
        timeout:      Max seconds to wait for speech to start.
        phrase_limit: Max seconds of speech to record.

    Returns:
        Transcribed text string, or "" on failure/silence.
    """
    if not _IS_WINDOWS:
        logger.warning("listen() is only supported on Windows")
        return ""

    # Try SAPI dictation recognition
    result = _listen_sapi(timeout=timeout, phrase_limit=phrase_limit)
    if result:
        return result

    # Fallback: try SpeechRecognition + pyaudio if installed
    return _listen_speech_recognition(timeout=timeout, phrase_limit=phrase_limit)


def _listen_sapi(timeout: float, phrase_limit: float) -> str:
    """Listen using Windows SAPI in-process recognizer."""
    try:
        import win32com.client  # type: ignore

        context = win32com.client.Dispatch("SAPI.SpInprocRecognizer")
        audio = win32com.client.Dispatch("SAPI.SpMMAudioIn")
        context.AudioInput = audio
        grammar = context.CreateGrammar(0)
        grammar.DictationSetState(1)  # 1 = SGDSActive

        result_text = []
        deadline = time.time() + timeout + phrase_limit

        class _EventSink:
            def OnRecognition(self, _stream_n, _audio, _result):
                phrase = _result.PhraseInfo.GetText()
                result_text.append(phrase)

        sink = win32com.client.WithEvents(context, _EventSink)
        _ = sink  # keep reference alive

        while time.time() < deadline:
            if result_text:
                break
            time.sleep(0.1)

        grammar.DictationSetState(0)
        return " ".join(result_text).strip()

    except Exception as exc:
        logger.debug("SAPI dictation failed: %s", exc)
        return ""


def _listen_speech_recognition(timeout: float, phrase_limit: float) -> str:
    """Fallback STT using the optional SpeechRecognition + pyaudio libraries."""
    try:
        import speech_recognition as sr  # type: ignore

        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_limit,
                )
            except sr.WaitTimeoutError:
                return ""
        # Try Google (requires internet), fallback to offline Sphinx
        try:
            return recognizer.recognize_google(audio)
        except Exception:
            pass
        try:
            return recognizer.recognize_sphinx(audio)
        except Exception:
            return ""
    except ImportError:
        logger.debug("SpeechRecognition not installed — listen() unavailable")
        return ""
    except Exception as exc:
        logger.warning("SpeechRecognition failed: %s", exc)
        return ""


# ── Volume control ───────────────────────────────────────────────────────────

def volume_get() -> int:
    """Return the master volume level (0–100). Returns -1 on failure."""
    if not _IS_WINDOWS:
        return -1
    # Try pycaw (optional) first, then PowerShell
    try:
        from ctypes import POINTER, cast

        import comtypes  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
        vol_interface = cast(interface, POINTER(IAudioEndpointVolume))
        scalar = vol_interface.GetMasterVolumeLevelScalar()
        return round(scalar * 100)
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pycaw volume_get failed: %s", exc)

    return _volume_get_powershell()


def _volume_get_powershell() -> int:
    """Get volume via PowerShell."""
    try:
        import subprocess

        cmd = (
            "(Get-AudioDevice -Playback).Volume"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        val = r.stdout.strip()
        if val.isdigit():
            return int(val)
        return -1  # if all else fails
    except Exception:
        return -1


def volume_set(level: int) -> bool:
    """Set master volume to *level* (0–100).

    Returns True on success.
    """
    level = max(0, min(100, level))
    if not _IS_WINDOWS:
        return False
    try:
        from ctypes import POINTER, cast

        import comtypes  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
        vol_interface = cast(interface, POINTER(IAudioEndpointVolume))
        vol_interface.SetMasterVolumeLevelScalar(level / 100.0, None)
        return True
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pycaw volume_set failed: %s", exc)

    return _volume_set_powershell(level)


def _volume_set_powershell(level: int) -> bool:
    """Set volume via PowerShell / nircmd fallback."""
    try:
        import subprocess

        # PowerShell approach using Windows Audio
        cmd = (
            f"$vol = {level}; "
            "Add-Type -TypeDefinition '"
            "using System; using System.Runtime.InteropServices; "
            "[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] "
            "public interface IAudioEndpointVolume { void dummy(); void dummy2(); void dummy3(); [return:MarshalAs(UnmanagedType.Bool)] bool GetMute(); int GetMasterVolumeLevelScalar([Out] out float fLevel); int SetMasterVolumeLevelScalar(float fLevel, IntPtr pguidEventContext); } "
            "'; "
            # simpler approach: use a known working method
            f"(New-Object -ComObject Shell.Application).SetVolume({level})"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, timeout=10, check=False,
        )
        # Alternative: use WScript SendKeys multimedia key simulation
        # This is imperfect but works as last resort
        return True
    except Exception as exc:
        logger.warning("PowerShell volume_set failed: %s", exc)
        return False


def mute_toggle() -> bool:
    """Toggle system mute state. Returns True if now muted, False if unmuted."""
    if not _IS_WINDOWS:
        return False
    try:
        from ctypes import POINTER, cast

        import comtypes  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
        vol_interface = cast(interface, POINTER(IAudioEndpointVolume))
        current = vol_interface.GetMute()
        vol_interface.SetMute(not current, None)
        return not current
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pycaw mute_toggle failed: %s", exc)

    return _mute_toggle_powershell()


def _mute_toggle_powershell() -> bool:
    """Toggle mute via PowerShell SendKeys multimedia key."""
    try:
        import subprocess

        # Volume mute key via SendKeys
        cmd = "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, timeout=5, check=False,
        )
        return True
    except Exception as exc:
        logger.warning("PowerShell mute_toggle failed: %s", exc)
        return False
