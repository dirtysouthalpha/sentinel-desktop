"""Additional gap tests for failsafe.py — arm/disarm edge cases, timing, custom callback."""

from unittest.mock import MagicMock, patch

from core import failsafe


class TestDisarmWhenNone:
    """disarm() when no listener is active does nothing."""

    def test_disarm_none_is_noop(self):
        failsafe._active = None
        failsafe.disarm()  # Should not raise
        assert failsafe._active is None


class TestArmReplacesExisting:
    """arm() stops the previous listener before creating a new one."""

    def test_arm_replaces_active_listener(self):
        old_listener = MagicMock()
        failsafe._active = old_listener
        with patch.object(failsafe.FailsafeListener, "start", return_value=True):
            result = failsafe.arm(lambda: None)
        assert result is True
        old_listener.stop.assert_called_once()
        assert failsafe._active is not old_listener
        # Cleanup
        failsafe._active = None


class TestOnPanicCallbackException:
    """_on_panic callback exception is caught and logged."""

    def test_callback_exception_does_not_propagate(self):
        callback = MagicMock(side_effect=RuntimeError("boom"))
        fl = failsafe.FailsafeListener(on_panic=callback)
        # Simulate 3 quick presses
        import time

        fl._presses = [time.monotonic()] * 3
        with patch("core.failsafe.logger"):
            fl._on_esc(None)  # Should not raise


class TestOnEscWindowTooWide:
    """_on_esc resets when presses are spread beyond PANIC_WINDOW."""

    def test_spread_out_presses_no_panic(self):
        import time

        callback = MagicMock()
        fl = failsafe.FailsafeListener(on_panic=callback)
        now = time.monotonic()
        # Spread presses over > 1.5s
        fl._presses = [now - 2.0, now - 1.0, now]
        fl._on_esc(None)
        callback.assert_not_called()


class TestOnEscSinglePress:
    """_on_esc with single press does not trigger panic."""

    def test_single_press_no_panic(self):
        callback = MagicMock()
        fl = failsafe.FailsafeListener(on_panic=callback)
        fl._on_esc(None)
        callback.assert_not_called()
        assert len(fl._presses) == 1


class TestOnPanicCallbackStoresCustomCallable:
    """FailsafeListener stores the custom on_panic callback."""

    def test_custom_callback_stored(self):
        def _cb() -> None:
            pass

        fl = failsafe.FailsafeListener(on_panic=_cb)
        assert fl._on_panic is _cb
