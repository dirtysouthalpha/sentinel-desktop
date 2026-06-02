"""Sentinel Desktop v2 — Sound notifications.

Plays audio alerts when the agent finishes a run (success or error),
when MFA is detected, or on other significant events. Uses winsound on
Windows (no external deps) or falls back to printing BEL character.
"""

from __future__ import annotations

import logging
import threading

from core.utils import is_windows

logger = logging.getLogger(__name__)

_IS_WINDOWS = is_windows()

# Sleep intervals for sound sequences
MFA_BEEP_INTERVAL = 0.1
SUCCESS_TONE_INTERVAL = 0.05
ERROR_TONE_INTERVAL = 0.05


def play_sound(sound_type: str = "complete", blocking: bool = False) -> None:
    """Play a notification sound.

    sound_type: "complete" | "error" | "mfa" | "approval" | "click"
    blocking: if True, wait for sound to finish
    """
    if blocking:
        _play(sound_type)
    else:
        t = threading.Thread(target=_play, args=(sound_type,), daemon=True)
        t.start()


def _play(sound_type: str) -> None:
    """Produce the sound internally."""
    try:
        if _IS_WINDOWS:
            import winsound

            freq_map = {
                "complete": (800, 200),  # short high ping
                "error": (300, 500),  # long low buzz
                "mfa": (600, 150),  # urgent double beep
                "approval": (1000, 100),  # quick chirp
                "click": (1200, 50),  # tiny tick
            }
            freq, duration = freq_map.get(sound_type, (800, 200))

            if sound_type == "mfa":
                # Double beep for MFA urgency
                winsound.Beep(freq, duration)
                import time

                time.sleep(MFA_BEEP_INTERVAL)
                winsound.Beep(freq, duration)
            elif sound_type == "complete":
                # Two-tone success: low→high
                winsound.Beep(600, 100)
                import time

                time.sleep(SUCCESS_TONE_INTERVAL)
                winsound.Beep(900, 150)
            elif sound_type == "error":
                # Descending error tone
                winsound.Beep(400, 200)
                import time

                time.sleep(ERROR_TONE_INTERVAL)
                winsound.Beep(250, 300)
            else:
                winsound.Beep(freq, duration)
        else:
            # Non-Windows: print BEL character
            print("\a", end="", flush=True)
    except (OSError, RuntimeError) as exc:
        logger.warning("Sound playback failed: %s", exc)


def play_file(filepath: str, blocking: bool = False) -> None:
    """Play a WAV file (Windows only, no-op on other platforms)."""
    if not _IS_WINDOWS:
        return
    try:
        import winsound

        flags = winsound.SND_FILENAME | winsound.SND_NODEFAULT
        if not blocking:
            flags |= winsound.SND_ASYNC
        winsound.PlaySound(filepath, flags)
    except (OSError, RuntimeError) as exc:
        logger.warning("WAV playback failed: %s", exc)
