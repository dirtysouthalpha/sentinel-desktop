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
        try:
            self._screen_size: tuple[int, int] = pyautogui.size()
        except Exception:
            logger.warning("Could not detect screen size, defaulting to 1920x1080")
            self._screen_size = (1920, 1080)

    def screenshot(self) -> Image.Image:
        try:
            return pyautogui.screenshot()
        except Exception as exc:
            logger.error("screenshot failed: %s", exc)
            raise

    def screenshot_base64(self, format: str = "PNG") -> str:
        try:
            img = self.screenshot()
            buf = io.BytesIO()
            img.save(buf, format=format)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as exc:
            logger.error("screenshot_base64 failed: %s", exc)
            raise

    def screenshot_region(self, x: int, y: int, w: int, h: int) -> Image.Image:
        try:
            return pyautogui.screenshot(region=(x, y, w, h))
        except Exception as exc:
            logger.error("screenshot_region(%d,%d,%d,%d) failed: %s", x, y, w, h, exc)
            raise

    def get_screen_size(self) -> tuple[int, int]:
        return self._screen_size

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        try:
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        except pyautogui.FailSafeException:
            raise
        except Exception as exc:
            logger.error("click(%d, %d) failed: %s", x, y, exc)
            raise

    def double_click(self, x: int, y: int) -> None:
        try:
            pyautogui.doubleClick(x=x, y=y)
        except pyautogui.FailSafeException:
            raise
        except Exception as exc:
            logger.error("double_click(%d, %d) failed: %s", x, y, exc)
            raise

    def right_click(self, x: int, y: int) -> None:
        try:
            pyautogui.rightClick(x=x, y=y)
        except pyautogui.FailSafeException:
            raise
        except Exception as exc:
            logger.error("right_click(%d, %d) failed: %s", x, y, exc)
            raise

    def move_to(self, x: int, y: int, duration: float = 0.3) -> None:
        try:
            pyautogui.moveTo(x=x, y=y, duration=duration)
        except pyautogui.FailSafeException:
            raise
        except Exception as exc:
            logger.error("move_to(%d, %d) failed: %s", x, y, exc)
            raise

    def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        duration: float = 0.5,
        button: str = "left",
    ) -> None:
        try:
            pyautogui.moveTo(from_x, from_y)
            pyautogui.drag(to_x - from_x, to_y - from_y, duration=duration, button=button)
        except pyautogui.FailSafeException:
            raise
        except Exception as exc:
            logger.error("drag(%d,%d -> %d,%d) failed: %s", from_x, from_y, to_x, to_y, exc)
            raise

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        try:
            pyautogui.scroll(amount, x=x, y=y)
        except pyautogui.FailSafeException:
            raise
        except Exception as exc:
            logger.error("scroll(%d) failed: %s", amount, exc)
            raise

    def get_mouse_position(self) -> tuple[int, int]:
        return pyautogui.position()

    def type_text(self, text: str, interval: float = 0.02) -> None:
        try:
            pyautogui.write(text, interval=interval)
        except Exception as exc:
            logger.error("type_text(%r…) failed: %s", text[:40], exc)
            raise

    def press_key(self, key: str) -> None:
        try:
            pyautogui.press(key)
        except Exception as exc:
            logger.error("press_key(%r) failed: %s", key, exc)
            raise

    def hotkey(self, *keys: str) -> None:
        try:
            pyautogui.hotkey(*keys)
        except Exception as exc:
            logger.error("hotkey(%s) failed: %s", "+".join(keys), exc)
            raise

    def find_on_screen(self, template_path: str, confidence: float = 0.8) -> tuple[int, int] | None:
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            logger.error("find_on_screen requires opencv-python: %s", exc)
            return None
        try:
            template = cv2.imread(template_path, 0)
            if template is None:
                logger.error("find_on_screen: could not read template %s", template_path)
                return None
            screen = cv2.cvtColor(np.array(self.screenshot()), cv2.COLOR_RGB2GRAY)
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= confidence:
                h, w = template.shape
                return (max_loc[0] + w // 2, max_loc[1] + h // 2)
        except Exception as exc:
            logger.error("find_on_screen failed: %s", exc)
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
