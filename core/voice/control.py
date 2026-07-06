"""
Sentinel Desktop v30.0.0 - Voice Control.
"""
from __future__ import annotations
import logging, shutil, subprocess, sys
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)
WAKE_WORD = "hey sentinel"

@dataclass
class VoiceResult:
    success: bool
    text: str = ""
    error: str = ""

def text_to_speech(text, rate=180):
    if not text:
        return VoiceResult(success=False, error="Empty text")
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.say(text)
        engine.runAndWait()
        return VoiceResult(success=True, text=text)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("pyttsx3 TTS failed: %s", e)
    if shutil.which("espeak"):
        try:
            subprocess.run(["espeak", text], check=True, timeout=10)
            return VoiceResult(success=True, text=text)
        except Exception as e:
            logger.debug("espeak failed: %s", e)
    if sys.platform == "darwin" and shutil.which("say"):
        try:
            subprocess.run(["say", text], check=True, timeout=10)
            return VoiceResult(success=True, text=text)
        except Exception as e:
            logger.debug("say failed: %s", e)
    return VoiceResult(success=False, error="No TTS engine available")

def speech_to_text(audio_path=None):
    try:
        import whisper
        model = whisper.load_model("base")
        if audio_path:
            result = model.transcribe(audio_path)
        else:
            return VoiceResult(success=False, error="Live recording not implemented")
        return VoiceResult(success=True, text=result.get("text", "").strip())
    except ImportError:
        return VoiceResult(success=False, error="Whisper not installed")
    except Exception as e:
        return VoiceResult(success=False, error=str(e))

def check_wake_word(text):
    return WAKE_WORD in text.lower().strip()

def extract_goal(text):
    lower = text.lower()
    if WAKE_WORD in lower:
        idx = lower.index(WAKE_WORD) + len(WAKE_WORD)
        return text[idx:].strip()
    return text.strip()

def get_voice_status():
    status = {"tts_engine": "none", "stt_engine": "none", "wake_word": WAKE_WORD}
    try:
        import pyttsx3
        pyttsx3.init()
        status["tts_engine"] = "pyttsx3"
    except Exception:
        if shutil.which("espeak"):
            status["tts_engine"] = "espeak"
        elif sys.platform == "darwin" and shutil.which("say"):
            status["tts_engine"] = "say"
    try:
        import whisper
        status["stt_engine"] = "whisper"
    except ImportError:
        pass
    return status
