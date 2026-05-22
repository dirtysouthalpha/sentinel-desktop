"""Tests confirming the tool schemas line up with the dispatch table."""

import pytest

import core.desktop as desktop_mod
from core.tool_schemas import TOOL_CAPABLE_PROVIDERS, TOOLS


class FakeDesktop:
    def click(self, *a, **kw):
        pass

    def type_text(self, *a, **kw):
        pass

    def press_key(self, *a, **kw):
        pass

    def hotkey(self, *a, **kw):
        pass

    def scroll(self, *a, **kw):
        pass


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


# ========== Extended tool schema validation tests ==========

def test_tool_names_are_unique():
    names = [t["function"]["name"] for t in TOOLS]
    assert len(names) == len(set(names)), f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"


def test_tool_count_sanity():
    assert len(TOOLS) >= 20, f"Only {len(TOOLS)} tools — expected at least 20"


def test_every_tool_has_description():
    for tool in TOOLS:
        fn = tool["function"]
        desc = fn.get("description", "")
        assert isinstance(desc, str) and desc.strip(), f"Tool '{fn['name']}' missing description"


def test_every_parameter_has_type():
    valid_types = {"string", "integer", "number", "boolean", "array", "object"}
    for tool in TOOLS:
        fn = tool["function"]
        props = fn.get("parameters", {}).get("properties", {})
        for pname, pdef in props.items():
            assert "type" in pdef, f"Tool '{fn['name']}' param '{pname}' missing type"
            assert pdef["type"] in valid_types, (
                f"Tool '{fn['name']}' param '{pname}' has invalid type '{pdef['type']}'"
            )


def test_every_parameter_has_type_and_optional_description():
    """Every parameter should have at minimum a type; description is recommended."""
    for tool in TOOLS:
        fn = tool["function"]
        props = fn.get("parameters", {}).get("properties", {})
        for pname, pdef in props.items():
            assert "type" in pdef, (
                f"Tool '{fn['name']}' param '{pname}' missing type field"
            )


def test_required_params_exist_in_properties():
    for tool in TOOLS:
        fn = tool["function"]
        params = fn.get("parameters", {})
        props = set(params.get("properties", {}).keys())
        for req in params.get("required", []):
            assert req in props, (
                f"Tool '{fn['name']}' requires '{req}' but it's not in properties"
            )


def test_enum_params_have_at_least_two_values():
    for tool in TOOLS:
        fn = tool["function"]
        props = fn.get("parameters", {}).get("properties", {})
        for pname, pdef in props.items():
            if "enum" in pdef:
                assert len(pdef["enum"]) >= 2, (
                    f"Tool '{fn['name']}' param '{pname}' enum has < 2 values"
                )


def test_default_type_matches_property_type():
    for tool in TOOLS:
        fn = tool["function"]
        props = fn.get("parameters", {}).get("properties", {})
        for pname, pdef in props.items():
            if "default" not in pdef:
                continue
            default_val = pdef["default"]
            ptype = pdef.get("type")
            if ptype == "string":
                assert isinstance(default_val, str), (
                    f"Tool '{fn['name']}' param '{pname}' default is not string"
                )
            elif ptype == "integer":
                assert isinstance(default_val, int) and not isinstance(default_val, bool), (
                    f"Tool '{fn['name']}' param '{pname}' default is not integer"
                )
            elif ptype == "boolean":
                assert isinstance(default_val, bool), (
                    f"Tool '{fn['name']}' param '{pname}' default is not boolean"
                )


def test_click_tool_requires_xy():
    tool = _get_tool("click")
    assert set(tool["function"]["parameters"]["required"]) == {"x", "y"}


def test_type_text_requires_text():
    tool = _get_tool("type_text")
    assert "text" in tool["function"]["parameters"]["required"]


def test_press_key_requires_key():
    tool = _get_tool("press_key")
    assert "key" in tool["function"]["parameters"]["required"]


def test_hotkey_requires_keys():
    tool = _get_tool("hotkey")
    assert "keys" in tool["function"]["parameters"]["required"]


def test_scroll_requires_amount():
    tool = _get_tool("scroll")
    assert "amount" in tool["function"]["parameters"]["required"]


def test_smart_open_requires_name():
    tool = _get_tool("smart_open")
    assert "name" in tool["function"]["parameters"]["required"]


def test_specific_tools_exist():
    expected = ["wait", "screenshot", "read_text", "drag", "finish", "note",
                "clipboard_read", "clipboard_write", "list_windows", "close_window"]
    names = {t["function"]["name"] for t in TOOLS}
    for name in expected:
        assert name in names, f"Expected tool '{name}' not found in TOOLS"


def test_tool_capable_providers_is_set():
    assert isinstance(TOOL_CAPABLE_PROVIDERS, set)


def test_all_providers_are_lowercase_strings():
    for provider in TOOL_CAPABLE_PROVIDERS:
        assert isinstance(provider, str), f"Provider {provider!r} is not a string"
        assert provider == provider.lower(), f"Provider '{provider}' is not lowercase"


def test_major_providers_present():
    major = {"openai", "anthropic", "google", "deepseek", "zai", "groq", "mistral"}
    missing = major - TOOL_CAPABLE_PROVIDERS
    assert not missing, f"Missing major providers: {missing}"


def test_tool_function_keys_are_valid():
    for tool in TOOLS:
        fn = tool["function"]
        assert "name" in fn, f"Tool missing 'name': {tool}"
        assert "description" in fn, f"Tool '{fn.get('name')}' missing 'description'"
        assert "parameters" in fn, f"Tool '{fn['name']}' missing 'parameters'"


# Helper
def _get_tool(name):
    for t in TOOLS:
        if t["function"]["name"] == name:
            return t
    pytest.fail(f"Tool '{name}' not found")
