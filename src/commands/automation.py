"""
Mouse & Keyboard Automation Commands
Uses pyautogui for screen interaction.
"""
import re
import time
from datetime import datetime
from src.core.engine import CommandResult
from src.config import SCREENSHOT_DIR

# Try import pyautogui
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    PYAUTOGUI_OK = True
except Exception:
    pyautogui = None
    PYAUTOGUI_OK = False


class AutomationCommands:
    """Mouse and keyboard automation."""

    def __init__(self):
        self.available = PYAUTOGUI_OK

    def _check(self) -> CommandResult:
        if not self.available:
            return CommandResult(False, "pyautogui not available. Install with: pip install pyautogui")
        return None

    def screenshot(self) -> CommandResult:
        err = self._check()
        if err:
            return err
        try:
            ss = pyautogui.screenshot()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = SCREENSHOT_DIR / f"screenshot_{ts}.png"
            ss.save(str(path))
            return CommandResult(True, f"Screenshot saved: {path}", {"path": str(path)})
        except Exception as e:
            return CommandResult(False, f"Screenshot failed: {e}")

    def execute(self, text: str) -> CommandResult:
        err = self._check()
        if err:
            return err

        text_lower = text.lower().strip()

        # Click
        if text_lower.startswith("click"):
            return self._handle_click(text)

        # Type
        if text_lower.startswith("type "):
            content = text[5:].strip()
            pyautogui.typewrite(content, interval=0.02)
            return CommandResult(True, f"Typed: {content}")

        # Press key(s)
        if text_lower.startswith("press "):
            key = text[6:].strip()
            return self._handle_key_press(key)

        # Move mouse
        if text_lower.startswith("move"):
            return self._handle_move(text)

        # Scroll
        if text_lower.startswith("scroll"):
            return self._handle_scroll(text)

        # Drag
        if text_lower.startswith("drag"):
            return self._handle_drag(text)

        return CommandResult(False, f"Unknown automation command: {text}")

    def _handle_click(self, text: str) -> CommandResult:
        match = re.search(r'(\d+)\s*[,x]\s*(\d+)', text)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            # Parse click type
            if "right" in text.lower():
                pyautogui.rightClick(x, y)
                action = "Right-clicked"
            elif "double" in text.lower():
                pyautogui.doubleClick(x, y)
                action = "Double-clicked"
            else:
                pyautogui.click(x, y)
                action = "Clicked"
            return CommandResult(True, f"{action} at ({x}, {y})")
        else:
            pyautogui.click()
            pos = pyautogui.position()
            return CommandResult(True, f"Clicked at current position ({pos.x}, {pos.y})")

    def _handle_key_press(self, key: str) -> CommandResult:
        # Handle combos like ctrl+c, alt+tab
        if "+" in key:
            parts = [p.strip() for p in key.split("+")]
            # Map common names
            key_map = {
                "ctrl": "ctrl", "control": "ctrl",
                "alt": "alt", "option": "alt",
                "shift": "shift", "windows": "win", "win": "win", "super": "win",
                "esc": "escape", "escape": "escape",
                "enter": "enter", "return": "enter",
                "tab": "tab", "space": "space", "spacebar": "space",
                "backspace": "backspace", "delete": "delete", "del": "delete",
                "up": "up", "down": "down", "left": "left", "right": "right",
                "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
                "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
                "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
            }
            mapped = [key_map.get(p.lower(), p) for p in parts]
            pyautogui.hotkey(*mapped)
            return CommandResult(True, f"Pressed: {'+'.join(mapped)}")
        else:
            pyautogui.press(key)
            return CommandResult(True, f"Pressed: {key}")

    def _handle_move(self, text: str) -> CommandResult:
        match = re.search(r'(\d+)\s*[,x]\s*(\d+)', text)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            pyautogui.moveTo(x, y, duration=0.3)
            return CommandResult(True, f"Moved mouse to ({x}, {y})")
        return CommandResult(False, "Usage: move 500,300")

    def _handle_scroll(self, text: str) -> CommandResult:
        match = re.search(r'(-?\d+)', text)
        amount = int(match.group(1)) if match else -3
        pyautogui.scroll(amount)
        direction = "up" if amount > 0 else "down"
        return CommandResult(True, f"Scrolled {direction} {abs(amount)} clicks")

    def _handle_drag(self, text: str) -> CommandResult:
        # Parse: drag 100,200 to 300,400
        coords = re.findall(r'(\d+)\s*[,x]\s*(\d+)', text)
        if len(coords) >= 2:
            x1, y1 = int(coords[0][0]), int(coords[0][1])
            x2, y2 = int(coords[1][0]), int(coords[1][1])
            pyautogui.dragTo(x2, y2, duration=0.5)
            return CommandResult(True, f"Dragged from ({x1},{y1}) to ({x2},{y2})")
        return CommandResult(False, "Usage: drag 100,200 to 300,400")
