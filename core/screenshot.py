"""
Sentinel Desktop v2 — Screenshot capture and analysis utilities.
"""

import base64
import io
import logging
import time
from typing import Optional, Tuple

import pyautogui
from PIL import Image

logger = logging.getLogger(__name__)


def capture_screen() -> Image.Image:
    """Capture the full primary screen → PIL Image."""
    return pyautogui.screenshot()


def capture_region(x: int, y: int, w: int, h: int) -> Image.Image:
    """Capture a rectangular region of the screen → PIL Image."""
    img = pyautogui.screenshot(region=(x, y, w, h))
    return img


def capture_to_base64(quality: int = 85) -> str:
    """Capture full screen → base64-encoded JPEG string."""
    img = capture_screen()
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def capture_region_to_base64(x: int, y: int, w: int, h: int,
                             quality: int = 85) -> str:
    """Capture a screen region → base64 JPEG."""
    img = capture_region(x, y, w, h)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def image_to_base64(img: Image.Image, quality: int = 85) -> str:
    """Convert a PIL Image → base64 JPEG."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def base64_to_image(b64_str: str) -> Image.Image:
    """Convert a base64 string → PIL Image."""
    data = base64.b64decode(b64_str)
    return Image.open(io.BytesIO(data))


def find_template(template_path: str, confidence: float = 0.8) -> Optional[Tuple[int, int]]:
    """Find a template image on screen. Returns center (x, y) or None."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.error("opencv-python required for template matching")
        return None

    screenshot = pyautogui.screenshot()
    screen_arr = np.array(screenshot.convert("RGB"))
    screen_gray = cv2.cvtColor(screen_arr, cv2.COLOR_RGB2GRAY)

    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        logger.error("Template not found: %s", template_path)
        return None

    result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    if max_val >= confidence:
        h, w = template.shape
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        return (center_x, center_y)
    return None


def wait_for_template(template_path: str, timeout: float = 30,
                      confidence: float = 0.8,
                      poll_interval: float = 1.0) -> Optional[Tuple[int, int]]:
    """Poll until a template appears on screen or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        pos = find_template(template_path, confidence)
        if pos:
            return pos
        time.sleep(poll_interval)
    return None
