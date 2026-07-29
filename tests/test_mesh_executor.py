"""Tests for the task executor."""
import asyncio

import pytest

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.executor import TaskExecutor
from core.mesh.node import NodeCapabilities


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def capabilities():
    return NodeCapabilities(
        can_orchestrate=False,
        can_execute_desktop=True,
        can_reason=True,
        can_remember=True,
    )


@pytest.fixture
def executor(bus, capabilities):
    ex = TaskExecutor(node_id="test-node", bus=bus, capabilities=capabilities)
    ex.start()
    yield ex
    ex.stop()


class TestTaskExecutor:
    def test_construct(self, bus, capabilities):
        ex = TaskExecutor(node_id="n1", bus=bus, capabilities=capabilities)
        assert ex.node_id == "n1"
        assert not ex._running

    @pytest.mark.asyncio
    async def test_exec_shell_command(self, executor):
        """Shell task executes a command."""
        result = await executor._exec_shell({
            "task_id": "t1",
            "goal": "echo hello",
            "params": {"command": "echo hello world"},
        })
        assert result["stdout"] == "hello world"
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exec_shell_failure(self, executor):
        """Shell task raises on non-zero exit."""
        with pytest.raises(RuntimeError, match="exit"):
            await executor._exec_shell({
                "task_id": "t1",
                "goal": "",
                "params": {"command": "exit 1"},
            })

    @pytest.mark.asyncio
    async def test_exec_shell_timeout(self, executor):
        """Shell task times out."""
        with pytest.raises(asyncio.TimeoutError):
            await executor._exec_shell({
                "task_id": "t1",
                "goal": "",
                "params": {"command": "sleep 10", "timeout": 1},
            })

    @pytest.mark.asyncio
    async def test_task_assignment_triggers_execution(self, executor, bus):
        """TASK_ASSIGNED event triggers execution."""
        completed = []
        bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

        await bus.publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "t1",
            "plan_id": "p1",
            "node_id": "test-node",
            "task_type": "shell",
            "goal": "echo test",
            "params": {"command": "echo test output"},
        })

        # Wait for execution
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert completed[0]["data"]["task_id"] == "t1"
        assert completed[0]["data"]["result"]["stdout"] == "test output"

    @pytest.mark.asyncio
    async def test_task_for_other_node_ignored(self, executor, bus):
        """Tasks assigned to other nodes are ignored."""
        completed = []
        bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

        await bus.publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "t1",
            "plan_id": "p1",
            "node_id": "other-node",
            "task_type": "shell",
            "goal": "echo test",
            "params": {"command": "echo test"},
        })

        await asyncio.sleep(0.3)
        assert len(completed) == 0

    @pytest.mark.asyncio
    async def test_execution_failure_publishes_task_failed(self, executor, bus):
        """Failed execution publishes TASK_FAILED."""
        failed = []
        bus.subscribe(FleetEvent.TASK_FAILED, lambda env: failed.append(env))

        await bus.publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "t1",
            "plan_id": "p1",
            "node_id": "test-node",
            "task_type": "shell",
            "goal": "",
            "params": {"command": "exit 42"},
        })

        for _ in range(100):
            if failed:
                break
            await asyncio.sleep(0.05)

        assert len(failed) == 1
        assert failed[0]["data"]["task_id"] == "t1"
        assert "exit 42" in failed[0]["data"]["error"] or "42" in failed[0]["data"]["error"]

    @pytest.mark.asyncio
    async def test_exec_python(self, executor):
        """Python task executes a function."""
        result = await executor._exec_python({
            "task_id": "t1",
            "goal": "",
            "params": {
                "module": "os.path",
                "function": "join",
                "args": ["/tmp", "test.txt"],
            },
        })
        assert "/tmp" in result["return_value"]
        assert "test.txt" in result["return_value"]
