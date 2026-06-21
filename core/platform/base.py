"""Sentinel Desktop v4.0 — Abstract base classes for platform backends.

Every platform backend must implement these interfaces. The rest of the
codebase programs against these ABCs and never touches OS-specific APIs
directly.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ── Data types shared across all platforms ──────────────────────────────


class UIElement:
    """A single accessible UI element, normalized across platforms.

    Attributes:
        name: Accessible name / label.
        control_type: Normalized type (``'button'``, ``'edit'``, ``'menu'``,
            ``'tab'``, ``'treeitem'``, etc.).
        bounding_box: ``(x, y, width, height)`` in screen coordinates, or
            ``None`` if unknown.
        enabled: Whether the element is interactive.
        value: Current text/value for edit fields, toggles, etc.
        automation_id: Platform-specific unique identifier (UIA AutomationId
            on Windows, accessible-name on Linux, identifier on macOS).
        actions: List of available actions (``'invoke'``, ``'toggle'``,
            ``'set_value'``, ``'expand'``, etc.).
        children: Nested child elements (populated on deep scans).
        raw: Platform-specific original data dict for advanced use.
    """

    __slots__ = (
        "name",
        "control_type",
        "bounding_box",
        "enabled",
        "value",
        "automation_id",
        "actions",
        "children",
        "raw",
    )

    def __init__(
        self,
        name: str = "",
        control_type: str = "unknown",
        bounding_box: tuple[int, int, int, int] | None = None,
        enabled: bool = True,
        value: str | None = None,
        automation_id: str | None = None,
        actions: list[str] | None = None,
        children: list[UIElement] | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.control_type = control_type
        self.bounding_box = bounding_box
        self.enabled = enabled
        self.value = value
        self.automation_id = automation_id
        self.actions = actions or []
        self.children = children or []
        self.raw = raw or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON/logging."""
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.control_type,
            "enabled": self.enabled,
        }
        if self.bounding_box:
            d["bounds"] = {
                "x": self.bounding_box[0],
                "y": self.bounding_box[1],
                "width": self.bounding_box[2],
                "height": self.bounding_box[3],
            }
        if self.value is not None:
            d["value"] = self.value
        if self.automation_id:
            d["automation_id"] = self.automation_id
        if self.actions:
            d["actions"] = self.actions
        return d


class WindowInfo:
    """Normalized window information across platforms."""

    __slots__ = ("title", "x", "y", "width", "height", "is_focused", "handle")

    def __init__(
        self,
        title: str = "",
        x: int = 0,
        y: int = 0,
        width: int = 0,
        height: int = 0,
        is_focused: bool = False,
        handle: Any = None,
    ) -> None:
        self.title = title
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.is_focused = is_focused
        self.handle = handle

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "title": self.title,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "is_focused": self.is_focused,
        }
        if self.handle is not None:
            d["handle"] = self.handle
        return d


# ── Abstract backends ───────────────────────────────────────────────────


class AccessibilityBackend(ABC):
    """Read and interact with the OS accessibility tree."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if the accessibility subsystem is usable."""
        ...

    @abstractmethod
    def get_tree(self, window_title: str | None = None) -> list[UIElement]:
        """Return the accessible element tree for the focused or named window.

        Args:
            window_title: Optional window title filter. ``None`` means the
                currently focused window.

        Returns:
            Flat list of :class:`UIElement` instances. May be empty if the
            accessibility system is unavailable or the window has no tree.
        """
        ...

    @abstractmethod
    def find_element(
        self,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        window_title: str | None = None,
    ) -> UIElement | None:
        """Find a single element by name, automation ID, or control type."""
        ...

    @abstractmethod
    def invoke_element(self, element: UIElement) -> bool:
        """Activate an element (click a button, select an item, etc.)."""
        ...

    @abstractmethod
    def set_element_value(self, element: UIElement, value: str) -> bool:
        """Set the text/value of an editable element."""
        ...


