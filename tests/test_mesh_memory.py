"""Tests for Neuralis-backed cross-session memory."""
import json
from unittest.mock import MagicMock, patch

from core.mesh.memory import NeuralisMemory
from core.mesh.task_graph import Task, TaskGraph, TaskStatus


class TestNeuralisMemory:
    def test_construct_disabled(self):
        mem = NeuralisMemory(enabled=False)
        assert mem.enabled is False
        assert mem._brain is None

    def test_construct_enabled(self):
        with patch("core.mesh.memory.BrainClient"):
            mem = NeuralisMemory(enabled=True)
            assert mem.enabled is True
            assert mem._brain is not None

    def test_store_checkpoint_disabled(self):
        mem = NeuralisMemory(enabled=False)
        result = mem.store_checkpoint("p1", "test", TaskGraph())
        assert result is False

    def test_store_checkpoint(self):
        with patch("core.mesh.memory.BrainClient") as MockBrain:
            mock_brain = MagicMock()
            MockBrain.return_value = mock_brain

            mem = NeuralisMemory(enabled=True)
            graph = TaskGraph()
            graph.add_task(Task(id="t1", type="shell", goal="echo test", status=TaskStatus.COMPLETED))

            result = mem.store_checkpoint("p1", "test plan", graph)
            assert result is True
            mock_brain.think.assert_called_once()
            call_kwargs = mock_brain.think.call_args.kwargs
            assert "orchestrator-checkpoint:p1" in call_kwargs["topic"]
            content = json.loads(call_kwargs["content"])
            assert content["plan_id"] == "p1"
            assert len(content["tasks"]) == 1

    def test_load_checkpoint(self):
        with patch("core.mesh.memory.BrainClient") as MockBrain:
            mock_brain = MagicMock()
            mock_brain.search.return_value = [
                {
                    "topic": "orchestrator-checkpoint:p1",
                    "content": json.dumps({
                        "plan_id": "p1",
                        "tasks": [{"id": "t1", "status": "completed"}],
                        "is_complete": False,
                    }),
                }
            ]
            MockBrain.return_value = mock_brain

            mem = NeuralisMemory(enabled=True)
            result = mem.load_checkpoint("p1")
            assert result is not None
            assert result["plan_id"] == "p1"
            assert result["is_complete"] is False

    def test_load_checkpoint_not_found(self):
        with patch("core.mesh.memory.BrainClient") as MockBrain:
            mock_brain = MagicMock()
            mock_brain.search.return_value = []
            MockBrain.return_value = mock_brain

            mem = NeuralisMemory(enabled=True)
            result = mem.load_checkpoint("nonexistent")
            assert result is None

    def test_find_incomplete_plans(self):
        with patch("core.mesh.memory.BrainClient") as MockBrain:
            mock_brain = MagicMock()
            mock_brain.search.return_value = [
                {
                    "topic": "orchestrator-checkpoint:p1",
                    "content": json.dumps({"plan_id": "p1", "is_complete": False}),
                },
                {
                    "topic": "orchestrator-checkpoint:p2",
                    "content": json.dumps({"plan_id": "p2", "is_complete": True}),
                },
            ]
            MockBrain.return_value = mock_brain

            mem = NeuralisMemory(enabled=True)
            incomplete = mem.find_incomplete_plans()
            assert len(incomplete) == 1
            assert incomplete[0]["plan_id"] == "p1"

    def test_store_event_disabled(self):
        mem = NeuralisMemory(enabled=False)
        assert mem.store_event("test", {}) is False

    def test_store_event(self):
        with patch("core.mesh.memory.BrainClient") as MockBrain:
            mock_brain = MagicMock()
            MockBrain.return_value = mock_brain

            mem = NeuralisMemory(enabled=True)
            result = mem.store_event("node_joined", {"node_id": "n1"})
            assert result is True
            mock_brain.think.assert_called_once()
