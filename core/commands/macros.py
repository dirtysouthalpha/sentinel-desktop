"""Macro recording and playback commands."""
import json
import time
from pathlib import Path
from core.legacy_engine import CommandResult


MACRO_DIR = Path(__file__).parent.parent.parent / "macros"


class MacroCommands:
    """Record, save, and replay macro sequences."""

    def __init__(self):
        self.recording = False
        self.recorded_actions = []
        self.macros = {}

    def start_recording(self) -> CommandResult:
        """Start recording a macro."""
        if self.recording:
            return CommandResult(False, "Already recording")
        self.recording = True
        self.recorded_actions = []
        return CommandResult(True, "Recording started. Perform actions now.")

    def record_action(self, action: str):
        """Record a single action."""
        if self.recording:
            self.recorded_actions.append({"action": action, "timestamp": time.time()})

    def stop_recording(self) -> CommandResult:
        """Stop recording and return the macro."""
        if not self.recording:
            return CommandResult(False, "Not currently recording")
        self.recording = False
        count = len(self.recorded_actions)
        return CommandResult(True, f"Recording stopped. {count} actions captured.")

    def save_macro(self, name: str) -> CommandResult:
        """Save a recorded macro to disk."""
        if not self.recorded_actions:
            return CommandResult(False, "No actions to save")
        MACRO_DIR.mkdir(parents=True, exist_ok=True)
        filepath = MACRO_DIR / f"{name}.json"
        data = {"name": name, "actions": self.recorded_actions}
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        self.macros[name] = self.recorded_actions
        return CommandResult(True, f"Macro saved: {name} ({len(self.recorded_actions)} actions)")

    def load_macro(self, name: str) -> CommandResult:
        """Load a saved macro from disk."""
        filepath = MACRO_DIR / f"{name}.json"
        if not filepath.exists():
            return CommandResult(False, f"Macro not found: {name}")
        with open(filepath) as f:
            data = json.load(f)
        self.macros[name] = data.get("actions", [])
        return CommandResult(True, f"Macro loaded: {name} ({len(self.macros[name])} actions)")

    def list_macros(self) -> CommandResult:
        """List all saved macros."""
        MACRO_DIR.mkdir(parents=True, exist_ok=True)
        saved = [f.stem for f in MACRO_DIR.glob("*.json")]
        if not saved:
            return CommandResult(True, "No saved macros")
        lines = "\n".join([f"  - {m}" for m in sorted(saved)])
        return CommandResult(True, "Saved macros:\n" + lines)

    def delete_macro(self, name: str) -> CommandResult:
        """Delete a saved macro."""
        filepath = MACRO_DIR / f"{name}.json"
        if not filepath.exists():
            return CommandResult(False, f"Macro not found: {name}")
        filepath.unlink()
        if name in self.macros:
            del self.macros[name]
        return CommandResult(True, f"Macro deleted: {name}")

    def execute(self, text: str) -> CommandResult:
        """Parse and execute macro commands."""
        t = text.lower().strip()
        if t in ["start recording", "record macro", "begin recording"]:
            return self.start_recording()
        if t in ["stop recording", "end recording"]:
            return self.stop_recording()
        if t.startswith("save macro"):
            parts = text.split(None, 2)
            if len(parts) >= 3:
                return self.save_macro(parts[2])
            return CommandResult(False, "Usage: save macro <name>")
        if t.startswith("load macro"):
            parts = text.split(None, 2)
            if len(parts) >= 3:
                return self.load_macro(parts[2])
            return CommandResult(False, "Usage: load macro <name>")
        if "list macro" in t or t == "macros":
            return self.list_macros()
        if t.startswith("delete macro"):
            parts = text.split(None, 2)
            name = parts[2] if len(parts) >= 3 else ""
            return self.delete_macro(name)
        return CommandResult(False, f"Unknown macro command: {text}")
