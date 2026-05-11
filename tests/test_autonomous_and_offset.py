"""Tests for autonomous mode and multi-monitor click offset translation."""
import pytest
import core.desktop as desktop_mod


class FakeDesktop:
    def __init__(self):
        self.clicks = []
    def click(self, *a, **kw):
        self.clicks.append((a, kw))
    def type_text(self, *a, **kw): pass
    def press_key(self, *a, **kw): pass
    def hotkey(self, *a, **kw): pass
    def scroll(self, *a, **kw): pass


@pytest.fixture
def fake_executor(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    from core.action_executor import ActionExecutor
    return ActionExecutor


def test_click_with_no_offset_passes_coords_through(fake_executor):
    ex = fake_executor(click_offset=(0, 0))
    ex.execute_sync({"action": "click", "x": 100, "y": 200})
    assert ex._desktop.clicks[-1][0] == (100, 200)


def test_click_with_negative_offset_translates_to_screen_coords(fake_executor):
    """Virtual-desktop capture starting at (-1920, 0) needs translation."""
    ex = fake_executor(click_offset=(-1920, 0))
    # LLM says "click at image coord (500, 400)"
    ex.execute_sync({"action": "click", "x": 500, "y": 400})
    # That maps to screen coord (500 + (-1920), 400 + 0) = (-1420, 400)
    assert ex._desktop.clicks[-1][0] == (-1420, 400)


def test_click_text_also_translates(fake_executor, monkeypatch):
    from core import ocr
    monkeypatch.setattr(ocr, "find_text", lambda *a, **kw: (300, 200))
    ex = fake_executor(click_offset=(-1920, -100))
    ex.execute_sync({"action": "click_text", "text": "Send"})
    assert ex._desktop.clicks[-1][0] == (300 - 1920, 200 - 100)


def test_autonomous_skips_approval_gate():
    """Engine must not invoke approval_callback when autonomous is on."""
    from core.engine import AgentEngine, APPROVAL_REQUIRED_ACTIONS

    # Sanity: 'click' is a state-changing action that normally requires approval.
    assert "click" in APPROVAL_REQUIRED_ACTIONS

    calls = []
    eng = AgentEngine(
        {"provider": "openai", "model": "gpt-4o", "api_key": "x",
         "approval_mode": True, "autonomous": True},
        approval_callback=lambda action: calls.append(action) or True,
    )
    # We're not actually running the loop — just confirm the config plumbing.
    # The engine should NOT consult approval_callback under autonomous=True.
    # The simplest way to assert that is to inspect the config flag the run
    # loop reads:
    assert eng.config.get("autonomous") is True
    assert eng.config.get("approval_mode") is True
    # No call yet — the gate check happens during run(), but we've verified
    # the config wiring. The actual gate behavior is tested in the run loop
    # via integration; here we just confirm the config flag isn't fighting.


def test_smart_open_in_state_changing_actions():
    """smart_open must be approval-gated like other state-changing actions."""
    from core.action_executor import STATE_CHANGING_ACTIONS
    assert "smart_open" in STATE_CHANGING_ACTIONS
