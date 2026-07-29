"""Tests for core/legacy_engine.py — CommandResult and CommandEngine parsing."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.legacy_engine import CommandEngine, CommandResult


@pytest.fixture
def engine(monkeypatch):
    """Build a CommandEngine with no-op defaults and a fake brain.

    ``_register_defaults`` imports many subcommand modules that require system
    access, so we neutralise it and inject a mock brain to keep the engine
    self-contained.
    """
    monkeypatch.setattr(CommandEngine, "_register_defaults", lambda self: None)
    return CommandEngine(brain=MagicMock())


class TestCommandResult:
    """Construction and representation of CommandResult."""

    def test_defaults(self):
        result = CommandResult(True, "ok")
        assert result.success is True
        assert result.message == "ok"
        assert result.data == {}

    def test_str_returns_message(self):
        result = CommandResult(True, "hello there")
        assert str(result) == "hello there"

    def test_data_default_not_shared(self):
        a = CommandResult(True, "a")
        b = CommandResult(True, "b")
        assert a.data is not b.data
        a.data["key"] = 1
        assert "key" not in b.data

    def test_custom_data_preserved(self):
        payload = {"value": 42}
        result = CommandResult(True, "ok", data=payload)
        assert result.data is payload


class TestParseCommand:
    """Natural-language routing: text -> (category, args)."""

    def test_command_routing(self, engine):
        cases = {
            "help": ("system", "help"),
            "cpu": ("system", "cpu"),
            "memory": ("system", "memory"),
            "ram": ("system", "memory"),
            "disk": ("system", "disk"),
            "battery": ("system", "battery"),
            "uptime": ("system", "uptime"),
            "temperature": ("system", "temperature"),
            "temp": ("system", "temperature"),
            "shutdown": ("power", "shutdown"),
            "speak hello": ("voice", "speak hello"),
            "record macro": ("macros", "record macro"),
            "list plugins": ("plugins", "list plugins"),
            "notify me": ("notify", "notify me"),
            "set timer": ("scheduler", "set timer"),
            "volume up": ("media", "volume up"),
            "click something": ("automation", "click something"),
            "type hello": ("automation", "type hello"),
            "ping google": ("network", "ping google"),
            "browse example.com": ("web", "browse example.com"),
            "kill firefox": ("process", "kill firefox"),
            "copy text": ("clipboard", "copy text"),
            "list windows": ("windows", "list"),
            "find file": ("files", "find file"),
            "think topic content": ("ai", "think topic content"),
            "brain status": ("ai", "brain status"),
            "recall something": ("ai", "recall something"),
        }
        for text, expected in cases.items():
            assert engine.parse_command(text) == expected, f"failed for: {text!r}"

    def test_complex_task_routing(self, engine):
        assert engine.parse_command("do this then that") == ("agent", "do this then that")
        assert engine.parse_command("first do X, then Y, and finally Z") == (
            "agent",
            "first do X, then Y, and finally Z",
        )

    def test_fallback_returns_none(self, engine):
        assert engine.parse_command("xyzzy nonsense 12345") is None


class TestIsComplexTask:
    """Multi-step request detection."""

    def test_then_indicator(self, engine):
        assert engine._is_complex_task("do this then that") is True

    def test_after_that_indicator(self, engine):
        assert engine._is_complex_task("go home after that") is True

    def test_first_indicator(self, engine):
        assert engine._is_complex_task("first do your homework") is True

    def test_comma_heavy_long_string(self, engine):
        assert engine._is_complex_task("a, b, c, d, e, f, g") is True

    def test_simple_task_not_complex(self, engine):
        assert engine._is_complex_task("open the browser") is False


class TestConversationalResponse:
    """Greetings and common conversational inputs return a string."""

    @pytest.mark.parametrize(
        "text",
        [
            "hey",
            "hi",
            "hello",
            "thanks",
            "bye",
            "how are you",
            "who are you",
            "i love you",
            "ok",
            "help me",
        ],
    )
    def test_returns_non_none(self, engine, text):
        assert engine._conversational_response(text) is not None
