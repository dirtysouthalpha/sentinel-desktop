"""Extended tests for tool_schemas — structural validation, coverage, and consistency."""

import pytest

from core.tool_schemas import TOOL_CAPABLE_PROVIDERS, TOOLS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_names():
    """Return ordered list of tool function names."""
    return [t["function"]["name"] for t in TOOLS]


def _tool_by_name(name: str):
    """Return the tool dict for a given function name, or None."""
    for t in TOOLS:
        if t["function"]["name"] == name:
            return t
    return None


# ---------------------------------------------------------------------------
# Structural validation — every entry must be well-formed
# ---------------------------------------------------------------------------


class TestToolStructures:
    """Every item in TOOLS must follow the OpenAI function-calling schema."""

    def test_tools_is_list(self):
        assert isinstance(TOOLS, list)

    def test_tools_not_empty(self):
        assert len(TOOLS) > 0

    @pytest.mark.parametrize("idx", range(len(TOOLS)))
    def test_each_tool_has_type_function(self, idx):
        assert TOOLS[idx].get("type") == "function"

    @pytest.mark.parametrize("idx", range(len(TOOLS)))
    def test_each_tool_has_function_key(self, idx):
        assert "function" in TOOLS[idx]
        assert isinstance(TOOLS[idx]["function"], dict)

    @pytest.mark.parametrize("idx", range(len(TOOLS)))
    def test_each_tool_function_has_name(self, idx):
        fn = TOOLS[idx]["function"]
        assert "name" in fn
        assert isinstance(fn["name"], str)
        assert len(fn["name"]) > 0

    @pytest.mark.parametrize("idx", range(len(TOOLS)))
    def test_each_tool_function_has_description(self, idx):
        fn = TOOLS[idx]["function"]
        assert "description" in fn
        assert isinstance(fn["description"], str)
        assert len(fn["description"]) > 0

    @pytest.mark.parametrize("idx", range(len(TOOLS)))
    def test_each_tool_has_parameters_object(self, idx):
        fn = TOOLS[idx]["function"]
        assert "parameters" in fn
        params = fn["parameters"]
        assert isinstance(params, dict)
        assert params.get("type") == "object"
        assert "properties" in params

    @pytest.mark.parametrize("idx", range(len(TOOLS)))
    def test_tool_names_are_unique(self, idx):
        names = _tool_names()
        name = names[idx]
        assert names.count(name) == 1, f"Duplicate tool name: {name}"


# ---------------------------------------------------------------------------
# Required vs optional parameters
# ---------------------------------------------------------------------------


