"""Sentinel Desktop v23 — BackendProtocol.

A ``runtime_checkable`` :class:`typing.Protocol` defining the full input surface
every platform backend's ``.input`` (alias of ``.stealth``) must satisfy. This
lets :class:`core.desktop.DesktopController` type-check its input dependency and
lets tests assert conformance via ``isinstance(backend.input, BackendProtocol)``.

The Protocol is structural (duck-typed) — backends satisfy it by HAVING the
methods, not by inheriting from it. ``runtime_checkable`` makes ``isinstance``
work against any object that implements the named attributes.

The 11 methods:

  - ``click(x, y, button='left', clicks=1)``
  - ``type_text(text)``
  - ``press_key(key)``
  - ``hotkey(*keys)``
  - ``scroll(amount, x=None, y=None)``
  - ``moveTo(x, y, duration=0.0)``               (Phase A v23 extension)
  - ``position() -> (x, y)``                      (Phase A v23 extension)
  - ``drag(x1, y1, x2, y2, duration, button)``    (Phase A v23 extension)
  - ``screenshot()``                              (Phase A v23 extension)
  - ``rightClick(x, y, clicks=1)``                (Phase A v23 extension)
  - ``doubleClick(x, y)``                         (Phase A v23 extension)

Plus ``is_available()`` — the liveness flag.

All concrete backends (:class:`LinuxStealthInput`, :class:`WindowsStealthInput`,
:class:`MacOSStealthInput`, :class:`NoOpStealthInput`) implement every method
above, so ``get_backend().input`` is always a ``BackendProtocol`` instance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BackendProtocol(Protocol):
    """Structural contract for the platform input surface.

    Every platform backend's ``.input`` attribute (alias of ``.stealth``)
    satisfies this Protocol. ``runtime_checkable`` lets callers assert
    ``isinstance(get_backend().input, BackendProtocol)``.

    The concrete implementations live in:
      - ``core.platform.linux_backend.LinuxStealthInput``
      - ``core.platform.windows_backend.WindowsStealthInput``
      - ``core.platform.macos_backend.MacOSStealthInput``
      - ``core.platform.base.NoOpStealthInput``
    """

    def is_available(self) -> bool:
        """Return ``True`` if the input subsystem is usable on this platform."""
        ...

    # ── Original 5 input methods (abstract on StealthInputBackend) ────────

    def click(
        self, x: int, y: int, button: str = "left", clicks: int = 1
    ) -> bool:
        """Click at ``(x, y)``. Returns ``True`` on success."""
        ...

    def type_text(self, text: str) -> bool:
        """Type *text*. Returns ``True`` on success."""
        ...

    def press_key(self, key: str) -> bool:
        """Press a named key. Returns ``True`` on success."""
        ...

    def hotkey(self, *keys: str) -> bool:
        """Send a chorded hotkey (e.g. ``'ctrl'``, ``'c'``). Returns ``True``."""
        ...

    def scroll(
        self, amount: int, x: int | None = None, y: int | None = None
    ) -> bool:
        """Scroll by *amount* clicks (positive up, negative down). Returns ``True``."""
        ...

    # ── Phase A v23 extensions — the 6 methods DesktopController needs ────

    def moveTo(self, x: int, y: int, duration: float = 0.0) -> bool:
        """Move the cursor to ``(x, y)``. Returns ``True`` on success."""
        ...

    def position(self) -> tuple[int, int]:
        """Return the current cursor ``(x, y)``. ``(0, 0)`` if unknown."""
        ...

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.5,
        button: str = "left",
    ) -> bool:
        """Drag from ``(x1, y1)`` to ``(x2, y2)``. Returns ``True`` on success."""
        ...

    def screenshot(self):
        """Capture the full screen as a ``PIL.Image``. Blank placeholder on failure."""
        ...

    def rightClick(self, x: int, y: int, clicks: int = 1) -> bool:
        """Right-click at ``(x, y)``. Returns ``True`` on success."""
        ...

    def doubleClick(self, x: int, y: int) -> bool:
        """Double-click at ``(x, y)``. Returns ``True`` on success."""
        ...
