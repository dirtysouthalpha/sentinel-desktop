"""Core desktop automation: mouse, keyboard, screen capture."""

import base64
import io
import logging
import time

import pyautogui
from PIL import Image

logger = logging.getLogger(__name__)

pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True


class DesktopController:
    """Controls mouse, keyboard, and screen capture."""

    def __init__(self):
        self._screen_size = pyautogui.size()

    def screenshot(self) -> Image.Image:
        return pyautogui.screenshot()

    def screenshot_base64(self, format="PNG") -> str:
        img = self.screenshot()
        buf = io.BytesIO()
        img.save(buf, format=format)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def screenshot_region(self, x, y, w, h) -> Image.Image:
        return pyautogui.screenshot(region=(x, y, w, h))

    def get_screen_size(self) -> tuple:
        return self._screen_size

    def click(self, x, y, button="left", clicks=1):
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    def double_click(self, x, y):
        pyautogui.doubleClick(x=x, y=y)

    def right_click(self, x, y):
        pyautogui.rightClick(x=x, y=y)

    def move_to(self, x, y, duration=0.3):
        pyautogui.moveTo(x=x, y=y, duration=duration)

    def drag(self, from_x, from_y, to_x, to_y, duration=0.5, button="left"):
        pyautogui.moveTo(from_x, from_y)
        pyautogui.drag(to_x - from_x, to_y - from_y, duration=duration, button=button)

    def scroll(self, amount, x=None, y=None):
        pyautogui.scroll(amount, x=x, y=y)

    def get_mouse_position(self) -> tuple:
        return pyautogui.position()

    def type_text(self, text, interval=0.02):
        pyautogui.typewrite(text, interval=interval) if text.isascii() else pyautogui.write(
            text, interval=interval
        )

    def press_key(self, key):
        pyautogui.press(key)

    def hotkey(self, *keys):
        pyautogui.hotkey(*keys)

    def find_on_screen(self, template_path, confidence=0.8):
        try:
            import cv2
            import numpy as np

            template = cv2.imread(template_path, 0)
            screen = cv2.cvtColor(np.array(self.screenshot()), cv2.COLOR_RGB2GRAY)
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= confidence:
                h, w = template.shape
                return (max_loc[0] + w // 2, max_loc[1] + h // 2)
        except Exception as e:
            logger.error("find_on_screen failed: %s", e)
        return None

    def wait_for_image(self, template_path, timeout=30, confidence=0.8, interval=1):
        start = time.time()
        while time.time() - start < timeout:
            pos = self.find_on_screen(template_path, confidence)
            if pos:
                return pos
            time.sleep(interval)
        return None

    def click_image(self, template_path, confidence=0.8, button="left"):
        pos = self.find_on_screen(template_path, confidence)
        if pos:
            self.click(pos[0], pos[1], button=button)
            return True
        return False


# Alias for backward compatibility
DesktopEngine = DesktopController

# Module-level convenience functions
_ctrl = None


def _get_controller() -> DesktopController:
    global _ctrl
    if _ctrl is None:
        _ctrl = DesktopController()
    return _ctrl


def screenshot():
    return _get_controller().screenshot()


def screenshot_base64():
    return _get_controller().screenshot_base64()


def click(x, y, button="left", clicks=1):
    _get_controller().click(x, y, button=button, clicks=clicks)


def type_text(text, interval=0.02):
    _get_controller().type_text(text, interval=interval)


def press_key(key):
    _get_controller().press_key(key)


def hotkey(*keys):
    _get_controller().hotkey(*keys)


def scroll(amount, x=None, y=None):
    _get_controller().scroll(amount, x=x, y=y)
