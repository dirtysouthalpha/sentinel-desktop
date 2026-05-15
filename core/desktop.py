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

    def __init__(self) -> None:
        self._screen_size: tuple[int, int] = pyautogui.size()

    def screenshot(self) -> Image.Image:
        return pyautogui.screenshot()

    def screenshot_base64(self, format: str = "PNG") -> str:
        img = self.screenshot()
        buf = io.BytesIO()
        img.save(buf, format=format)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def screenshot_region(self, x: int, y: int, w: int, h: int) -> Image.Image:
        return pyautogui.screenshot(region=(x, y, w, h))

    def get_screen_size(self) -> tuple[int, int]:
        return self._screen_size

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    def double_click(self, x: int, y: int) -> None:
        pyautogui.doubleClick(x=x, y=y)

    def right_click(self, x: int, y: int) -> None:
        pyautogui.rightClick(x=x, y=y)

    def move_to(self, x: int, y: int, duration: float = 0.3) -> None:
        pyautogui.moveTo(x=x, y=y, duration=duration)

    def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        duration: float = 0.5,
        button: str = "left",
    ) -> None:
        pyautogui.moveTo(from_x, from_y)
        pyautogui.drag(to_x - from_x, to_y - from_y, duration=duration, button=button)

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        pyautogui.scroll(amount, x=x, y=y)

    def get_mouse_position(self) -> tuple[int, int]:
        return pyautogui.position()

    def type_text(self, text: str, interval: float = 0.02) -> None:
        # pyautogui.write() handles arbitrary text via clipboard fallback.
        # pyautogui.typewrite() only works with single key names like 'enter'.
        pyautogui.write(text, interval=interval)

    def press_key(self, key: str) -> None:
        pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        pyautogui.hotkey(*keys)

    def find_on_screen(self, template_path: str, confidence: float = 0.8) -> tuple[int, int] | None:
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

    def wait_for_image(
        self, template_path: str, timeout: float = 30, confidence: float = 0.8, interval: float = 1
    ) -> tuple[int, int] | None:
        start = time.time()
        while time.time() - start < timeout:
            pos = self.find_on_screen(template_path, confidence)
            if pos:
                return pos
            time.sleep(interval)
        return None

    def click_image(
        self, template_path: str, confidence: float = 0.8, button: str = "left"
    ) -> bool:
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


def screenshot() -> Image.Image:
    return _get_controller().screenshot()


def screenshot_base64() -> str:
    return _get_controller().screenshot_base64()


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    _get_controller().click(x, y, button=button, clicks=clicks)


def type_text(text: str, interval: float = 0.02) -> None:
    _get_controller().type_text(text, interval=interval)


def press_key(key: str) -> None:
    _get_controller().press_key(key)


def hotkey(*keys: str) -> None:
    _get_controller().hotkey(*keys)


def scroll(amount: int, x: int | None = None, y: int | None = None) -> None:
    _get_controller().scroll(amount, x=x, y=y)
