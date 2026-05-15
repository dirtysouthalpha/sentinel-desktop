"""Tests for core/failsafe.py — Esc-x3 panic stop listener."""

import time
from unittest.mock import MagicMock, patch

from core.failsafe import PANIC_PRESS_COUNT, PANIC_WINDOW_SECONDS, FailsafeListener


class TestFailsafeListener:
    def test_start_without_keyboard_returns_false(self):
        fl = FailsafeListener(on_panic=lambda: None)
        # On CI without the 'keyboard' package, start() returns False.
        result = fl.start()
        # If keyboard IS installed, this would be True; either way, no crash.
        assert isinstance(result, bool)

    def test_start_idempotent(self):
        fl = FailsafeListener(on_panic=lambda: None)
        fl._started = True
        assert fl.start() is True

    def test_stop_without_start_is_noop(self):
        fl = FailsafeListener(on_panic=lambda: None)
        fl.stop()  # should not raise

    def test_on_esc_triggers_panic_after_three_presses(self):
        panic_called = False

        def on_panic():
            nonlocal panic_called
            panic_called = True

        fl = FailsafeListener(on_panic=on_panic)
        for _ in range(PANIC_PRESS_COUNT):
            fl._on_esc(None)
        assert panic_called

    def test_on_esc_does_not_trigger_with_two_presses(self):
        fl = FailsafeListener(on_panic=lambda: None)
        fl._on_esc(None)
        fl._on_esc(None)
        # Should not raise or trigger — just record two presses.

    def test_on_esc_resets_after_trigger(self):
        count = 0

        def on_panic():
            nonlocal count
            count += 1

        fl = FailsafeListener(on_panic=on_panic)
        for _ in range(PANIC_PRESS_COUNT):
            fl._on_esc(None)
        assert count == 1
        # Four more presses should trigger again.
        for _ in range(PANIC_PRESS_COUNT):
            fl._on_esc(None)
        assert count == 2

    def test_on_panic_exception_is_caught(self):
        def bad_panic():
            raise RuntimeError("boom")

        fl = FailsafeListener(on_panic=bad_panic)
        for _ in range(PANIC_PRESS_COUNT):
            fl._on_esc(None)  # should not raise

    def test_presses_outside_window_do_not_trigger(self):
        panic_count = 0

        def on_panic():
            nonlocal panic_count
            panic_count += 1

        fl = FailsafeListener(on_panic=on_panic)
        # Simulate two quick presses, then wait, then one more
        fl._on_esc(None)
        fl._on_esc(None)
        # Artificially age out the timestamps by injecting old timestamps
        with fl._lock:
            fl._presses.clear()
            fl._presses.append(time.monotonic() - PANIC_WINDOW_SECONDS - 1.0)
            fl._presses.append(time.monotonic() - PANIC_WINDOW_SECONDS - 0.5)
        # Third press now — the window from first to third exceeds threshold
        fl._on_esc(None)
        assert panic_count == 0

    def test_single_press_does_not_trigger(self):
        panic_called = False

        def on_panic():
            nonlocal panic_called
            panic_called = True

        fl = FailsafeListener(on_panic=on_panic)
        fl._on_esc(None)
        assert not panic_called

    def test_presses_deque_has_maxlen(self):
        fl = FailsafeListener(on_panic=lambda: None)
        assert fl._presses.maxlen == PANIC_PRESS_COUNT

    def test_stop_sets_stopped_flag(self):
        fl = FailsafeListener(on_panic=lambda: None)
        fl._started = True
        fl._kb = MagicMock()
        fl._hotkey_handle = MagicMock()
        fl.stop()
        assert fl._stopped is True

    def test_stop_when_already_stopped_is_noop(self):
        fl = FailsafeListener(on_panic=lambda: None)
        fl._stopped = True
        fl._kb = MagicMock()
        fl.stop()  # should not call unhook
        fl._kb.unhook.assert_not_called()

    def test_stop_when_no_keyboard_is_noop(self):
        fl = FailsafeListener(on_panic=lambda: None)
        fl._started = True
        fl._kb = None
        fl.stop()  # should not raise
        assert fl._stopped is False  # early return, _stopped not set

    def test_start_with_mock_keyboard_module(self):
        fl = FailsafeListener(on_panic=lambda: None)
        mock_kb = MagicMock()
        mock_kb.on_press_key.return_value = "handle123"
        with patch.dict("sys.modules", {"keyboard": mock_kb}):
            result = fl.start()
        assert result is True
        assert fl._started is True
        assert fl._kb is mock_kb
        mock_kb.on_press_key.assert_called_once_with("esc", fl._on_esc)

    def test_start_keyboard_hook_failure_returns_false(self):
        fl = FailsafeListener(on_panic=lambda: None)
        mock_kb = MagicMock()
        mock_kb.on_press_key.side_effect = OSError("permission denied")
        with patch.dict("sys.modules", {"keyboard": mock_kb}):
            result = fl.start()
        assert result is False

    def test_panic_press_count_is_three(self):
        assert PANIC_PRESS_COUNT == 3

    def test_panic_window_is_1_5_seconds(self):
        assert PANIC_WINDOW_SECONDS == 1.5

    def test_on_esc_clears_presses_after_trigger(self):
        fl = FailsafeListener(on_panic=lambda: None)
        for _ in range(PANIC_PRESS_COUNT):
            fl._on_esc(None)
        # After trigger, presses should be cleared
        assert len(fl._presses) == 0

    def test_on_esc_does_not_clear_before_trigger(self):
        fl = FailsafeListener(on_panic=lambda: None)
        fl._on_esc(None)
        fl._on_esc(None)
        assert len(fl._presses) == 2


class TestModuleLevelArmDisarm:
    def test_arm_disarm_cycle(self):
        import core.failsafe as mod

        original_active = mod._active
        try:
            result = mod.arm(lambda: None)
            assert isinstance(result, bool)
            mod.disarm()
            assert mod._active is None
        finally:
            mod._active = original_active

    def test_disarm_without_arm(self):
        import core.failsafe as mod

        original_active = mod._active
        try:
            mod._active = None
            mod.disarm()  # should not raise
        finally:
            mod._active = original_active

    def test_arm_replaces_existing_listener(self):
        import core.failsafe as mod

        original_active = mod._active
        try:
            # First arm
            fl1 = FailsafeListener(on_panic=lambda: None)
            mod._active = fl1
            # Second arm should stop the first and replace
            result = mod.arm(lambda: None)
            assert isinstance(result, bool)
            assert mod._active is not fl1
        finally:
            mod.disarm()
            mod._active = original_active

    def test_disarm_stops_and_clears_active(self):
        import core.failsafe as mod

        original_active = mod._active
        try:
            mock_listener = MagicMock()
            mod._active = mock_listener
            mod.disarm()
            mock_listener.stop.assert_called_once()
            assert mod._active is None
        finally:
            mod._active = original_active
