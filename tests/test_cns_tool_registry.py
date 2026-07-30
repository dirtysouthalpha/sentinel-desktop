"""Tests for the CNS 2.0 Tool Registry."""
import asyncio

import pytest

from core.cns.tool_registry import ToolCall, ToolRegistry, ToolResult


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(success=True, output="hello")
        assert r.success is True
        assert r.output == "hello"
        assert r.error is None

    def test_failure_result(self):
        r = ToolResult(success=False, output="", error="boom")
        assert r.success is False
        assert r.error == "boom"


class TestToolCall:
    def test_tool_call_creation(self):
        result = ToolResult(success=True, output="ok")
        tc = ToolCall(name="echo", args={"text": "hi"}, result=result)
        assert tc.name == "echo"
        assert tc.args == {"text": "hi"}
        assert tc.result == result
        assert len(tc.call_id) == 8
        assert tc.timestamp  # non-empty


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        reg.register("add", lambda a, b: a + b, "Add two numbers")
        fn = reg.get("add")
        assert fn(2, 3) == 5

    def test_register_duplicate_raises(self):
        reg = ToolRegistry()
        reg.register("foo", lambda: "foo")
        with pytest.raises(ValueError, match="already registered"):
            reg.register("foo", lambda: "bar")

    def test_get_missing_raises(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.get("nonexistent")

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register("a", lambda: None, "Tool A")
        reg.register("b", lambda: None, "Tool B")
        tools = reg.list_tools()
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "a" in names
        assert "b" in names

    def test_list_tools_sorted(self):
        reg = ToolRegistry()
        reg.register("z", lambda: None)
        reg.register("a", lambda: None)
        tools = reg.list_tools()
        assert tools[0]["name"] == "a"
        assert tools[1]["name"] == "z"

    def test_decorator_registers(self):
        reg = ToolRegistry()

        @reg.tool("greet", "Greet someone")
        def greet(user: str) -> str:
            return f"Hello, {user}!"

        assert "greet" in reg
        call = reg.call("greet", user="World")
        assert call.result.success
        assert call.result.output == "Hello, World!"

    def test_call_sync_tool(self):
        reg = ToolRegistry()
        reg.register("double", lambda x: x * 2)
        tc = reg.call("double", x=5)
        assert tc.result.success
        assert tc.result.output == "10"

    def test_call_async_tool(self):
        reg = ToolRegistry()

        async def async_add(a, b):
            return a + b

        reg.register("async_add", async_add)
        tc = reg.call("async_add", a=3, b=4)
        assert tc.result.success
        assert tc.result.output == "7"

    @pytest.mark.asyncio
    async def test_acall_async_tool(self):
        reg = ToolRegistry()

        async def async_mul(a, b):
            return a * b

        reg.register("async_mul", async_mul)
        tc = await reg.acall("async_mul", a=3, b=4)
        assert tc.result.success
        assert tc.result.output == "12"

    @pytest.mark.asyncio
    async def test_acall_sync_tool(self):
        reg = ToolRegistry()
        reg.register("add", lambda a, b: a + b)
        tc = await reg.acall("add", a=1, b=2)
        assert tc.result.success
        assert tc.result.output == "3"

    def test_call_failure_captured(self):
        reg = ToolRegistry()

        def bad_tool():
            raise RuntimeError("explosion")

        reg.register("bad", bad_tool)
        tc = reg.call("bad")
        assert tc.result.success is False
        assert "explosion" in tc.result.error

    def test_history_tracked(self):
        reg = ToolRegistry()
        reg.register("echo", lambda text: text)
        reg.call("echo", text="first")
        reg.call("echo", text="second")
        assert len(reg.history) == 2
        assert reg.history[0].result.output == "first"
        assert reg.history[1].result.output == "second"

    def test_clear_history(self):
        reg = ToolRegistry()
        reg.register("echo", lambda text: text)
        reg.call("echo", text="hi")
        reg.clear_history()
        assert len(reg.history) == 0

    def test_unregister(self):
        reg = ToolRegistry()
        reg.register("temp", lambda: None)
        reg.unregister("temp")
        assert "temp" not in reg

    def test_unregister_missing_raises(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nope")

    def test_contains(self):
        reg = ToolRegistry()
        reg.register("x", lambda: None)
        assert "x" in reg
        assert "y" not in reg

    def test_len(self):
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.register("a", lambda: None)
        reg.register("b", lambda: None)
        assert len(reg) == 2
