"""Tests confirming the tool schemas line up with the dispatch table."""
import pytest

import core.desktop as desktop_mod
from core.tool_schemas import TOOLS, TOOL_CAPABLE_PROVIDERS


class FakeDesktop:
    def click(self, *a, **kw): pass
    def type_text(self, *a, **kw): pass
    def press_key(self, *a, **kw): pass
    def hotkey(self, *a, **kw): pass
    def scroll(self, *a, **kw): pass


@pytest.fixture
def executor_cls(monkeypatch):
    monkeypatch.setattr(desktop_mod, "DesktopEngine", FakeDesktop)
    from core.action_executor import ActionExecutor
    return ActionExecutor


def test_every_tool_has_a_handler(executor_cls):
    ex = executor_cls()
    dispatch = ex._dispatch_table
    for tool in TOOLS:
        name = tool["function"]["name"]
        assert name in dispatch, f"tool '{name}' has no executor handler"


def test_smart_open_tool_is_listed():
    names = {t["function"]["name"] for t in TOOLS}
    assert "smart_open" in names


def test_anthropic_and_openai_are_marked_tool_capable():
    assert "openai" in TOOL_CAPABLE_PROVIDERS
    assert "anthropic" in TOOL_CAPABLE_PROVIDERS


def test_tool_parameters_are_well_formed():
    for tool in TOOLS:
        assert tool.get("type") == "function"
        fn = tool["function"]
        assert isinstance(fn.get("name"), str) and fn["name"]
        params = fn.get("parameters", {})
        assert params.get("type") == "object"
        assert "properties" in params