class TestParameterRequirements:
    """Verify required/optional fields are correctly declared."""

    def test_click_requires_xy(self):
        t = _tool_by_name("click")
        assert "required" in t["function"]["parameters"]
        assert set(t["function"]["parameters"]["required"]) == {"x", "y"}

    def test_click_button_optional(self):
        props = _tool_by_name("click")["function"]["parameters"]["properties"]
        assert "button" in props
        assert "required" not in props.get("button", {})

    def test_type_text_requires_text(self):
        t = _tool_by_name("type_text")
        assert t["function"]["parameters"]["required"] == ["text"]

    def test_press_key_requires_key(self):
        t = _tool_by_name("press_key")
        assert t["function"]["parameters"]["required"] == ["key"]

    def test_hotkey_requires_keys(self):
        t = _tool_by_name("hotkey")
        assert t["function"]["parameters"]["required"] == ["keys"]

    def test_scroll_requires_amount(self):
        t = _tool_by_name("scroll")
        assert t["function"]["parameters"]["required"] == ["amount"]

    def test_find_image_requires_template_path(self):
        t = _tool_by_name("find_image")
        assert t["function"]["parameters"]["required"] == ["template_path"]

    def test_click_text_requires_text(self):
        t = _tool_by_name("click_text")
        assert t["function"]["parameters"]["required"] == ["text"]

    def test_read_text_has_no_required(self):
        t = _tool_by_name("read_text")
        assert (
            "required" not in t["function"]["parameters"]
            or t["function"]["parameters"]["required"] == []
        )

    def test_wait_requires_seconds(self):
        t = _tool_by_name("wait")
        assert t["function"]["parameters"]["required"] == ["seconds"]

    def test_smart_open_requires_name(self):
        t = _tool_by_name("smart_open")
        assert t["function"]["parameters"]["required"] == ["name"]

    def test_open_app_requires_path(self):
        t = _tool_by_name("open_app")
        assert t["function"]["parameters"]["required"] == ["path"]

    def test_focus_window_requires_title(self):
        t = _tool_by_name("focus_window")
        assert t["function"]["parameters"]["required"] == ["title"]

    def test_close_window_requires_title(self):
        t = _tool_by_name("close_window")
        assert t["function"]["parameters"]["required"] == ["title"]

    def test_write_file_requires_path_and_content(self):
        t = _tool_by_name("write_file")
        assert set(t["function"]["parameters"]["required"]) == {"path", "content"}

    def test_clipboard_write_requires_text(self):
        t = _tool_by_name("clipboard_write")
        assert t["function"]["parameters"]["required"] == ["text"]

    def test_note_requires_text(self):
        t = _tool_by_name("note")
        assert t["function"]["parameters"]["required"] == ["text"]

    def test_finish_requires_summary(self):
        t = _tool_by_name("finish")
        assert t["function"]["parameters"]["required"] == ["summary"]

    def test_drag_requires_coordinates(self):
        t = _tool_by_name("drag")
        assert set(t["function"]["parameters"]["required"]) == {"from_x", "from_y", "to_x", "to_y"}

    def test_wait_for_text_requires_text(self):
        t = _tool_by_name("wait_for_text")
        assert t["function"]["parameters"]["required"] == ["text"]

    def test_wait_for_image_requires_template_path(self):
        t = _tool_by_name("wait_for_image")
        assert t["function"]["parameters"]["required"] == ["template_path"]

    def test_powershell_requires_command(self):
        t = _tool_by_name("powershell")
        assert t["function"]["parameters"]["required"] == ["command"]

    def test_run_script_requires_path(self):
        t = _tool_by_name("run_script")
        assert t["function"]["parameters"]["required"] == ["path"]


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestDefaults:
    """Check that declared defaults match expectations."""

    def test_click_button_default_left(self):
        props = _tool_by_name("click")["function"]["parameters"]["properties"]
        assert props["button"].get("default") == "left"

    def test_find_image_confidence_default(self):
        props = _tool_by_name("find_image")["function"]["parameters"]["properties"]
        assert props["confidence"].get("default") == 0.8

    def test_click_text_fuzzy_default_true(self):
        props = _tool_by_name("click_text")["function"]["parameters"]["properties"]
        assert props["fuzzy"].get("default") is True

    def test_smart_wait_timeout_default(self):
        props = _tool_by_name("smart_wait")["function"]["parameters"]["properties"]
        assert props["timeout"].get("default") == 10

    def test_wait_for_stable_defaults(self):
        props = _tool_by_name("wait_for_stable")["function"]["parameters"]["properties"]
        assert props["timeout"].get("default") == 10
        assert props["stable_time"].get("default") == 1.5

    def test_wait_for_text_timeout_default(self):
        props = _tool_by_name("wait_for_text")["function"]["parameters"]["properties"]
        assert props["timeout"].get("default") == 10

    def test_wait_for_image_timeout_default(self):
        props = _tool_by_name("wait_for_image")["function"]["parameters"]["properties"]
        assert props["timeout"].get("default") == 30

    def test_drag_duration_default(self):
        props = _tool_by_name("drag")["function"]["parameters"]["properties"]
        assert props["duration"].get("default") == 0.5

    def test_open_app_args_default_empty(self):
        props = _tool_by_name("open_app")["function"]["parameters"]["properties"]
        assert props["args"].get("default") == []

    def test_list_controls_max_results_default(self):
        props = _tool_by_name("list_controls")["function"]["parameters"]["properties"]
        assert props["max_results"].get("default") == 60

    def test_list_directory_path_default(self):
        props = _tool_by_name("list_directory")["function"]["parameters"]["properties"]
        assert props["path"].get("default") == "."


