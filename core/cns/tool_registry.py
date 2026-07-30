"""CNS Tool Registry — bind external functions as callable tools.

The tool registry lets the CNS discover, invoke, and track external
functions (shell commands, API calls, desktop actions, etc.) as first-class
tools. It supports both sync and async callables and provides a decorator
for convenient registration.

Classes:
    ToolResult  — Outcome of a tool invocation (success, output, error)
    ToolCall    — Record of a single tool invocation (name, args, result)
    ToolRegistry — Registry for registering, listing, and calling tools
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Outcome of a tool invocation.

    Attributes:
        success: Whether the tool completed without error.
        output: The tool's return value (as a string).
        error: Error message if the tool failed, else None.
    """
    success: bool
    output: str
    error: str | None = None


@dataclass
class ToolCall:
    """Record of a single tool invocation.

    Attributes:
        name: The tool name that was called.
        args: The keyword arguments passed to the tool.
        result: The ToolResult of the invocation.
        call_id: A unique identifier for this call.
        timestamp: ISO-8601 timestamp of when the call was made.
    """
    name: str
    args: dict[str, Any]
    result: ToolResult
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ToolRegistry:
    """Registry for binding external functions as callable tools.

    Tools are registered by name with an optional description. The registry
    supports both synchronous and asynchronous callables. Invocations are
    recorded as ToolCall instances for later inspection.

    Example:
        registry = ToolRegistry()

        @registry.tool("greet", "Greet a user")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        call = registry.call("greet", name="World")
        assert call.result.success
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._descriptions: dict[str, str] = {}
        self._history: list[ToolCall] = []

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        description: str = "",
    ) -> None:
        """Register a function as a named tool.

        Args:
            name: The tool name used for lookup and invocation.
            fn: The callable (sync or async) to register.
            description: Human-readable description of the tool.

        Raises:
            ValueError: If a tool with the given name is already registered.
        """
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = fn
        self._descriptions[name] = description
        logger.debug("Registered tool '%s'", name)

    def get(self, name: str) -> Callable[..., Any]:
        """Retrieve a registered tool by name.

        Args:
            name: The tool name to look up.

        Returns:
            The registered callable.

        Raises:
            KeyError: If no tool with the given name exists.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._tools[name]

    def list_tools(self) -> list[dict[str, str]]:
        """List all registered tools with their descriptions.

        Returns:
            A list of dicts with 'name' and 'description' keys.
        """
        return [
            {"name": name, "description": self._descriptions.get(name, "")}
            for name in sorted(self._tools)
        ]

    def tool(
        self,
        name: str,
        description: str = "",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering a function as a tool.

        Args:
            name: The tool name.
            description: Human-readable description.

        Returns:
            A decorator that registers the function.

        Example:
            @registry.tool("add", "Add two numbers")
            def add(a: int, b: int) -> int:
                return a + b
        """
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(name, fn, description)
            return fn
        return decorator

    def call(self, name: str, **kwargs: Any) -> ToolCall:
        """Invoke a registered tool by name.

        Supports both sync and async tools. Async tools are awaited
        automatically. The invocation is recorded in the history.

        Args:
            name: The tool name to call.
            **kwargs: Keyword arguments to pass to the tool.

        Returns:
            A ToolCall record with the result.

        Raises:
            KeyError: If the tool is not registered.
        """
        fn = self.get(name)
        try:
            if inspect.iscoroutinefunction(fn):
                result_obj = asyncio.run(self._async_call(fn, **kwargs))
            else:
                output = fn(**kwargs)
                result_obj = ToolResult(success=True, output=str(output))
        except Exception as e:
            logger.warning("Tool '%s' failed: %s", name, e)
            result_obj = ToolResult(success=False, output="", error=str(e))

        tc = ToolCall(name=name, args=kwargs, result=result_obj)
        self._history.append(tc)
        return tc

    async def acall(self, name: str, **kwargs: Any) -> ToolCall:
        """Async version of call() — invoke a registered tool.

        Args:
            name: The tool name to call.
            **kwargs: Keyword arguments to pass to the tool.

        Returns:
            A ToolCall record with the result.
        """
        fn = self.get(name)
        try:
            result_obj = await self._async_call(fn, **kwargs)
        except Exception as e:
            logger.warning("Tool '%s' failed: %s", name, e)
            result_obj = ToolResult(success=False, output="", error=str(e))

        tc = ToolCall(name=name, args=kwargs, result=result_obj)
        self._history.append(tc)
        return tc

    async def _async_call(
        self,
        fn: Callable[..., Any],
        **kwargs: Any,
    ) -> ToolResult:
        """Invoke a callable, awaiting it if it is async."""
        if inspect.iscoroutinefunction(fn):
            output = await fn(**kwargs)
        else:
            output = fn(**kwargs)
        return ToolResult(success=True, output=str(output))

    @property
    def history(self) -> list[ToolCall]:
        """Return the full history of tool calls."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear the call history."""
        self._history.clear()

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: The tool name to remove.

        Raises:
            KeyError: If the tool is not registered.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        del self._tools[name]
        del self._descriptions[name]

    def __contains__(self, name: str) -> bool:
        """True if a tool with the given name is registered."""
        return name in self._tools

    def __len__(self) -> int:
        """Number of registered tools."""
        return len(self._tools)
