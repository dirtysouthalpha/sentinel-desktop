"""Tests for Engine._handle_consecutive_failure — centralized failure tracking."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.engine import AgentEngine


def _make_engine(**overrides) -> AgentEngine:
    """Create a minimal Engine instance for testing _handle_consecutive_failure."""
    eng = AgentEngine.__new__(AgentEngine)
    eng.config = {
        "provider": "openai",
        "api_key": "sk-test",
        "model": "gpt-4o",
        "max_steps": 5,
        "use_tools": False,
        "auto_screenshot": False,
    }
    eng.config.update(overrides)
    eng.running = True
    eng.step = 1
    eng.notes: list[str] = []
    eng.forensic_log: list[dict] = []
    eng.finish_summary = ""
    eng.max_steps = 5
    eng._consecutive_failures = 0
    eng.llm = MagicMock()
    eng.executor = MagicMock()
    eng.logger = MagicMock()
    eng.checkpoint = MagicMock()
    eng.gate = MagicMock()
    eng.MAX_CONSECUTIVE_FAILURES = 3
    eng.RECOVERY_PROMPT_THRESHOLD = 2
    return eng


# ========================== Tests ==========================


def test_llm_call_failure_increments_counter() -> None:
    """LLM call failure increments _consecutive_failures."""
    engine = _make_engine()
    messages: list[dict] = []

    result = engine._handle_consecutive_failure("llm_call", messages)

    assert result == "continue"
    assert engine._consecutive_failures == 1


def test_parse_failure_increments_counter() -> None:
    """Parse failure increments _consecutive_failures."""
    engine = _make_engine()
    messages: list[dict] = []

    result = engine._handle_consecutive_failure("parse", messages)

    assert result == "continue"
    assert engine._consecutive_failures == 1


def test_max_consecutive_failures_aborts() -> None:
    """When failures reach MAX_CONSECUTIVE_FAILURES, method returns 'abort'."""
    engine = _make_engine()
    engine._consecutive_failures = 2  # one below max of 3
    messages: list[dict] = []

    result = engine._handle_consecutive_failure("llm_call", messages)

    assert result == "abort"
    assert engine._consecutive_failures == 3
    assert any("Terminating" in n for n in engine.notes)
    engine.logger.log_event.assert_called_once_with(
        "abort",
        {"reason": "max_consecutive_failures", "count": 3},
    )


def test_recovery_prompt_injected_at_threshold() -> None:
    """LLM call failure at threshold injects recovery prompt."""
    engine = _make_engine()
    engine._consecutive_failures = 1  # next will be 2 = threshold
    messages: list[dict] = []

    result = engine._handle_consecutive_failure("llm_call", messages)

    assert result == "continue"
    assert engine._consecutive_failures == 2
    # Should have injected the recovery prompt
    assert len(messages) == 1
    assert "different approach" in messages[0]["content"]


def test_parse_failure_injects_json_nudge() -> None:
    """Parse failure always injects the 'valid JSON' nudge message."""
    engine = _make_engine()
    messages: list[dict] = []

    engine._handle_consecutive_failure("parse", messages)

    # First message should be the JSON nudge
    assert len(messages) >= 1
    assert "valid JSON" in messages[0]["content"]


def test_parse_failure_adds_note() -> None:
    """Parse failure appends a note about the failure."""
    engine = _make_engine()
    engine.step = 7
    messages: list[dict] = []

    engine._handle_consecutive_failure("parse", messages)

    assert any("Step 7" in n for n in engine.notes)


def test_parse_recovery_prompt_at_threshold() -> None:
    """Parse failure at threshold injects the parse-specific recovery prompt."""
    engine = _make_engine()
    engine._consecutive_failures = 1  # next = 2 = threshold
    messages: list[dict] = []

    result = engine._handle_consecutive_failure("parse", messages)

    assert result == "continue"
    # Should have JSON nudge + parse recovery prompt
    assert len(messages) == 2
    assert "parse failures" in messages[1]["content"]


def test_llm_call_does_not_add_json_nudge() -> None:
    """LLM call failure should NOT inject the 'valid JSON' nudge."""
    engine = _make_engine()
    messages: list[dict] = []

    engine._handle_consecutive_failure("llm_call", messages)

    # No messages injected (below threshold)
    assert len(messages) == 0


def test_no_recovery_prompt_below_threshold() -> None:
    """Below threshold, no recovery prompt is injected for LLM failures."""
    engine = _make_engine()
    engine._consecutive_failures = 0  # next = 1, below threshold of 2
    messages: list[dict] = []

    engine._handle_consecutive_failure("llm_call", messages)

    assert len(messages) == 0


def test_abort_takes_priority_over_recovery() -> None:
    """At MAX, abort should be returned even though threshold is also exceeded."""
    engine = _make_engine()
    engine._consecutive_failures = 2  # next = 3 = MAX
    messages: list[dict] = []

    result = engine._handle_consecutive_failure("llm_call", messages)

    assert result == "abort"
    # No recovery prompt injected — abort short-circuits
    assert len(messages) == 0