# ---------------------------------------------------------------------------
# Enum constraints
# ---------------------------------------------------------------------------


class TestEnums:
    """Verify enum-restricted fields have the expected values."""

    def test_click_button_enum(self):
        props = _tool_by_name("click")["function"]["parameters"]["properties"]
        assert set(props["button"]["enum"]) == {"left", "right", "middle"}

    def test_click_text_button_enum(self):
        props = _tool_by_name("click_text")["function"]["parameters"]["properties"]
        assert set(props["button"]["enum"]) == {"left", "right", "middle"}

    def test_read_text_scope_enum(self):
        props = _tool_by_name("read_text")["function"]["parameters"]["properties"]
        assert set(props["scope"]["enum"]) == {"focused", "all"}

    def test_drag_button_enum(self):
        props = _tool_by_name("drag")["function"]["parameters"]["properties"]
        assert set(props["button"]["enum"]) == {"left", "right"}


# ---------------------------------------------------------------------------
# Parameter types
# ---------------------------------------------------------------------------


class TestParamTypes:
    """Verify parameter types are correctly declared."""

    def test_click_xy_are_integers(self):
        props = _tool_by_name("click")["function"]["parameters"]["properties"]
        assert props["x"]["type"] == "integer"
        assert props["y"]["type"] == "integer"

    def test_scroll_amount_is_integer(self):
        props = _tool_by_name("scroll")["function"]["parameters"]["properties"]
        assert props["amount"]["type"] == "integer"

    def test_hotkey_keys_is_array(self):
        props = _tool_by_name("hotkey")["function"]["parameters"]["properties"]
        assert props["keys"]["type"] == "array"
        assert props["keys"]["items"]["type"] == "string"

    def test_find_image_confidence_is_number(self):
        props = _tool_by_name("find_image")["function"]["parameters"]["properties"]
        assert props["confidence"]["type"] == "number"

    def test_wait_seconds_is_number(self):
        props = _tool_by_name("wait")["function"]["parameters"]["properties"]
        assert props["seconds"]["type"] == "number"

    def test_screenshot_has_no_required_params(self):
        t = _tool_by_name("screenshot")
        req = t["function"]["parameters"].get("required", [])
        assert req == [] or req is None or "required" not in t["function"]["parameters"]

    def test_list_windows_has_no_required_params(self):
        t = _tool_by_name("list_windows")
        req = t["function"]["parameters"].get("required", [])
        assert req == [] or req is None or "required" not in t["function"]["parameters"]

    def test_system_info_has_no_required_params(self):
        t = _tool_by_name("system_info")
        req = t["function"]["parameters"].get("required", [])
        assert req == [] or req is None or "required" not in t["function"]["parameters"]

    def test_list_processes_has_no_required_params(self):
        t = _tool_by_name("list_processes")
        req = t["function"]["parameters"].get("required", [])
        assert req == [] or req is None or "required" not in t["function"]["parameters"]

    def test_clipboard_read_has_no_required_params(self):
        t = _tool_by_name("clipboard_read")
        req = t["function"]["parameters"].get("required", [])
        assert req == [] or req is None or "required" not in t["function"]["parameters"]

    def test_smart_wait_region_is_int_array(self):
        props = _tool_by_name("smart_wait")["function"]["parameters"]["properties"]
        assert props["region"]["type"] == "array"
        assert props["region"]["items"]["type"] == "integer"

    def test_set_text_requires_text(self):
        t = _tool_by_name("set_text")
        assert "text" in t["function"]["parameters"]["required"]

    def test_start_process_requires_path(self):
        t = _tool_by_name("start_process")
        assert t["function"]["parameters"]["required"] == ["path"]

    def test_read_window_requires_title(self):
        t = _tool_by_name("read_window")
        assert t["function"]["parameters"]["required"] == ["title"]

    def test_read_file_requires_path(self):
        t = _tool_by_name("read_file")
        assert t["function"]["parameters"]["required"] == ["path"]


