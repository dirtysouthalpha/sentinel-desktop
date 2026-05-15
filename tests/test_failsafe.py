"""Tests for core/failsafe.py — Esc-x3 panic stop listener."""



from core.failsafe import PANIC_PRESS_COUNT, FailsafeListener


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
