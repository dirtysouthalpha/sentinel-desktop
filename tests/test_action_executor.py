"""Tests for ActionExecutor — sensitive filter, dry-run, unknown actions."""
# Avoid importing pyautogui-touching modules by patching DesktopEngine at
# import time. The test executes only the routing logic that doesn't call
# into pyautogui.

import asyncio

import pytest

import core.desktop as desktop_mod


class FakeDesktop:
    def __init__(self):
        self.calls = []

    def click(self, *a, **kw):
        self.calls.append(("click", a, kw))

    def type_text(self, text, **_):
        self.calls.append(("type_text", text))

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))

    def scroll(self, *a, **kw):
        self.calls.append(("scroll", a, kw))


@pytest.fixture
def fake_executor(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    from core.action_executor import ActionExecutor

    return ActionExecutor


def test_unknown_action_returns_error(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "warp_drive"})
    assert out["success"] is False
    assert "unknown" in out.get("error", "").lower()


def test_sensitive_text_is_blocked(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "type_text", "text": "my password is hunter2"})
    assert out["success"] is False
    assert out.get("error") == "sensitive_field"


def test_dry_run_does_not_invoke_handler(fake_executor):
    ex = fake_executor(dry_run=True)
    out = ex.execute_sync({"action": "click", "x": 1, "y": 2})
    assert out["success"] is True
    assert out.get("dry_run") is True
    assert ex._desktop.calls == []  # no real click happened


def test_dry_run_still_runs_read_only_actions(fake_executor):
    ex = fake_executor(dry_run=True)
    # `note` is read-only — should still report success and not be marked dry_run.
    out = ex.execute_sync({"action": "note", "text": "hi"})
    assert out["success"] is True
    assert not out.get("dry_run")


def test_normal_click_routes_to_desktop(fake_executor):
    ex = fake_executor(dry_run=False)
    out = ex.execute_sync({"action": "click", "x": 5, "y": 6})
    assert out["success"] is True
    assert any(c[0] == "click" for c in ex._desktop.calls)


def test_pre_action_callback_fires_before_dispatch(fake_executor):
    seen = []
    ex = fake_executor(pre_action_callback=lambda a: seen.append(a["action"]))
    ex.execute_sync({"action": "click", "x": 1, "y": 2})
    ex.execute_sync({"action": "press_key", "key": "enter"})
    assert seen == ["click", "press_key"]


def test_pre_action_callback_failure_does_not_break_dispatch(fake_executor):
    def boom(_a):
        raise RuntimeError("kaboom")

    ex = fake_executor(pre_action_callback=boom)
    out = ex.execute_sync({"action": "click", "x": 1, "y": 2})
    assert out["success"] is True


def test_click_text_handler_returns_text_not_found_without_ocr(fake_executor, monkeypatch):
    # When Tesseract isn't available, find_text returns None and the
    # handler must report a clean error rather than crashing.
    from core import utils

    monkeypatch.setattr(utils, "have_tesseract", lambda: False)
    ex = fake_executor()
    out = ex.execute_sync({"action": "click_text", "text": "Send"})
    assert out["success"] is False
    assert out["error"] == "text_not_found"


def test_dispatch_has_new_uia_and_ocr_handlers(fake_executor):
    ex = fake_executor()
    for name in ("click_text", "read_text", "click_control", "set_text", "list_controls"):
        assert name in ex._dispatch_table, f"missing handler: {name}"


# ---- _contains_sensitive edge cases ----


def test_sensitive_password_keyword(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "type_text", "text": "enter password here"})
    assert out["success"] is False
    assert out["error"] == "sensitive_field"


def test_sensitive_api_key_keyword(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "type_text", "text": "my api_key = 12345"})
    assert out["success"] is False
    assert out["error"] == "sensitive_field"


def test_sensitive_ssn_keyword(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "type_text", "text": "social_security number"})
    assert out["success"] is False
    assert out["error"] == "sensitive_field"


def test_sensitive_case_insensitive(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "type_text", "text": "SECRET value"})
    assert out["success"] is False
    assert out["error"] == "sensitive_field"