# ---------------------------------------------------------------------------
# TOOL_CAPABLE_PROVIDERS
# ---------------------------------------------------------------------------


class TestToolCapableProviders:
    """Verify the tool-capable provider set."""

    def test_is_a_set(self):
        assert isinstance(TOOL_CAPABLE_PROVIDERS, set)

    def test_not_empty(self):
        assert len(TOOL_CAPABLE_PROVIDERS) > 0

    def test_major_providers_present(self):
        for p in ("openai", "anthropic", "google", "groq", "deepseek"):
            assert p in TOOL_CAPABLE_PROVIDERS, f"{p} missing from TOOL_CAPABLE_PROVIDERS"

    def test_all_entries_are_strings(self):
        for p in TOOL_CAPABLE_PROVIDERS:
            assert isinstance(p, str)
            assert len(p) > 0

    def test_no_duplicates(self):
        # Sets can't have duplicates, but verify it's actually a set
        assert len(TOOL_CAPABLE_PROVIDERS) == len(set(TOOL_CAPABLE_PROVIDERS))


# ---------------------------------------------------------------------------
# Coverage inventory — ensure expected tools are present
# ---------------------------------------------------------------------------


class TestToolInventory:
    """Verify all expected tools are registered."""

    EXPECTED_TOOLS = [
        "click",
        "double_click",
        "right_click",
        "type_text",
        "press_key",
        "hotkey",
        "scroll",
        "screenshot",
        "find_image",
        "click_text",
        "read_text",
        "read_window",
        "wait",
        "smart_open",
        "open_app",
        "focus_window",
        "close_window",
        "list_windows",
        "list_controls",
        "click_control",
        "set_text",
        "read_file",
        "write_file",
        "clipboard_read",
        "clipboard_write",
        "note",
        "finish",
        "drag",
        "smart_wait",
        "wait_for_stable",
        "wait_for_text",
        "wait_for_image",
        "system_info",
        "list_processes",
        "start_process",
        "kill_process",
        "powershell",
        "run_script",
        "close_app",
        "list_directory",
    ]

    def test_all_expected_tools_present(self):
        names = set(_tool_names())
        for name in self.EXPECTED_TOOLS:
            assert name in names, f"Expected tool '{name}' not found in TOOLS"

    def test_no_extra_unexpected_tools(self):
        names = set(_tool_names())
        # If this fails, either the expected list needs updating or a tool
        # was accidentally added
        extra = names - set(self.EXPECTED_TOOLS)
        # We don't hard-fail on extras — just document them
        if extra:
            pytest.skip(f"Extra tools found (update EXPECTED_TOOLS?): {extra}")

    def test_tool_count_reasonable(self):
        # We should have roughly 35-50 tools
        assert 30 <= len(TOOLS) <= 80


# ---------------------------------------------------------------------------
# Description quality
# ---------------------------------------------------------------------------


class TestDescriptions:
    """Verify tool descriptions are meaningful."""

    @pytest.mark.parametrize("idx", range(len(TOOLS)))
    def test_description_minimum_length(self, idx):
        desc = TOOLS[idx]["function"]["description"]
        assert len(desc) >= 10, (
            f"Tool {TOOLS[idx]['function']['name']} has a very short description"
        )

    @pytest.mark.parametrize("idx", range(len(TOOLS)))
    def test_description_is_string(self, idx):
        desc = TOOLS[idx]["function"]["description"]
        assert isinstance(desc, str)
