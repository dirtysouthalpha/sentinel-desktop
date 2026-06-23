"""Media control commands."""
import subprocess
import platform
from src.core.engine import CommandResult

try:
    import pyautogui
    PYAUTOGUI_OK = True
except Exception:
    pyautogui = None
    PYAUTOGUI_OK = False


class MediaCommands:
    """Control volume, media playback."""

    def volume(self, action: str = "level") -> CommandResult:
        """Get or set system volume using keyboard fallback."""
        try:
            if not PYAUTOGUI_OK:
                return CommandResult(False, "Volume control not available")
            if action == "level":
                return CommandResult(True, "Volume control requires pycaw for level reading")
            elif action == "mute":
                pyautogui.press("volumemute")
                return CommandResult(True, "Volume toggled")
            elif action == "up":
                for _ in range(5):
                    pyautogui.press("volumeup")
                return CommandResult(True, "Volume increased")
            elif action == "down":
                for _ in range(5):
                    pyautogui.press("volumedown")
                return CommandResult(True, "Volume decreased")
            return CommandResult(False, f"Unknown volume action: {action}")
        except Exception as e:
            return CommandResult(False, f"Volume control failed: {e}")

    def playback(self, action: str) -> CommandResult:
        """Control media playback."""
        try:
            if not PYAUTOGUI_OK:
                return CommandResult(False, "Media control not available")
            key_map = {
                "play": "playpause",
                "pause": "playpause",
                "next": "nexttrack",
                "prev": "prevtrack",
                "previous": "prevtrack",
                "stop": "mediastop",
            }
            key = key_map.get(action.lower())
            if key:
                pyautogui.press(key)
                return CommandResult(True, f"Media: {action}")
            return CommandResult(False, f"Unknown playback action: {action}")
        except Exception as e:
            return CommandResult(False, f"Playback control failed: {e}")

    def execute(self, text: str) -> CommandResult:
        """Parse and execute media commands."""
        t = text.lower().strip()
        if t.startswith("volume"):
            parts = t.split()
            if len(parts) == 1:
                return self.volume("level")
            return self.volume(parts[1])
        if t in ["mute", "unmute"]:
            return self.volume(t)
        if t in ["play", "pause", "next", "prev", "previous", "stop"]:
            return self.playback(t)
        if ("play" in t or "pause" in t) and "track" not in t:
            return self.playback("play")
        if "next" in t and ("track" in t or "song" in t or "media" in t):
            return self.playback("next")
        if "previous" in t or ("prev" in t and ("track" in t or "song" in t)):
            return self.playback("prev")
        return CommandResult(False, f"Unknown media command: {text}")
