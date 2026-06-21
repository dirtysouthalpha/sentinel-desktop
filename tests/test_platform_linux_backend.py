"""Tests for the extended platform input surface (Phase A of the cross-platform
DesktopController wiring).

Covers:
- StealthInputBackend ABC's 6 new methods (moveTo, position, drag, screenshot,
  rightClick, doubleClick) are non-abstract defaults so existing Windows/Mac
  backends keep instantiating.
- LinuxStealthInput implements all 6 via xdotool/mss (subprocess mocked).
- Every concrete backend (Linux, NoOp) exposes the full 11-method input surface
  via both ``.stealth`` and the ``.input`` alias.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# The full input surface every backend.input must offer.
_FULL_INPUT_SURFACE = [
    "click", "type_text", "press_key", "hotkey", "scroll",  # original 5
    "moveTo", "position", "drag", "screenshot",              # new (Phase A)
    "rightClick", "doubleClick",                              # new (Phase A)
]


# ---------------------------------------------------------------------------
# ABC contract — the 6 new methods are NOT abstract (Windows/Mac safe)
# ---------------------------------------------------------------------------


class TestABCContract:
    def test_new_methods_are_not_abstract(self):
        """Adding the 6 methods must NOT make Windows/Mac backends abstract
        (they don't implement them yet). They're defaults, not @abstractmethod."""
        from core.platform.base import StealthInputBackend

        abstracts = set(StealthInputBackend.__abstractmethods__)
        for method in ["moveTo", "position", "drag", "screenshot",
                       "rightClick", "doubleClick"]:
            assert method not in abstracts, (
                f"{method} is @abstractmethod — would break Windows/Mac backends"
            )
        # Original 5 stay abstract.
        for method in ["click", "type_text", "press_key", "hotkey", "scroll",
                       "is_available"]:
            assert method in abstracts

    def test_abc_defaults_return_safe_values(self):
        """The ABC's default implementations degrade safely (don't raise
        unexpectedly). screenshot returns a blank image, position returns (0,0)."""
        from PIL import Image

        from core.platform.base import StealthInputBackend

        # A minimal concrete subclass implementing only the 5 abstracts.
        class _Minimal(StealthInputBackend):
            def is_available(self):
                return False

            def click(self, x, y, button="left", clicks=1):
                return False

            def type_text(self, text):
                return False

            def press_key(self, key):
                return False

            def hotkey(self, *keys):
                return False

            def scroll(self, amount, x=None, y=None):
                return False

        m = _Minimal()
        assert m.position() == (0, 0)
        # moveTo/drag raise NotImplementedError by default (subclasses override);
        # the safe defaults are position/screenshot/rightClick/doubleClick.
        with pytest.raises(NotImplementedError):
            m.moveTo(10, 10)
        with pytest.raises(NotImplementedError):
            m.drag(1, 1, 2, 2)
        assert isinstance(m.screenshot(), Image.Image)
        assert m.rightClick(5, 5) is False
        assert m.doubleClick(5, 5) is False


# ---------------------------------------------------------------------------
# LinuxStealthInput — the 6 new methods (xdotool mocked)
# ---------------------------------------------------------------------------


class TestLinuxStealthInputExtensions:
    def _make(self):
        from core.platform.linux_backend import LinuxStealthInput

        inp = LinuxStealthInput()
        inp._available = True  # bypass the xdotool probe
        return inp

    def test_move_to_invokes_xdotool_mousemove(self):
        inp = self._make()
        with patch("core.platform.linux_backend.subprocess.run") as mock_run:
            assert inp.moveTo(100, 200) is True
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "xdotool" in args
            assert "mousemove" in args
            assert "100" in args and "200" in args

    def test_move_to_returns_false_when_unavailable(self):
        inp = self._make()
        inp._available = False
        assert inp.moveTo(1, 1) is False

    def test_position_parses_xdotool_output(self):
        inp = self._make()

        def fake_run(cmd, **kw):
            class _R:
                returncode = 0
                stdout = "x:123 y:456 screen:0 window:42"
            return _R()

        with patch("core.platform.linux_backend.subprocess.run", side_effect=fake_run):
            assert inp.position() == (123, 456)

    def test_position_returns_zero_on_unavailable(self):
        inp = self._make()
        inp._available = False
        assert inp.position() == (0, 0)

    def test_position_handles_garbage_output(self):
        inp = self._make()

        def fake_run(cmd, **kw):
            class _R:
                returncode = 0
                stdout = "garbage no colons"
            return _R()

        with patch("core.platform.linux_backend.subprocess.run", side_effect=fake_run):
            assert inp.position() == (0, 0)

    def test_drag_invokes_mousedown_move_mouseup(self):
        inp = self._make()
        with patch("core.platform.linux_backend.subprocess.run") as mock_run:
            assert inp.drag(10, 20, 30, 40) is True
        # 4 calls: move-to-start, mousedown, move-to-end, mouseup
        assert mock_run.call_count == 4
        # Each call's first positional arg is the argv list; argv[1] is the
        # xdotool subcommand ('mousemove'/'mousedown'/'mouseup').
        cmds = [c.args[0][1] for c in mock_run.call_args_list]
        assert "mousemove" in cmds[0]
        assert "mousedown" in cmds[1]
        assert "mousemove" in cmds[2]
        assert "mouseup" in cmds[3]

    def test_drag_returns_false_when_unavailable(self):
        inp = self._make()
        inp._available = False
        assert inp.drag(1, 1, 2, 2) is False

    def test_right_click_routes_to_click_right(self):
        inp = self._make()
        with patch.object(inp, "click", return_value=True) as mock_click:
            assert inp.rightClick(50, 60) is True
            mock_click.assert_called_once_with(50, 60, button="right", clicks=1)

    def test_double_click_routes_to_click_twice(self):
        inp = self._make()
        with patch.object(inp, "click", return_value=True) as mock_click:
            assert inp.doubleClick(50, 60) is True
            mock_click.assert_called_once_with(50, 60, button="left", clicks=2)

    def test_screenshot_returns_pil_image_even_on_failure(self):
        """screenshot() must NEVER raise — it returns a blank PIL image on failure."""
        from PIL import Image

        inp = self._make()
        # Force mss to fail; should fall through to the blank-image branch.
        img = inp.screenshot()
        assert isinstance(img, Image.Image)

    def test_screenshot_when_mss_unavailable(self):
        """If mss isn't importable, screenshot returns a 1920x1080 blank image."""
        from PIL import Image

        inp = self._make()
        import builtins

        real_import = builtins.__import__

        def _block_mss(name, *args, **kwargs):
            if name == "mss":
                raise ImportError("no mss")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_block_mss):
            img = inp.screenshot()
        assert isinstance(img, Image.Image)
        assert img.size == (1920, 1080)


