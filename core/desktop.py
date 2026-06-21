"""Sentinel Desktop v3.0 — Core desktop automation utilities.

Provides functions for mouse, keyboard, and screen capture operations.
Cross-platform desktop automation with error handling and logging.
"""

import base64
import io
import logging
import time

from PIL import Image

from core import humanize
from core.humanize import motion as _humanize_motion
from core.humanize import profile as _humanize_profile
from core.humanize import rng as _humanize_rng
from core.humanize import timing as _humanize_timing
from core.humanize import typing as _humanize_typing

logger = logging.getLogger(__name__)

# Lazy import pyautogui to avoid DISPLAY requirement on headless systems
pyautogui = None


class _FailSafeSentinelError(Exception):
    """Sentinel used when pyautogui has not been imported yet."""


_FailSafeException: type[Exception] = _FailSafeSentinelError


def _ensure_pyautogui():
    """Import pyautogui on first use to avoid headless system failures.

    Returns None (rather than raising) when pyautogui cannot be imported —
    e.g. on a headless Linux box with no DISPLAY, pyautogui's import eagerly
    reads ``os.environ['DISPLAY']`` via mouseinfo and raises ``KeyError``.
    Callers must tolerate a None return by degrading gracefully (the
    DesktopController falls back to default screen size + blank screenshots).
    """
    global pyautogui, _FailSafeException
    if pyautogui is None:
        try:
            import pyautogui as _pyautogui

            pyautogui = _pyautogui
            _FailSafeException = pyautogui.FailSafeException
            pyautogui.PAUSE = 0.1
            pyautogui.FAILSAFE = True
        except (KeyError, ImportError, OSError, RuntimeError, AttributeError) as exc:
            # KeyError: 'DISPLAY' on headless Linux (mouseinfo reads os.environ at import).
            # ImportError: pyautogui not installed.
            # The rest are defensive. We log + leave pyautogui as None; callers degrade.
            logger.warning(
                "pyautogui unavailable (%s: %s); input/capture will degrade.",
                type(exc).__name__, exc,
            )
            return None
    return pyautogui


def _is_stealth_profile(profile) -> bool:
    """Check if a profile is a StealthProfile (type-check compatible).

    Avoids circular import by checking attribute instead of isinstance.
    """
    return hasattr(profile, "scroll_momentum")