class StealthInputBackend(ABC):
    """Send input without moving the real cursor or keyboard focus."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if stealth input is usable on this platform."""
        ...

    @abstractmethod
    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
    ) -> bool:
        """Click at ``(x, y)`` without moving the visible cursor.

        Returns ``True`` if the click was delivered, ``False`` if stealth
        mode failed (caller should fall back to physical input).
        """
        ...

    @abstractmethod
    def type_text(self, text: str) -> bool:
        """Type *text* without moving the visible cursor.

        Returns ``True`` on success, ``False`` on failure.
        """
        ...

    @abstractmethod
    def press_key(self, key: str) -> bool:
        """Press a named key without moving the visible cursor."""
        ...

    @abstractmethod
    def hotkey(self, *keys: str) -> bool:
        """Send a chorded hotkey (e.g. ``'ctrl'``, ``'c'``)."""
        ...

    @abstractmethod
    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> bool:
        """Scroll the mouse wheel by *amount* clicks.

        Positive scrolls up, negative scrolls down.
        """
        ...

    # ── Extended input surface (v23 cross-platform) ──────────────────────
    # These are NOT @abstractmethod — they have default NotImplementedError /
    # no-op implementations so existing backends (Windows, macOS) that don't
    # yet override them keep working. Backends that support them (Linux) override.
    # This avoids forcing a Windows/Mac regression when extending the contract.

    def moveTo(self, x: int, y: int, duration: float = 0.0) -> bool:
        """Move the cursor to ``(x, y)``. If *duration* > 0, animate the move.

        Returns ``True`` if the move succeeded. Default: not supported.
        """
        raise NotImplementedError

    def position(self) -> tuple[int, int]:
        """Return the current cursor position ``(x, y)``.

        Returns ``(0, 0)`` if the position cannot be determined. Default: ``(0, 0)``.
        """
        return (0, 0)

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.5,
        button: str = "left",
    ) -> bool:
        """Drag from ``(x1, y1)`` to ``(x2, y2)`` holding *button*.

        Returns ``True`` if the drag completed. Default: not supported.
        """
        raise NotImplementedError

    def screenshot(self):
        """Capture the full screen as a PIL.Image.

        Returns a blank placeholder image if capture is unavailable — never raises.
        Default: 1×1 blank image.
        """
        from PIL import Image

        return Image.new("RGB", (1, 1))

    def rightClick(self, x: int, y: int, clicks: int = 1) -> bool:
        """Right-click at ``(x, y)``. Returns ``True`` on success. Default: False."""
        return False

    def doubleClick(self, x: int, y: int) -> bool:
        """Double-click at ``(x, y)``. Returns ``True`` on success. Default: False."""
        return False


class CredentialBackend(ABC):
    """Secure credential storage."""

    @abstractmethod
    def store(self, key: str, value: str) -> bool:
        """Store a credential. Return ``True`` on success."""
        ...

    @abstractmethod
    def retrieve(self, key: str) -> str | None:
        """Retrieve a credential. Return ``None`` if not found."""
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a credential. Return ``True`` if it existed."""
        ...

    @abstractmethod
    def list_keys(self) -> list[str]:
        """List all stored credential names."""
        ...


class ShellBackend(ABC):
    """Execute shell commands and scripts on the current platform."""

    @abstractmethod
    def execute(
        self,
        command: str,
        timeout: float = 60.0,
        capture: bool = True,
    ) -> dict[str, Any]:
        """Execute *command* in the default system shell.

        Args:
            command: Shell command string.
            timeout: Max seconds to wait.
            capture: If ``True``, capture stdout/stderr.

        Returns:
            Dict with ``'exit_code'``, ``'stdout'``, ``'stderr'``.
        """
        ...

    @abstractmethod
    def get_platform_shell(self) -> str:
        """Return the default shell executable (e.g. ``'powershell'``,
        ``'bash'``, ``'zsh'``)."""
        ...

    @abstractmethod
    def sanitize_command(self, command: str) -> str:
        """Sanitize a command to prevent injection. Returns the cleaned
        command string or raises ``ValueError`` for dangerous input."""
        ...


class WindowBackend(ABC):
    """List, focus, resize, and close windows."""

    @abstractmethod
    def list_windows(self) -> list[WindowInfo]:
        """Return all visible windows."""
        ...

    @abstractmethod
    def focus_window(self, title: str) -> bool:
        """Bring a window to the foreground by partial title match."""
        ...

    @abstractmethod
    def close_window(self, title: str) -> bool:
        """Close a window by partial title match."""
        ...

    @abstractmethod
    def get_focused_window_rect(self) -> tuple[int, int, int, int] | None:
        """Return ``(x, y, width, height)`` of the foreground window."""
        ...

    @abstractmethod
    def get_window_rect(self, title: str) -> tuple[int, int, int, int] | None:
        """Return ``(x, y, width, height)`` for a window by title."""
        ...


class OverlayBackend(ABC):
    """Transparent overlay for visual feedback during automation."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if overlays are supported on this platform."""
        ...

    @abstractmethod
    def show_ring(
        self,
        x: int,
        y: int,
        color: str = "#00F0FF",
        duration_ms: int = 420,
    ) -> None:
        """Show a ring highlight at ``(x, y)`` for *duration_ms*."""
        ...

    @abstractmethod
    def show_cursor_move(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        duration_ms: int = 300,
    ) -> None:
        """Animate a cursor movement from one point to another."""
        ...


