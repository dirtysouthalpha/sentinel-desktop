"""Tests for v13.0 Process & Service Control — schemas, executor, tools."""

from __future__ import annotations

import os

import pytest

from core.action_schemas import (
    ACTION_MODELS,
    GetEnvAction,
    ServiceControlAction,
    SetEnvAction,
    SetPriorityAction,
)
from core.tool_schemas import TOOLS

# ── Schema tests ─────────────────────────────────────────────────────


class TestProcessSchemas:
    def test_all_registered(self):
        for action in ["set_priority", "get_env", "set_env", "service_control"]:
            assert action in ACTION_MODELS

    def test_set_priority_valid(self):
        a = SetPriorityAction(action="set_priority", pid=1234, priority="high")
        assert a.priority == "high"
        assert a.pid == 1234

    def test_get_env_valid(self):
        a = GetEnvAction(action="get_env", name="PATH")
        assert a.name == "PATH"

    def test_set_env_valid(self):
        a = SetEnvAction(action="set_env", name="FOO", value="bar")
        assert a.permanent is False

    def test_service_control_valid(self):
        a = ServiceControlAction(
            action="service_control",
            name="Spooler",
            control_action="query",
        )
        assert a.control_action == "query"


# ── Executor tests ───────────────────────────────────────────────────


class TestProcessExecutor:
    def test_dispatch_entries(self):
        from core.action_executor import ActionExecutor
        for action in ["set_priority", "get_env", "set_env", "service_control"]:
            assert action in ActionExecutor._dispatch_table

    def test_get_env_executor(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        result = executor._get_env(name="PATH")
        assert result["success"] is True
        assert len(result["output"]) > 0

    def test_get_env_missing(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        result = executor._get_env(name="SENTINEL_TEST_NONEXISTENT_12345")
        assert result["success"] is False

    def test_set_and_get_env(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        result = executor._set_env(name="SENTINEL_TEST_VAR", value="test123")
        assert result["success"] is True
        # Verify it was set
        verify = executor._get_env(name="SENTINEL_TEST_VAR")
        assert verify["success"] is True
        assert verify["output"] == "test123"
        # Cleanup
        os.environ.pop("SENTINEL_TEST_VAR", None)

    def test_service_control_query(self):
        """Query a known service that should exist on Windows."""
        import sys
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        # EventLog should exist on all Windows
        result = executor._service_control(
            name="EventLog", control_action="query",
        )
        # Should succeed or fail gracefully
        assert isinstance(result, dict)
        assert "success" in result


# ── Tool schema tests ────────────────────────────────────────────────


class TestProcessToolSchemas:
    def test_all_tools_exist(self):
        names = [t["function"]["name"] for t in TOOLS]
        for tool in ["set_priority", "get_env", "set_env", "service_control"]:
            assert tool in names

    def test_service_control_params(self):
        tool = next(
            t for t in TOOLS
            if t["function"]["name"] == "service_control"
        )
        props = tool["function"]["parameters"]["properties"]
        assert "name" in props
        assert "control_action" in props
        assert props["control_action"]["type"] == "string"

    def test_set_env_params(self):
        tool = next(
            t for t in TOOLS
            if t["function"]["name"] == "set_env"
        )
        props = tool["function"]["parameters"]["properties"]
        assert "name" in props
        assert "value" in props
        assert "permanent" in props
