"""Sentinel Desktop v22.0 — Voice Engine.

Wraps ``core/audio.py`` (v17 TTS/STT/volume) with:
- A ``VoiceMode`` state machine (IDLE / LISTENING / SPEAKING / AMBIENT).
- Ambient wake-word monitoring via a background polling loop.
- A configurable ``on_wake`` callback invoked when the wake word is detected.

No new pip dependencies — uses the existing SAPI ``listen()`` for keyword
detection, which gracefully degrades to ``""`` on non-Windows hosts.

Usage::

    from core.voice import VoiceEngine

    def handle_wake(transcript: str) -> None:
        print("Heard:", transcript)

    engine = VoiceEngine(wake_word="sentinel", on_wake=handle_wake)
    engine.start_ambient()
    # … later …
    engine.stop_ambient()
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from enum import Enum

from core.audio import listen, speak

logger = logging.getLogger(__name__)


class VoiceMode(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    SPEAKING = "speaking"
    AMBIENT = "ambient"


class VoiceEngine:
    """Stateful voice engine with ambient wake-word monitoring.

    Args:
        wake_word:      Keyword or phrase to listen for in ambient mode.
        listen_timeout: Seconds per listen() poll cycle in ambient mode.
        on_wake:        Callback(transcript) fired when the wake word is detected.
    """

    def __init__(
        self,
        wake_word: str = "sentinel",
        listen_timeout: float = 3.0,
        on_wake: Callable[[str], None] | None = None,
    ) -> None:
        self.wake_word = wake_word.lower()
        self.listen_timeout = listen_timeout
        self.on_wake = on_wake
        self._mode = VoiceMode.IDLE
        self._mode_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    # Mode state
    # ------------------------------------------------------------------

    @property
    def mode(self) -> VoiceMode:
        with self._mode_lock:
            return self._mode

    def _set_mode(self, mode: VoiceMode) -> None:
        with self._mode_lock:
            self._mode = mode

    # ------------------------------------------------------------------
    # Ambient mode
    # ------------------------------------------------------------------

    def start_ambient(self) -> bool:
        """Start background wake-word polling. Returns False if already running."""
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._set_mode(VoiceMode.AMBIENT)
        self._thread = threading.Thread(
            target=self._ambient_loop, daemon=True, name="VoiceAmbient"
        )
        self._thread.start()
        logger.info("VoiceEngine ambient mode started (wake_word=%r)", self.wake_word)
        return True

    def stop_ambient(self) -> bool:
        """Stop background wake-word polling. Returns False if not running."""
        if not (self._thread and self._thread.is_alive()):
            return False
        self._stop.set()
        self._thread.join(timeout=self.listen_timeout + 2)
        self._set_mode(VoiceMode.IDLE)
        logger.info("VoiceEngine ambient mode stopped")
        return True

    @property
    def is_ambient(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _ambient_loop(self) -> None:
        while not self._stop.is_set():
            transcript = listen(timeout=self.listen_timeout, phrase_limit=5.0)
            if transcript and self.wake_word in transcript.lower():
                logger.info("Wake word %r detected in: %r", self.wake_word, transcript)
                self._set_mode(VoiceMode.LISTENING)
                if self.on_wake:
                    try:
                        self.on_wake(transcript)
                    except Exception as exc:
                        logger.warning("on_wake callback error: %s", exc)
                if not self._stop.is_set():
                    self._set_mode(VoiceMode.AMBIENT)

    # ------------------------------------------------------------------
    # Speak / listen wrappers
    # ------------------------------------------------------------------

    def speak(self, text: str, blocking: bool = True) -> bool:
        """Speak text via TTS, temporarily entering SPEAKING mode."""
        prev = self.mode
        self._set_mode(VoiceMode.SPEAKING)
        result = speak(text, blocking=blocking)
        self._set_mode(prev)
        return result

    def listen_once(self, timeout: float | None = None) -> str:
        """Capture a single microphone utterance and return the transcript."""
        self._set_mode(VoiceMode.LISTENING)
        transcript = listen(timeout=timeout if timeout is not None else self.listen_timeout)
        self._set_mode(VoiceMode.IDLE)
        return transcript

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, object]:
        """Return current engine state as a plain dict."""
        return {
            "mode": self.mode.value,
            "wake_word": self.wake_word,
            "is_ambient": self.is_ambient,
        }


# Process-wide singleton (lazy-init)
_engine: VoiceEngine | None = None


def get_voice_engine() -> VoiceEngine:
    global _engine
    if _engine is None:
        _engine = VoiceEngine()
    return _engine
