"""Gap tests for tool_schemas.py — duplicate names, required params, dispatch coverage."""

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


class TestNoDuplicateToolNames:
    """Every tool name is unique."""

    def test_no_duplicate_names(self):
        names = [t["function"]["name"] for t in TOOLS]
        assert len(names) == len(set(names)), f"Duplicates: {[n for n in names if names.count(n) > 1]}"


class TestAllToolsHaveDescription:
    """Every tool has a non-empty description."""

    def test_all_have_description(self):
        for tool in TOOLS:
            desc = tool["function"].get("description", "")
            assert desc and len(desc) > 5, f"{tool['function']['name']} has no description"


class TestRequiredParamsPresent:
    """Tools with required params have matching properties."""

    def test_required_in_properties(self):
        for tool in TOOLS:
            params = tool["function"].get("parameters", {})
            required = params.get("required", [])
            properties = params.get("properties", {})
            for req in required:
                assert req in properties, f"{tool['function']['name']}: required '{req}' not in properties"


class TestAllDispatchEntriesHaveSchemas:
    """Every dispatch table entry has a corresponding tool schema."""

    def test_dispatch_covers_all_schemas(self):
        original = desktop_mod.DesktopEngine
        desktop_mod.DesktopEngine = FakeDesktop
        try:
            from core.action_executor import ActionExecutor

            ex = ActionExecutor()
            dispatch = set(ex._dispatch_table.keys())
        finally:
            desktop_mod.DesktopEngine = original

        schema_names = {t["function"]["name"] for t in TOOLS}

        # Every schema name should have a dispatch entry
        missing = schema_names - dispatch
        assert not missing, f"Schemas without dispatch: {missing}"


class TestToolCapableProviders:
    """TOOL_CAPABLE_PROVIDERS contains expected providers."""

    def test_google_included(self):
        assert "google" in TOOL_CAPABLE_PROVIDERS

    def test_deepseek_included(self):
        assert "deepseek" in TOOL_CAPABLE_PROVIDERS

    def test_groq_included(self):
        assert "groq" in TOOL_CAPABLE_PROVIDERS


class TestToolsCount:
    """TOOLS has a reasonable number of entries."""

    def test_at_least_30_tools(self):
        assert len(TOOLS) >= 30

    def test_at_most_50_tools(self):
        assert len(TOOLS) <= 50


class TestToolFunctionFields:
    """Each tool has type='function' and function with name."""

    def test_all_have_type_function(self):
        for tool in TOOLS:
            assert tool.get("type") == "function"

    def test_all_function_names_are_strings(self):
        for tool in TOOLS:
            name = tool["function"]["name"]
            assert isinstance(name, str) and name.isidentifier(), f"Bad name: {name}"


class TestParameterTypes:
    """All parameter type fields are valid JSON Schema types."""

    def test_valid_param_types(self):
        valid_types = {"string", "integer", "number", "boolean", "array", "object"}
        for tool in TOOLS:
            for pname, pdef in tool["function"].get("parameters", {}).get("properties", {}).items():
                ptype = pdef.get("type")
                assert ptype in valid_types, f"{tool['function']['name']}.{pname} has invalid type: {ptype}"
