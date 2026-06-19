"""Integration tests: humanization wired into core/stealth_input.py chokepoint.

Stealth input (PostMessage) has NO cursor, so there's no motion to humanize.
What we DO humanize is the *timing*:
- post_click: the down→up hold (replaces the fixed delay=0.02)
- post_text: the per-character cadence (replaces the fixed delay=0.005)

When SENTINEL_HUMANIZE is OFF, behavior is byte-identical to today (fixed
delays) — the parity guarantee that protects the existing baseline.

Note: stealth_input is Windows-only (win32). These tests exercise the timing
path via the module's internal sleep calls, with win32 stubbed where needed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core import stealth_input


class TestPostClickTiming:
    def test_post_click_uses_humanized_hold_when_enabled(self, monkeypatch):
        """When humanized, the down→up delay comes from humanize.timing,
        not the fixed default."""
        monkeypatch.setenv("SENTINEL_HUMANIZE", "1")
        sleeps: list[float] = []

        # stealth_input only acts when _HAS_WIN32; force it True and stub the
        # win32 calls so we observe timing without a real window.
        monkeypatch.setattr(stealth_input, "_HAS_WIN32", True)

        class _FakeWin:
            MK_LBUTTON = 1
            WM_LBUTTONDOWN = 0x201
            WM_LBUTTONUP = 0x202

        monkeypatch.setattr(stealth_input, "win32con", _FakeWin, raising=False)

        fake_win32gui = type("fake_gui", (), {})
        fake_win32gui.WindowFromPoint = lambda *a, **kw: 1
        fake_win32gui.ScreenToClient = lambda *a, **kw: (0, 0)
        monkeypatch.setattr(stealth_input, "win32gui", fake_win32gui, raising=False)

        fake_win32api = type("fake_api", (), {})
        fake_win32api.PostMessage = lambda *a, **kw: None
        monkeypatch.setattr(stealth_input, "win32api", fake_win32api, raising=False)

        with patch("core.stealth_input.time.sleep", lambda s: sleeps.append(s)):
            stealth_input.post_click(100, 100)

        # At least one sleep fired (the humanized hold), and the values came
        # from humanize.timing (within the profile's click_hold range), NOT
        # all equal to the fixed 0.02 default.
        assert sleeps, "no sleep observed — timing not humanized"
        assert not all(abs(s - 0.02) < 1e-9 for s in sleeps), (
            "delays all equal the fixed 0.02 default — not humanized"
        )

    def test_post_click_uses_fixed_delay_when_disabled(self, monkeypatch):
        """OFF path: the down→up delay is the original fixed default (0.02)."""
        monkeypatch.setenv("SENTINEL_HUMANIZE", "0")
        sleeps: list[float] = []
        monkeypatch.setattr(stealth_input, "_HAS_WIN32", True)

        class _FakeWin:
            MK_LBUTTON = 1
            WM_LBUTTONDOWN = 0x201
            WM_LBUTTONUP = 0x202

        monkeypatch.setattr(stealth_input, "win32con", _FakeWin, raising=False)
        fake_win32gui = type("fake_gui", (), {})
        fake_win32gui.WindowFromPoint = lambda *a, **kw: 1
        fake_win32gui.ScreenToClient = lambda *a, **kw: (0, 0)
        monkeypatch.setattr(stealth_input, "win32gui", fake_win32gui, raising=False)
        fake_win32api = type("fake_api", (), {})
        fake_win32api.PostMessage = lambda *a, **kw: None
        monkeypatch.setattr(stealth_input, "win32api", fake_win32api, raising=False)

        with patch("core.stealth_input.time.sleep", lambda s: sleeps.append(s)):
            stealth_input.post_click(100, 100, delay=0.02)

        # Original behavior: 2 sleeps per click (down, up), each 0.02.
        assert sleeps
        assert all(abs(s - 0.02) < 1e-9 for s in sleeps), (
            f"OFF-path delays diverged from fixed 0.02: {sleeps}"
        )


class TestPostTextTiming:
    def test_post_text_uses_humanized_cadence_when_enabled(self, monkeypatch):
        """When humanized, per-char delays come from humanize.typing, not 0.005."""
        monkeypatch.setenv("SENTINEL_HUMANIZE", "1")
        sleeps: list[float] = []
        monkeypatch.setattr(stealth_input, "_HAS_WIN32", True)

        fake_win32gui = type("fake_gui", (), {})
        fake_win32gui.GetForegroundWindow = lambda *a, **kw: 1
        monkeypatch.setattr(stealth_input, "win32gui", fake_win32gui, raising=False)

        class _FakeCon:
            WM_CHAR = 0x102

        monkeypatch.setattr(stealth_input, "win32con", _FakeCon, raising=False)
        fake_win32api = type("fake_api", (), {})
        fake_win32api.PostMessage = lambda *a, **kw: None
        monkeypatch.setattr(stealth_input, "win32api", fake_win32api, raising=False)

        # _get_focus_hwnd may try win32 internals; stub it.
        monkeypatch.setattr(stealth_input, "_get_focus_hwnd", lambda hwnd: hwnd, raising=False)

        with patch("core.stealth_input.time.sleep", lambda s: sleeps.append(s)):
            stealth_input.post_text("hello")

        # 5 chars → up to 5 per-char sleeps. They must NOT all equal the
        # fixed 0.005 default — that's the whole point.
        assert len(sleeps) >= 1
        assert not all(abs(s - 0.005) < 1e-9 for s in sleeps), (
            "per-char delays all equal fixed 0.005 — not humanized"
        )

    def test_post_text_uses_fixed_delay_when_disabled(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_HUMANIZE", "0")
        sleeps: list[float] = []
        monkeypatch.setattr(stealth_input, "_HAS_WIN32", True)

        fake_win32gui = type("fake_gui", (), {})
        fake_win32gui.GetForegroundWindow = lambda *a, **kw: 1
        monkeypatch.setattr(stealth_input, "win32gui", fake_win32gui, raising=False)
        monkeypatch.setattr(stealth_input, "_get_focus_hwnd", lambda hwnd: hwnd, raising=False)
        fake_win32api = type("fake_api", (), {})
        fake_win32api.PostMessage = lambda *a, **kw: None
        monkeypatch.setattr(stealth_input, "win32api", fake_win32api, raising=False)
        class _FakeCon:
            WM_CHAR = 0x102
        monkeypatch.setattr(stealth_input, "win32con", _FakeCon, raising=False)

        with patch("core.stealth_input.time.sleep", lambda s: sleeps.append(s)):
            stealth_input.post_text("ab", delay=0.005)

        assert sleeps
        assert all(abs(s - 0.005) < 1e-9 for s in sleeps), (
            f"OFF-path per-char delays diverged from fixed 0.005: {sleeps}"
        )