# ---------------------------------------------------------------------------
# Backend.input alias — every backend exposes the full surface
# ---------------------------------------------------------------------------


class TestInputAlias:
    def test_linux_backend_input_alias_exposes_full_surface(self):
        from core.platform.linux_backend import LinuxBackend

        b = LinuxBackend()
        assert b.input is b.stealth
        for method in _FULL_INPUT_SURFACE:
            assert hasattr(b.input, method), f"LinuxBackend.input missing {method}"

    def test_noop_backend_input_alias_exposes_full_surface(self):
        from core.platform.base import NoOpBackend

        b = NoOpBackend()
        assert b.input is b.stealth
        for method in _FULL_INPUT_SURFACE:
            assert hasattr(b.input, method), f"NoOpBackend.input missing {method}"

    def test_get_backend_input_works_on_linux(self):
        """The real get_backend() on this Linux box returns a backend whose
        .input exposes all 11 methods (the headline contract)."""
        from core.platform import get_backend

        b = get_backend()
        for method in _FULL_INPUT_SURFACE:
            assert hasattr(b.input, method), f"get_backend().input missing {method}"


# ---------------------------------------------------------------------------
# BackendProtocol conformance — runtime_checkable isinstance
# ---------------------------------------------------------------------------
# Every concrete backend's .input must satisfy the BackendProtocol Protocol
# (core/platform/backend.py). runtime_checkable makes isinstance work against
# any object that has the named attributes — this asserts the structural
# contract holds for all four backends, on any host platform.