class DesktopController:
    """Controls mouse, keyboard, and screen capture."""

    def __init__(self) -> None:
        """Initialize the controller and detect the current screen resolution."""
        try:
            pg = _ensure_pyautogui()
            self._screen_size: tuple[int, int] = (
                pg.size() if pg is not None else (1920, 1080)
            )
        except (OSError, RuntimeError, ValueError, KeyError):
            logger.warning("Could not detect screen size, defaulting to 1920x1080")
            self._screen_size = (1920, 1080)
        # v23 cross-platform: route input through the platform backend when
        # pyautogui is unavailable (headless Linux). See _backend_input.
        try:
            from core.platform import get_backend
            self._backend_input = get_backend().input
        except Exception:  # pragma: no cover - defensive
            self._backend_input = None

    @property
    def _use_backend_input(self) -> bool:
        """True when input should route through the platform backend (not pyautogui).

        Routing prefers pyautogui when it's available (Windows/Mac and
        Linux-with-a-display) so existing behavior is byte-identical there.
        When pyautogui is None (headless Linux / no DISPLAY), the platform
        backend (.input) handles click/type/scroll/etc via xdotool.
        """
        return pyautogui is None and self._backend_input is not None

    def screenshot(self) -> Image.Image:
        """Take a full-screen screenshot.

        Returns:
            PIL.Image: A full-screen RGB screenshot. Returns a blank
            placeholder image on capture failure.

        """
        try:
            if self._use_backend_input:
                return self._backend_input.screenshot()
            _ensure_pyautogui()
            return pyautogui.screenshot()
        except (OSError, RuntimeError, AttributeError) as exc:
            logger.warning("screenshot failed: %s", exc)
            return Image.new("RGB", self._screen_size)

    def screenshot_base64(self, format: str = "PNG") -> str:
        """Return a base64-encoded screenshot string.

        Args:
            format: Image format passed to PIL save (e.g. ``"PNG"``, ``"JPEG"``).

        Returns:
            str: Base64-encoded image string, or empty string on failure.

        """
        try:
            img = self.screenshot()
            buf = io.BytesIO()
            img.save(buf, format=format)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except (OSError, ValueError) as exc:
            logger.warning("screenshot_base64 failed: %s", exc)
            return ""

    def screenshot_region(self, x: int, y: int, w: int, h: int) -> Image.Image:
        """Capture a screenshot of the specified region.

        Args:
            x: Left edge X coordinate in pixels.
            y: Top edge Y coordinate in pixels.
            w: Width of the region in pixels.
            h: Height of the region in pixels.

        Returns:
            PIL.Image: RGB image of the region, or a blank placeholder on failure.

        """
        try:
            if self._use_backend_input:
                # Backend screenshot is full-screen; crop to the requested region.
                full = self._backend_input.screenshot()
                return full.crop((x, y, x + w, y + h))
            _ensure_pyautogui()
            return pyautogui.screenshot(region=(x, y, w, h))
        except (OSError, RuntimeError, AttributeError) as exc:
            logger.warning("screenshot_region failed: %s", exc)
            return Image.new("RGB", (w, h))

    def get_screen_size(self) -> tuple[int, int]:
        """Return the detected screen resolution as (width, height).

        Returns:
            tuple[int, int]: Screen width and height in pixels.

        """
        return self._screen_size

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        target_size: tuple[int, int] | None = None,
    ) -> None:
        """Click at the specified screen coordinates.

        Args:
            x: X coordinate in pixels.
            y: Y coordinate in pixels.
            button: Mouse button to click (``"left"``, ``"right"``, ``"middle"``).
            clicks: Number of times to click (1 for single, 2 for double-click).
            target_size: Optional target dimensions (width, height) for stealth-tier
                Fitts's-Law timing and overshoot/correction.

        """
        try:
            if self._use_backend_input:
                # Headless Linux: route through the platform backend (xdotool).
                self._backend_input.click(x, y, button=button, clicks=clicks)
                return
            _ensure_pyautogui()
            if humanize.is_enabled():
                self._humanized_move_and_click(
                    x, y, button=button, clicks=clicks, target_size=target_size
                )
            else:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("click failed: %s", exc)

    def double_click(self, x: int, y: int) -> None:
        """Double-click at the specified screen coordinates.

        Args:
            x: X coordinate in pixels.
            y: Y coordinate in pixels.

        """
        try:
            if self._use_backend_input:
                self._backend_input.doubleClick(x, y)
                return
            _ensure_pyautogui()
            if humanize.is_enabled():
                self._humanized_move_and_click(x, y, button="left", clicks=2)
            else:
                pyautogui.doubleClick(x=x, y=y)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("double_click failed: %s", exc)

    def right_click(self, x: int, y: int) -> None:
        """Right-click at the specified screen coordinates.

        Args:
            x: X coordinate in pixels.
            y: Y coordinate in pixels.

        """
        try:
            if self._use_backend_input:
                self._backend_input.rightClick(x, y)
                return
            _ensure_pyautogui()
            if humanize.is_enabled():
                self._humanized_move_and_click(x, y, button="right", clicks=1)
            else:
                pyautogui.rightClick(x=x, y=y)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("right_click failed: %s", exc)

    def _humanized_move_and_click(
        self,
        x: int,
        y: int,
        *,
        button: str,
        clicks: int,
        target_size: tuple[int, int] | None = None,
    ) -> None:
        """Move to (x, y) along a humanized curve, then click.

        Args:
            x: X coordinate in pixels.
            y: Y coordinate in pixels.
            button: Mouse button to click.
            clicks: Number of times to click (1 for single, 2 for double-click).
            target_size: Optional target dimensions for stealth-tier Fitts's-Law
                timing and overshoot/correction.

        Falls back to a plain moveTo+click if the humanized path raises.
        """
        try:
            self._humanized_move_to(x, y, target_size=target_size)
        except Exception as exc:  # noqa: BLE001 — never let humanization block input
            logger.debug("humanized move fell back to linear: %s", exc)
            try:
                pyautogui.moveTo(x=x, y=y)
            except (_FailSafeException, OSError, RuntimeError, AttributeError):
                pass
        # Click with a humanized down→up hold between repeated clicks.
        hold = None
        try:
            hold = _humanize_timing.click_hold_duration(
                rng=_humanize_rng.get_rng(), profile=_humanize_profile.get_default_profile()
            )
        except Exception:  # noqa: BLE001
            hold = None
        for i in range(max(1, clicks)):
            pyautogui.click(x=x, y=y, button=button, clicks=1)
            if hold and i < clicks - 1:
                time.sleep(hold)

    def _humanized_move_to(
        self, x: int, y: int, target_size: tuple[int, int] | None = None
    ) -> None:
        """Replay a humanized trajectory as a sequence of micro moveTo calls.

        Args:
            x: X coordinate in pixels.
            y: Y coordinate in pixels.
            target_size: Optional target dimensions for stealth-tier Fitts's-Law
                timing and overshoot/correction.
        """
        start = self.get_mouse_position()
        trajectory = _humanize_motion.humanized_path(
            start,
            (int(x), int(y)),
            target_size=target_size,
            rng=_humanize_rng.get_rng(),
            profile=_humanize_profile.get_default_profile(),
        )
        for (px, py), dwell in trajectory:
            pyautogui.moveTo(int(px), int(py), _pause=False)
            if dwell > 0:
                time.sleep(dwell)

    def move_to(self, x: int, y: int, duration: float = 0.3) -> None:
        """Move the mouse cursor to the specified coordinates.

        Args:
            x: Target X coordinate in pixels.
            y: Target Y coordinate in pixels.
            duration: Time in seconds to animate the movement (used only when
                humanization is disabled; the humanized path derives its own
                eased timing).

        """
        try:
            if self._use_backend_input:
                self._backend_input.moveTo(x, y, duration=duration)
                return
            _ensure_pyautogui()
            if humanize.is_enabled():
                self._humanized_move_to(x, y)
            else:
                pyautogui.moveTo(x=x, y=y, duration=duration)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("move_to failed: %s", exc)

    def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        duration: float = 0.5,
        button: str = "left",
    ) -> None:
        """Drag from one point to another.

        Args:
            from_x: Starting X coordinate in pixels.
            from_y: Starting Y coordinate in pixels.
            to_x: Destination X coordinate in pixels.
            to_y: Destination Y coordinate in pixels.
            duration: Time in seconds for the drag movement.
            button: Mouse button to hold during drag (``"left"`` or ``"right"``).

        """
        try:
            if self._use_backend_input:
                self._backend_input.drag(
                    from_x, from_y, to_x, to_y, duration=duration, button=button
                )
                return
            _ensure_pyautogui()
            pyautogui.moveTo(from_x, from_y)
            pyautogui.drag(to_x - from_x, to_y - from_y, duration=duration, button=button)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("drag failed: %s", exc)

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        """Scroll the mouse wheel by *amount* clicks at the given coordinates.

        Args:
            amount: Number of scroll clicks. Positive scrolls up, negative scrolls down.
            x: X coordinate to position the cursor before scrolling, or None.
            y: Y coordinate to position the cursor before scrolling, or None.

        """
        try:
            if self._use_backend_input:
                self._backend_input.scroll(amount, x=x, y=y)
                return
            _ensure_pyautogui()
            # Stealth-tier: momentum scroll trajectory for StealthProfile
            if humanize.is_enabled():
                profile = _humanize_profile.get_default_profile()
                if _is_stealth_profile(profile):
                    self._momentum_scroll(amount, x=x, y=y, profile=profile)  # type: ignore[arg-type]
                    return

            pyautogui.scroll(amount, x=x, y=y)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("scroll failed: %s", exc)

    def get_mouse_position(self) -> tuple[int, int]:
        """Return the current mouse cursor position as (x, y).

        Returns:
            tuple[int, int]: Current (x, y) cursor position, or (0, 0) on failure.

        """
        try:
            if self._use_backend_input:
                return self._backend_input.position()
            _ensure_pyautogui()
            return pyautogui.position()
        except (OSError, RuntimeError, AttributeError) as exc:
            logger.warning("get_mouse_position failed: %s", exc)
            return (0, 0)

    def type_text(self, text: str, interval: float = 0.02) -> None:
        """Type the given text string using simulated keystrokes.

        Args:
            text: The string to type.
            interval: Seconds between each keystroke (used only when
                humanization is disabled; the humanized path samples per-key
                delays from a real distribution).

        """
        try:
            if self._use_backend_input:
                self._backend_input.type_text(text)
                return
            _ensure_pyautogui()
            if humanize.is_enabled() and len(text) > 1:
                self._humanized_type(text)
            else:
                pyautogui.write(text, interval=interval)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("type_text failed: %s", exc)

    def _humanized_type(self, text: str) -> None:
        """Type `text` with per-keystroke cadence sampled from a human distribution.

        Falls back to pyautogui.write if the humanized path raises.
        """
        try:
            delays = _humanize_typing.keystroke_delays(
                text,
                rng=_humanize_rng.get_rng(),
                profile=_humanize_profile.get_default_profile(),
            )
        except Exception:  # noqa: BLE001 — never let humanization block typing
            pyautogui.write(text, interval=0.02)
            return
        for i, ch in enumerate(text):
            pyautogui.press(ch)
            if i < len(delays):
                time.sleep(delays[i])

    def _momentum_scroll(self, amount: int, x: int | None, y: int | None, profile) -> None:
        """Scroll with inertial momentum for StealthProfile.

        Args:
            amount: Number of scroll clicks (positive = up, negative = down).
            x: X coordinate to position cursor before scrolling.
            y: Y coordinate to position cursor before scrolling.
            profile: Tempo profile (must be StealthProfile).

        Falls back to discrete scroll if momentum trajectory fails.
        """
        try:
            from core.humanize.scroll import momentum_scroll_trajectory

            trajectory = momentum_scroll_trajectory(
                amount,
                rng=_humanize_rng.get_rng(),
                profile=profile,
            )
            total_scrolled = 0
            for frame_delta, dwell in trajectory:
                pyautogui.scroll(frame_delta, x=x, y=y)
                total_scrolled += frame_delta
                if dwell > 0:
                    time.sleep(dwell)
        except Exception:  # noqa: BLE001 — never let momentum block scrolling
            pyautogui.scroll(amount, x=x, y=y)

    def press_key(self, key: str) -> None:
        """Press and release a single key by name.

        Args:
            key: Key name as accepted by pyautogui (e.g. ``"enter"``, ``"escape"``, ``"tab"``).

        """
        try:
            if self._use_backend_input:
                self._backend_input.press_key(key)
                return
            _ensure_pyautogui()
            pyautogui.press(key)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("press_key failed: %s", exc)

    def hotkey(self, *keys: str) -> None:
        """Press multiple keys simultaneously as a keyboard shortcut."""
        try:
            if self._use_backend_input:
                self._backend_input.hotkey(*keys)
                return
            _ensure_pyautogui()
            pyautogui.hotkey(*keys)
        except (_FailSafeException, OSError, RuntimeError, AttributeError) as exc:
            logger.warning("hotkey failed: %s", exc)

    def find_on_screen(self, template_path: str, confidence: float = 0.8) -> tuple[int, int] | None:
        """Locate a template image on screen and return its centre (x, y).

        Uses OpenCV template matching. Requires ``opencv-python`` to be installed.

        Args:
            template_path: Filesystem path to the template image.
            confidence: Minimum match confidence threshold (0.0–1.0).

        Returns:
            tuple[int, int] | None: Centre (x, y) coordinates of the match,
            or None if the template is not found or opencv is unavailable.

        """
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
        except (OSError, RuntimeError, AttributeError, ValueError) as exc:
            logger.warning("find_on_screen failed: %s", exc)
        return None

    def wait_for_image(
        self,
        template_path: str,
        timeout: float = 30,
        confidence: float = 0.8,
        interval: float = 1,
    ) -> tuple[int, int] | None:
        """Poll the screen until *template_path* appears or *timeout* expires.

        Args:
            template_path: Filesystem path to the template image.
            timeout: Maximum seconds to wait before giving up.
            confidence: Minimum match confidence threshold (0.0–1.0).
            interval: Seconds between each scan attempt.

        Returns:
            tuple[int, int] | None: Centre (x, y) of the found template,
            or None if not found within the timeout.

        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                pos = self.find_on_screen(template_path, confidence)
                if pos:
                    return pos
            except (OSError, RuntimeError, AttributeError, ValueError) as exc:
                logger.warning("wait_for_image scan failed: %s", exc)
            time.sleep(interval)
        return None

    def click_image(
        self,
        template_path: str,
        confidence: float = 0.8,
        button: str = "left",
    ) -> bool:
        """Find a template on screen and click it.

        Args:
            template_path: Filesystem path to the template image.
            confidence: Minimum match confidence threshold (0.0–1.0).
            button: Mouse button to use (``"left"``, ``"right"``, ``"middle"``).

        Returns:
            bool: True if the template was found and clicked, False otherwise.

        """
        pos = self.find_on_screen(template_path, confidence)
        if not pos:
            logger.debug("click_image: template %s not found", template_path)
            return False
        self.click(pos[0], pos[1], button=button)
        return True


# Alias for backward compatibility
DesktopEngine = DesktopController

# Module-level convenience functions
_ctrl: DesktopController | None = None


def _get_controller() -> DesktopController:
    """Return the module-level :class:`DesktopController` singleton."""
    global _ctrl
    if _ctrl is None:
        _ctrl = DesktopController()
    return _ctrl


def screenshot() -> Image.Image:
    """Take a full-screen screenshot via the default controller.

    Returns:
        PIL.Image: A full-screen RGB screenshot.

    """
    return _get_controller().screenshot()


def screenshot_base64() -> str:
    """Return a base64-encoded PNG screenshot via the default controller.

    Returns:
        str: Base64-encoded PNG image string.

    """
    return _get_controller().screenshot_base64()


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    """Click at screen coordinates using the default controller.

    Args:
        x: X coordinate in pixels.
        y: Y coordinate in pixels.
        button: Mouse button (``"left"``, ``"right"``, ``"middle"``).
        clicks: Number of times to click.

    """
    _get_controller().click(x, y, button=button, clicks=clicks)


def type_text(text: str, interval: float = 0.02) -> None:
    """Type text using the default controller.

    Args:
        text: The string to type.
        interval: Seconds between each keystroke.

    """
    _get_controller().type_text(text, interval=interval)


def press_key(key: str) -> None:
    """Press and release a key using the default controller.

    Args:
        key: Key name as accepted by pyautogui (e.g. ``"enter"``, ``"escape"``).

    """
    _get_controller().press_key(key)


def hotkey(*keys: str) -> None:
    """Press a keyboard shortcut using the default controller."""
    _get_controller().hotkey(*keys)


def scroll(amount: int, x: int | None = None, y: int | None = None) -> None:
    """Scroll the mouse wheel using the default controller.

    Args:
        amount: Number of scroll clicks. Positive scrolls up, negative down.
        x: X coordinate to scroll at, or None for current position.
        y: Y coordinate to scroll at, or None for current position.

    """
    _get_controller().scroll(amount, x=x, y=y)