# ── No-op fallback ──────────────────────────────────────────────────────


class NoOpAccessibility(AccessibilityBackend):
    """No-op accessibility backend for unsupported platforms."""

    def is_available(self) -> bool:
        return False

    def get_tree(self, window_title: str | None = None) -> list[UIElement]:
        return []

    def find_element(
        self,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        window_title: str | None = None,
    ) -> UIElement | None:
        return None

    def invoke_element(self, element: UIElement) -> bool:
        return False

    def set_element_value(self, element: UIElement, value: str) -> bool:
        return False


class NoOpStealthInput(StealthInputBackend):
    """No-op stealth input for unsupported platforms."""

    def is_available(self) -> bool:
        return False

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> bool:
        return False

    def type_text(self, text: str) -> bool:
        return False

    def press_key(self, key: str) -> bool:
        return False

    def hotkey(self, *keys: str) -> bool:
        return False

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> bool:
        return False

    def moveTo(self, x: int, y: int, duration: float = 0.0) -> bool:
        return False

    def position(self) -> tuple[int, int]:
        return (0, 0)

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.5,
        button: str = "left",
    ) -> bool:
        return False

    def screenshot(self):
        from PIL import Image

        return Image.new("RGB", (1, 1))

    def rightClick(self, x: int, y: int, clicks: int = 1) -> bool:
        return False

    def doubleClick(self, x: int, y: int) -> bool:
        return False


class NoOpCredential(CredentialBackend):
    """No-op credential backend — stores nothing, returns nothing."""

    def store(self, key: str, value: str) -> bool:
        logger.warning("Credential storage unavailable on this platform")
        return False

    def retrieve(self, key: str) -> str | None:
        return None

    def delete(self, key: str) -> bool:
        return False

    def list_keys(self) -> list[str]:
        return []


class NoOpShell(ShellBackend):
    """No-op shell backend for unsupported platforms."""

    def execute(
        self,
        command: str,
        timeout: float = 60.0,
        capture: bool = True,
    ) -> dict[str, Any]:
        return {"exit_code": -1, "stdout": "", "stderr": "No shell available"}

    def get_platform_shell(self) -> str:
        return "sh"

    def sanitize_command(self, command: str) -> str:
        return command


class NoOpWindow(WindowBackend):
    """No-op window backend for unsupported platforms."""

    def list_windows(self) -> list[WindowInfo]:
        return []

    def focus_window(self, title: str) -> bool:
        return False

    def close_window(self, title: str) -> bool:
        return False

    def get_focused_window_rect(self) -> tuple[int, int, int, int] | None:
        return None

    def get_window_rect(self, title: str) -> tuple[int, int, int, int] | None:
        return None


class NoOpOverlay(OverlayBackend):
    """No-op overlay backend for unsupported platforms."""

    def is_available(self) -> bool:
        return False

    def show_ring(
        self,
        x: int,
        y: int,
        color: str = "#00F0FF",
        duration_ms: int = 420,
    ) -> None:
        pass

    def show_cursor_move(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        duration_ms: int = 300,
    ) -> None:
        pass


class NoOpBackend:
    """Aggregated no-op backend for completely unsupported platforms.

    Returns no-op implementations for every subsystem so the application
    never crashes, just gracefully degrades.
    """

    def __init__(self) -> None:
        self.accessibility = NoOpAccessibility()
        self.stealth = NoOpStealthInput()
        self.credentials = NoOpCredential()
        self.shell = NoOpShell()
        self.window = NoOpWindow()
        self.overlay = NoOpOverlay()

    @property
    def input(self) -> NoOpStealthInput:
        """Alias for ``.stealth`` — the physical/stealth input surface.

        Callers (core.stealth_input, core.desktop) use ``backend.input.*`` so
        the code reads naturally; the underlying object is the same stealth
        input subsystem.
        """
        return self.stealth

    @property
    def default_shell(self) -> str:
        return "sh"