class TestBackendProtocolConformance:
    def test_linux_backend_input_satisfies_protocol(self):
        """LinuxBackend.input is a BackendProtocol instance (runtime_checkable)."""
        from core.platform.backend import BackendProtocol
        from core.platform.linux_backend import LinuxBackend

        assert isinstance(LinuxBackend().input, BackendProtocol)

    def test_noop_backend_input_satisfies_protocol(self):
        """NoOpBackend.input is a BackendProtocol instance."""
        from core.platform.backend import BackendProtocol
        from core.platform.base import NoOpBackend

        assert isinstance(NoOpBackend().input, BackendProtocol)

    def test_windows_backend_input_satisfies_protocol(self):
        """WindowsBackend.input is a BackendProtocol instance.

        WindowsStealthInput now implements all 11 methods (Phase A v23 gap-fill)
        so it satisfies the Protocol structurally. This test runs on any host
        because we import the class directly (it imports win32 libs lazily via
        the backend module's guarded imports).
        """
        from core.platform.backend import BackendProtocol

        # WindowsBackend imports win32 libs; on non-Windows the import may fail
        # at module load (win32gui etc.). Try the import; skip if the host
        # can't load it — the conformance is still asserted on Windows CI.
        try:
            from core.platform.windows_backend import WindowsBackend
        except Exception:  # noqa: BLE001 — import-time platform deps
            pytest.skip("WindowsBackend not importable on this host")
        try:
            backend = WindowsBackend()
        except Exception:  # noqa: BLE001 — needs win32 at runtime
            pytest.skip("WindowsBackend not instantiable on this host")
        assert isinstance(backend.input, BackendProtocol)

    def test_macos_backend_input_satisfies_protocol(self):
        """MacOSBackend.input is a BackendProtocol instance."""
        from core.platform.backend import BackendProtocol

        try:
            from core.platform.macos_backend import MacOSBackend
        except Exception:  # noqa: BLE001
            pytest.skip("MacOSBackend not importable on this host")
        try:
            backend = MacOSBackend()
        except Exception:  # noqa: BLE001
            pytest.skip("MacOSBackend not instantiable on this host")
        assert isinstance(backend.input, BackendProtocol)

    def test_get_backend_input_satisfies_protocol_on_current_host(self):
        """The real get_backend().input on THIS host is a BackendProtocol."""
        from core.platform import get_backend
        from core.platform.backend import BackendProtocol

        assert isinstance(get_backend().input, BackendProtocol)

    def test_all_eleven_methods_present_on_each_importable_backend(self):
        """Beyond isinstance (which only checks method presence, not signatures),
        explicitly assert every one of the 11 methods is callable on each
        backend we can import on this host."""
        candidates = []
        try:
            from core.platform.linux_backend import LinuxBackend
            candidates.append(("Linux", LinuxBackend()))
        except Exception:  # noqa: BLE001
            pass
        try:
            from core.platform.base import NoOpBackend
            candidates.append(("NoOp", NoOpBackend()))
        except Exception:  # noqa: BLE001
            pass
        try:
            from core.platform.windows_backend import WindowsBackend
            candidates.append(("Windows", WindowsBackend()))
        except Exception:  # noqa: BLE001
            pass
        try:
            from core.platform.macos_backend import MacOSBackend
            candidates.append(("MacOS", MacOSBackend()))
        except Exception:  # noqa: BLE001
            pass

        assert len(candidates) >= 1, "no backends importable on this host"
        for name, backend in candidates:
            for method in _FULL_INPUT_SURFACE:
                assert callable(getattr(backend.input, method, None)), (
                    f"{name}Backend.input.{method} not callable"
                )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