def test_not_sensitive_normal_text(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": "type_text", "text": "Hello World"})
    assert out["success"] is True


def test_not_sensitive_similar_words(fake_executor):
    """Words containing 'pass' but not exact keyword should pass."""
    ex = fake_executor()
    out = ex.execute_sync({"action": "type_text", "text": "passenger bypass"})
    assert out["success"] is True


def test_contains_sensitive_token_keyword():
    from core.action_executor import _contains_sensitive

    assert _contains_sensitive("bearer token for auth") is True
    assert _contains_sensitive("hello world") is False
    assert _contains_sensitive("credit_card=4111") is True
    assert _contains_sensitive("PIN code") is True
    assert _contains_sensitive("passwd reset") is True


def test_contains_sensitive_empty_string():
    from core.action_executor import _contains_sensitive

    assert _contains_sensitive("") is False


# ---- _sanitize_params edge cases ----


def test_sanitize_truncates_long_strings():
    from core.action_executor import _sanitize_params

    params = {"text": "x" * 500}
    result = _sanitize_params(params)
    assert len(result["text"]) == 203  # 200 + "..."
    assert result["text"].endswith("...")


def test_sanitize_preserves_short_strings():
    from core.action_executor import _sanitize_params

    params = {"key": "short", "num": 42}
    result = _sanitize_params(params)
    assert result == {"key": "short", "num": 42}


def test_sanitize_large_list():
    from core.action_executor import _sanitize_params

    params = {"items": list(range(1000))}
    result = _sanitize_params(params)
    assert isinstance(result["items"], str)
    assert "list" in result["items"].lower()


def test_sanitize_large_dict():
    from core.action_executor import _sanitize_params

    params = {"data": {f"k{i}": f"v{i}" for i in range(200)}}
    result = _sanitize_params(params)
    assert isinstance(result["data"], str)
    assert "dict" in result["data"].lower()


# ---- _dry_run_result helper ----


def test_dry_run_result_format():
    from core.action_executor import _dry_run_result

    result = _dry_run_result("click", {"x": 1, "y": 2})
    assert result["success"] is True
    assert result["dry_run"] is True
    assert "click" in result["output"]
    assert "DRY-RUN" in result["output"]


def test_dry_run_result_truncates_long_params():
    from core.action_executor import _dry_run_result

    params = {"data": "x" * 500}
    result = _dry_run_result("type_text", params)
    assert result["success"] is True
    # The output message should not be excessively long
    assert len(result["output"]) < 400


# ---- Action log tracking ----


def test_action_log_tracks_executions(fake_executor):
    ex = fake_executor()
    ex.execute_sync({"action": "click", "x": 1, "y": 2})
    ex.execute_sync({"action": "press_key", "key": "enter"})
    log = ex.log
    assert len(log) == 2
    assert log[0]["action"] == "click"
    assert log[1]["action"] == "press_key"


def test_action_log_is_a_copy(fake_executor):
    ex = fake_executor()
    ex.execute_sync({"action": "click", "x": 1, "y": 2})
    log_copy = ex.log
    log_copy.append({"action": "tampered"})
    assert len(ex.log) == 1  # internal log unchanged


# ---- Dry-run for all state-changing actions ----


@pytest.mark.parametrize(
    "action",
    [
        {"action": "click", "x": 1, "y": 2},
        {"action": "type_text", "text": "hi"},
        {"action": "press_key", "key": "enter"},
        {"action": "hotkey", "keys": ["ctrl", "c"]},
        {"action": "scroll", "amount": 3},
        {"action": "drag", "from_x": 0, "from_y": 0, "to_x": 100, "to_y": 100},
    ],
)
def test_dry_run_blocks_state_changing_actions(fake_executor, action):
    ex = fake_executor(dry_run=True)
    out = ex.execute_sync(action)
    assert out["success"] is True
    assert out.get("dry_run") is True
    assert ex._desktop.calls == []


# ---- Read-only actions still run in dry-run ----


def test_dry_run_screenshot_still_runs(fake_executor, monkeypatch):
    from core import screenshot as ss

    monkeypatch.setattr(ss, "capture_to_base64", lambda **kw: "fake_base64")
    ex = fake_executor(dry_run=True)
    out = ex.execute_sync({"action": "screenshot"})
    assert out["success"] is True
    assert not out.get("dry_run")


def test_dry_run_read_file_still_runs(fake_executor, tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello from test")
    ex = fake_executor(dry_run=True)
    out = ex.execute_sync({"action": "read_file", "path": str(test_file)})
    assert out["success"] is True
    assert "hello from test" in out["output"]


def test_dry_run_system_info_still_runs(fake_executor, monkeypatch):
    from core import system_info as si

    monkeypatch.setattr(si, "system_info", lambda: {"os": "test"})
    ex = fake_executor(dry_run=True)
    out = ex.execute_sync({"action": "system_info"})
    assert out["success"] is True
    assert not out.get("dry_run")


# ---- Exception handling in handlers ----


def test_handler_exception_returns_error(fake_executor, monkeypatch):
    """If a handler throws internally and catches, returns error dict."""
    ex = fake_executor()

    # The hotkey handler catches exceptions and returns hotkey_failed
    def boom_hotkey(*keys):
        raise RuntimeError("keyboard exploded")

    ex._desktop.hotkey = boom_hotkey
    out = ex.execute_sync({"action": "hotkey", "keys": ["ctrl", "c"]})
    assert out["success"] is False
    assert out["error"] == "hotkey_failed"


# ---- Empty/missing action key ----


def test_empty_action_string(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"action": ""})
    assert out["success"] is False
    assert "unknown" in out.get("error", "").lower()


def test_missing_action_key(fake_executor):
    ex = fake_executor()
    out = ex.execute_sync({"x": 1, "y": 2})
    assert out["success"] is False


# ---- Multiple sequential actions maintain log ----


def test_sequential_actions_log_in_order(fake_executor):
    ex = fake_executor()
    actions = [{"action": "click", "x": i, "y": i} for i in range(5)]
    for a in actions:
        ex.execute_sync(a)
    log = ex.log
    assert len(log) == 5
    for i, entry in enumerate(log):
        assert entry["action"] == "click"
        assert entry["success"] is True


# ---- Approval callback timeout handling ----


def test_approval_callback_timeout_returns_error(fake_executor):
    """Test that approval callback timeout is handled gracefully."""
    import asyncio

    async def never_approve(_action):
        """Simulate a user that never responds."""
        await asyncio.sleep(600)  # Sleep longer than timeout
        return True

    async def run_timeout_test():
        ex = fake_executor(approval_callback=never_approve)
        # Monkey patch the timeout to be very short for testing
        from core import action_executor

        original_timeout = action_executor.APPROVAL_CALLBACK_TIMEOUT
        action_executor.APPROVAL_CALLBACK_TIMEOUT = 0.1  # 100ms

        try:
            # v18: the deprecated async execute() wrapper was removed; the
            # approval-gate timeout logic lives in _execute_with_logging.
            out = await ex._execute_with_logging({"action": "click", "x": 1, "y": 2})
            return out
        finally:
            action_executor.APPROVAL_CALLBACK_TIMEOUT = original_timeout

    out = asyncio.run(run_timeout_test())
    assert out["success"] is False
    assert out.get("error") == "timeout"
    assert "approval timed out" in out.get("output", "").lower()


def test_approval_callback_rejection_returns_error(fake_executor):
    """Test that rejected approval returns proper error."""

    async def always_reject(_action):
        return False

    async def run_rejection_test():
        ex = fake_executor(approval_callback=always_reject)
        return await ex._execute_with_logging({"action": "click", "x": 1, "y": 2})

    out = asyncio.run(run_rejection_test())
    assert out["success"] is False
    assert out.get("error") == "rejected"
    assert "rejected" in out.get("output", "").lower()


def test_approval_callback_acceptance_allows_action(fake_executor):
    """Test that approved actions execute normally."""

    async def always_approve(_action):
        return True

    async def run_approval_test():
        ex = fake_executor(approval_callback=always_approve)
        return await ex._execute_with_logging({"action": "click", "x": 1, "y": 2})

    out = asyncio.run(run_approval_test())
    assert out["success"] is True
