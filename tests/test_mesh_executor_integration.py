"""Integration tests for the task executor with real backends."""
from unittest.mock import MagicMock, patch

import pytest

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.executor import TaskExecutor
from core.mesh.node import NodeCapabilities


@pytest.fixture
def executor():
    ex = TaskExecutor(
        node_id="test-node",
        bus=EventBus(),
        capabilities=NodeCapabilities(can_execute_desktop=True, can_reason=True),
        llm_config={"provider": "openai", "api_key": "test-key", "model": "gpt-4o"},
    )
    ex.start()
    yield ex
    ex.stop()


class TestExecutorIntegration:
    @pytest.mark.asyncio
    async def test_exec_action_integration(self, executor):
        """Action task calls ActionExecutor.execute_sync."""
        with patch("core.mesh.executor.ActionExecutor") as MockAE:
            mock_instance = MagicMock()
            mock_instance.execute_sync.return_value = {"success": True, "output": "clicked"}
            MockAE.return_value = mock_instance

            # Reset cached instance so lazy-init creates a new (mocked) one
            executor._executor = None

            result = await executor._exec_action({
                "task_id": "t1",
                "params": {"action": "click", "action_params": {"x": 100, "y": 200}},
            })
            assert result["success"] is True
            mock_instance.execute_sync.assert_called_once_with({"action": "click", "x": 100, "y": 200})

    @pytest.mark.asyncio
    async def test_exec_llm_integration(self, executor):
        """LLM task calls LLMClient.chat."""
        with patch("core.mesh.executor.LLMClient") as MockLLM:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = "The answer is 42."
            MockLLM.return_value = mock_instance

            # Reset cached instance so lazy-init creates a new (mocked) one
            executor._llm = None

            result = await executor._exec_llm({
                "task_id": "t1",
                "goal": "What is the meaning of life?",
                "params": {},
            })
            assert result["response"] == "The answer is 42."
            mock_instance.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_llm_uses_config_defaults(self, executor):
        """LLM task falls back to llm_config for provider/model."""
        with patch("core.mesh.executor.LLMClient") as MockLLM:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = "response"
            MockLLM.return_value = mock_instance

            # Reset cached instance so lazy-init creates a new (mocked) one
            executor._llm = None

            await executor._exec_llm({
                "task_id": "t1",
                "goal": "test prompt",
                "params": {},
            })
            call_kwargs = mock_instance.chat.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"
            assert call_kwargs["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_action_task_end_to_end(self, executor):
        """Action task assignment -> execution -> TASK_COMPLETED."""
        bus = executor.bus
        completed = []
        bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

        with patch("core.mesh.executor.ActionExecutor") as MockAE:
            mock_instance = MagicMock()
            mock_instance.execute_sync.return_value = {"success": True}
            MockAE.return_value = mock_instance

            # Reset cached instance so lazy-init creates a new (mocked) one
            executor._executor = None

            await bus.publish(FleetEvent.TASK_ASSIGNED, {
                "task_id": "t1",
                "plan_id": "p1",
                "node_id": "test-node",
                "task_type": "action",
                "goal": "",
                "params": {"action": "screenshot", "action_params": {}},
            })

        import asyncio
        for _ in range(50):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert completed[0]["data"]["result"]["success"] is True
