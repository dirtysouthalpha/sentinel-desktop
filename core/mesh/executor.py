"""Task executor for the fleet mesh."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.node import NodeCapabilities

logger = logging.getLogger(__name__)

# Type alias
EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class TaskExecutor:
    """Executes tasks assigned to this node via the mesh event bus."""

    def __init__(
        self,
        node_id: str,
        bus: EventBus,
        capabilities: NodeCapabilities,
    ) -> None:
        self.node_id = node_id
        self.bus = bus
        self.capabilities = capabilities
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
            "shell": self._exec_shell,
            "python": self._exec_python,
            "action": self._exec_action,
            "llm": self._exec_llm,
        }
        self._running = False

    def start(self) -> None:
        """Start listening for task assignments."""
        self._running = True
        self.bus.subscribe(FleetEvent.TASK_ASSIGNED, self._on_task_assigned)
        logger.info("Task executor started for node %s", self.node_id)

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        self.bus.unsubscribe(FleetEvent.TASK_ASSIGNED, self._on_task_assigned)

    async def _on_task_assigned(self, envelope: dict[str, Any]) -> None:
        """Handle task assignment."""
        if not self._running:
            return
        data = envelope.get("data", {})
        assigned_node = data.get("node_id", "")
        if assigned_node != self.node_id:
            return  # Not for us

        task_id = data.get("task_id", "")
        plan_id = data.get("plan_id", "")
        task_type = data.get("task_type", "shell")
        task_goal = data.get("goal", "")
        task_params = data.get("params", {})

        logger.info("Executing task %s (type=%s): %s", task_id, task_type, task_goal)

        # Publish TASK_RUNNING
        await self.bus.publish(FleetEvent.TASK_RUNNING, {
            "task_id": task_id,
            "plan_id": plan_id,
            "node_id": self.node_id,
        })

        # Execute
        try:
            handler = self._handlers.get(task_type, self._exec_shell)
            result = await handler({
                "task_id": task_id,
                "goal": task_goal,
                "params": task_params,
            })
            # Success
            await self.bus.publish(FleetEvent.TASK_COMPLETED, {
                "task_id": task_id,
                "plan_id": plan_id,
                "node_id": self.node_id,
                "result": result,
            })
        except Exception as e:
            logger.exception("Task %s execution failed", task_id)
            await self.bus.publish(FleetEvent.TASK_FAILED, {
                "task_id": task_id,
                "plan_id": plan_id,
                "node_id": self.node_id,
                "error": str(e),
            })

    async def _exec_shell(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a shell command."""
        command = task.get("params", {}).get("command", task.get("goal", ""))
        if not command:
            raise ValueError("No command specified for shell task")

        timeout = task.get("params", {}).get("timeout", 60)
        cwd = task.get("params", {}).get("cwd", None)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed (exit {proc.returncode}): {stderr.decode().strip()}"
            )
        return {
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
            "exit_code": proc.returncode,
        }

    async def _exec_python(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a Python function."""
        module_path = task.get("params", {}).get("module", "")
        function_name = task.get("params", {}).get("function", "")
        args = task.get("params", {}).get("args", [])
        kwargs = task.get("params", {}).get("kwargs", {})

        if not module_path or not function_name:
            raise ValueError("Python task requires 'module' and 'function' params")

        import importlib
        mod = importlib.import_module(module_path)
        func = getattr(mod, function_name)
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return {"return_value": repr(result)}

    async def _exec_action(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a Sentinel Desktop action."""
        action_name = task.get("params", {}).get("action", "")
        action_params = task.get("params", {}).get("action_params", {})
        if not action_name:
            raise ValueError("Action task requires 'action' param")
        # Placeholder — would integrate with core.actions
        return {"action": action_name, "status": "executed", "params": action_params}

    async def _exec_llm(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute an LLM call."""
        prompt = task.get("goal", "")
        model = task.get("params", {}).get("model", "default")
        if not prompt:
            raise ValueError("LLM task requires a goal/prompt")
        # Placeholder — would integrate with core.engine
        return {"model": model, "prompt": prompt, "response": "LLM response placeholder"}
