"""Voice command integration - speech-to-text and text-to-speech."""
import platform
import shutil
import subprocess

from core.legacy_engine import CommandResult
from core.powershell import _ps_escape_single_quoted


class VoiceCommands:
    """Handle voice input and output."""

    def __init__(self):
        self.tts_engine = self._detect_tts_engine()
        self.stt_engine = self._detect_stt_engine()

    def _detect_tts_engine(self) -> str:
        """Detect available TTS engine."""
        if shutil.which("espeak"):
            return "espeak"
        if shutil.which("flite"):
            return "flite"
        if shutil.which("say"):
            return "say"
        if platform.system() == "Windows":
            return "sapi"
        return "none"

    def _detect_stt_engine(self) -> str:
        """Detect available STT engine."""
        if shutil.which("whisper"):
            return "whisper"
        # NB: this had a leading space pre-v31, so the lookup could never hit.
        if shutil.which("pocketsphinx_continuous"):
            return "pocketsphinx"
        return "none"

    def speak(self, text: str) -> CommandResult:
        """Speak text using available TTS engine."""
        if self.tts_engine == "none":
            return CommandResult(False, "No TTS engine available")
        try:
            engine = self.tts_engine
            if engine == "espeak":
                subprocess.Popen(["espeak", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif engine == "flite":
                subprocess.Popen(["flite", "-t", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif engine == "say":
                subprocess.Popen(["say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif engine == "sapi":
                # A single quote in *text* closed the literal and appended
                # arbitrary PowerShell pre-v31; escape it properly.
                try:
                    ps_text = _ps_escape_single_quoted(text)
                except (TypeError, ValueError) as exc:
                    return CommandResult(False, f"Unsafe speech text: {exc}")
                ps_cmd = (
                    "Add-Type -AssemblyName System.Speech; "
                    f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak({ps_text})"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-command", ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return CommandResult(True, f"Speaking: {text[:50]}")
        except FileNotFoundError:
            return CommandResult(False, "TTS engine not found")
        except Exception as e:
            return CommandResult(False, f"TTS failed: {e}")

    def listen(self) -> CommandResult:
        """Listen for voice input (placeholder for STT)."""
        if self.stt_engine == "none":
            return CommandResult(False, "No STT engine available")
        return CommandResult(True, "Listening... (STT placeholder)")

    def status(self) -> CommandResult:
        """Report voice engine status."""
        return CommandResult(True, f"TTS: {self.tts_engine} | STT: {self.stt_engine}")

    def execute(self, text: str) -> CommandResult:
        """Parse and execute voice commands."""
        t = text.lower().strip()
        if t.startswith("speak ") or t.startswith("say "):
            parts = text.split(None, 1)
            msg = parts[1] if len(parts) > 1 else ""
            return self.speak(msg)
        if t in ["listen", "start listening"]:
            return self.listen()
        if "voice status" in t or "voice info" in t:
            return self.status()
        return CommandResult(False, f"Unknown voice command: {text}")
