"""Tests for memory and conductor action schemas and executor dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.action_schemas import ACTION_MODELS, validate_action

# ---------------------------------------------------------------------------
# Memory action schemas
# ---------------------------------------------------------------------------


class TestMemoryActionSchemas:
    def test_memory_store_valid(self):
        out, errs = validate_action(
            {
                "action": "memory_store",
                "key": "firewall_ip",
                "value": "192.168.1.1",
            }
        )
        assert errs == []
        assert out["key"] == "firewall_ip"
        assert out["category"] == ""  # default

    def test_memory_store_with_category_and_tags(self):
        out, errs = validate_action(
            {
                "action": "memory_store",
                "key": "fw_creds",
                "value": "admin/password",
                "category": "credentials",
                "tags": ["sonicwall", "default"],
            }
        )
        assert errs == []
        assert out["category"] == "credentials"
        assert out["tags"] == ["sonicwall", "default"]

    def test_memory_store_missing_key(self):
        _, errs = validate_action({"action": "memory_store", "value": "x"})
        assert errs

    def test_memory_store_missing_value(self):
        _, errs = validate_action({"action": "memory_store", "key": "x"})
        assert errs

    def test_memory_recall_valid(self):
        out, errs = validate_action(
            {
                "action": "memory_recall",
                "key": "firewall_ip",
            }
        )
        assert errs == []
        assert out["key"] == "firewall_ip"

    def test_memory_recall_missing_key(self):
        _, errs = validate_action({"action": "memory_recall"})
        assert errs

    def test_memory_search_valid(self):
        out, errs = validate_action(
            {
                "action": "memory_search",
                "query": "firewall",
            }
        )
        assert errs == []
        assert out["limit"] == 10  # default

    def test_memory_search_with_limit(self):
        out, errs = validate_action(
            {
                "action": "memory_search",
                "query": "test",
                "limit": 50,
            }
        )
        assert errs == []
        assert out["limit"] == 50

    def test_memory_search_limit_too_high(self):
        _, errs = validate_action(
            {
                "action": "memory_search",
                "query": "test",
                "limit": 200,
            }
        )
        assert errs

    def test_memory_search_limit_zero(self):
        _, errs = validate_action(
            {
                "action": "memory_search",
                "query": "test",
                "limit": 0,
            }
        )
        assert errs

    def test_memory_forget_valid(self):
        out, errs = validate_action(
            {
                "action": "memory_forget",
                "key": "firewall_ip",
            }
        )
        assert errs == []

    def test_memory_forget_missing_key(self):
        _, errs = validate_action({"action": "memory_forget"})
        assert errs


# ---------------------------------------------------------------------------
# Conductor action schemas
# ---------------------------------------------------------------------------


class TestConductorActionSchemas:
    def test_conductor_run_valid(self):
        out, errs = validate_action(
            {
                "action": "conductor_run",
                "goal": "Check all firewalls and generate report",
            }
        )
        assert errs == []
        assert out["timeout"] == 120.0  # default

    def test_conductor_run_with_timeout(self):
        out, errs = validate_action(
            {
                "action": "conductor_run",
                "goal": "Do complex thing",
                "timeout": 300.0,
            }
        )
        assert errs == []
        assert out["timeout"] == 300.0

    def test_conductor_run_missing_goal(self):
        _, errs = validate_action({"action": "conductor_run"})
        assert errs

    def test_conductor_run_timeout_too_low(self):
        _, errs = validate_action(
            {
                "action": "conductor_run",
                "goal": "test",
                "timeout": 5.0,
            }
        )
        assert errs

    def test_conductor_run_timeout_too_high(self):
        _, errs = validate_action(
            {
                "action": "conductor_run",
                "goal": "test",
                "timeout": 9999.0,
            }
        )
        assert errs


# ---------------------------------------------------------------------------
# Parametrized: all new actions are in the registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["memory_store", "memory_recall", "memory_search", "memory_forget", "conductor_run"],
)
def test_new_actions_are_modeled(name):
    assert name in ACTION_MODELS


# ---------------------------------------------------------------------------
# Executor dispatch: Memory actions
# ---------------------------------------------------------------------------


class TestExecutorMemoryDispatch:
    """Test that memory actions dispatch through the executor."""

    def _make_executor(self):
        from core.action_executor import ActionExecutor

        return ActionExecutor()

    def test_memory_store_dispatches(self, tmp_path):
        mock_mem = MagicMock()
        mock_mem.store.return_value = 1
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_store",
                    "key": "fw_ip",
                    "value": "192.168.1.1",
                    "category": "network",
                    "tags": ["sonicwall"],
                }
            )
            assert result["success"] is True
            assert result["key"] == "fw_ip"
            mock_mem.store.assert_called_once_with(
                key="fw_ip",
                value="192.168.1.1",
                category="network",
                tags=["sonicwall"],
            )

    def test_memory_store_error(self):
        mock_mem = MagicMock()
        mock_mem.store.side_effect = Exception("DB locked")
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_store",
                    "key": "fw_ip",
                    "value": "192.168.1.1",
                }
            )
            assert result["success"] is False
            assert "DB locked" in result["output"]

    def test_memory_recall_found(self):
        mock_mem = MagicMock()
        mock_mem.recall.return_value = {
            "key": "fw_ip",
            "value": "192.168.1.1",
            "category": "network",
        }
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_recall",
                    "key": "fw_ip",
                }
            )
            assert result["success"] is True
            assert result["fact"]["value"] == "192.168.1.1"

    def test_memory_recall_not_found(self):
        mock_mem = MagicMock()
        mock_mem.recall.return_value = None
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_recall",
                    "key": "nonexistent",
                }
            )
            assert result["success"] is False
            assert "No fact found" in result["output"]

    def test_memory_recall_error(self):
        mock_mem = MagicMock()
        mock_mem.recall.side_effect = Exception("corrupt")
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_recall",
                    "key": "fw_ip",
                }
            )
            assert result["success"] is False
            assert "corrupt" in result["output"]

    def test_memory_search_found(self):
        mock_mem = MagicMock()
        mock_mem.query.return_value = [
            {"key": "fw_ip", "value": "192.168.1.1"},
            {"key": "fw_ip2", "value": "10.0.0.1"},
        ]
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_search",
                    "query": "firewall",
                    "limit": 5,
                }
            )
            assert result["success"] is True
            assert result["count"] == 2
            mock_mem.query.assert_called_once_with("firewall", limit=5)

    def test_memory_search_empty(self):
        mock_mem = MagicMock()
        mock_mem.query.return_value = []
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_search",
                    "query": "nonexistent",
                }
            )
            assert result["success"] is True
            assert result["count"] == 0

    def test_memory_forget_success(self):
        mock_mem = MagicMock()
        mock_mem.delete.return_value = True
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_forget",
                    "key": "fw_ip",
                }
            )
            assert result["success"] is True

    def test_memory_forget_not_found(self):
        mock_mem = MagicMock()
        mock_mem.delete.return_value = False
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_forget",
                    "key": "nonexistent",
                }
            )
            assert result["success"] is False
            assert "not found" in result["output"]

    def test_memory_forget_error(self):
        mock_mem = MagicMock()
        mock_mem.delete.side_effect = Exception("io error")
        with patch(
            "core.action_executor.ActionExecutor._get_semantic_memory", return_value=mock_mem
        ):
            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "memory_forget",
                    "key": "fw_ip",
                }
            )
            assert result["success"] is False


# ---------------------------------------------------------------------------
# Executor dispatch: Conductor action
# ---------------------------------------------------------------------------


class TestExecutorConductorDispatch:
    """Test that conductor_run dispatches through the executor."""

    def _make_executor(self):
        from core.action_executor import ActionExecutor

        return ActionExecutor()

    def test_conductor_run_dispatches(self):
        mock_result = {
            "goal": "test goal",
            "status": "success",
            "success": True,
            "summary": "All done",
            "tasks_total": 2,
            "tasks_succeeded": 2,
            "tasks_failed": 0,
            "results": [],
        }
        with patch("core.conductor.coordinator.Conductor") as MockConductor:
            mock_instance = MagicMock()

            async def fake_run(goal, timeout=120.0):
                return mock_result

            mock_instance.run = fake_run
            MockConductor.return_value = mock_instance

            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "conductor_run",
                    "goal": "Check firewalls",
                    "timeout": 60.0,
                }
            )
            assert result["success"] is True
            assert result["tasks_total"] == 2

    def test_conductor_run_error(self):
        with patch("core.conductor.coordinator.Conductor") as MockConductor:
            mock_instance = MagicMock()

            async def failing_run(goal, timeout=120.0):
                raise RuntimeError("Decomposition failed")

            mock_instance.run = failing_run
            MockConductor.return_value = mock_instance

            executor = self._make_executor()
            result = executor.execute_sync(
                {
                    "action": "conductor_run",
                    "goal": "Test goal",
                }
            )
            assert result["success"] is False
            assert "failed" in result["status"]


# ---------------------------------------------------------------------------
# Integration: Semantic memory round-trip through executor
# ---------------------------------------------------------------------------


class TestMemoryIntegration:
    """End-to-end: store → recall → search → forget through executor."""

    def _make_executor(self, tmp_path):
        from core.action_executor import ActionExecutor
        from core.memory.semantic import SemanticMemory

        executor = ActionExecutor()
        executor._semantic_memory = SemanticMemory(path=tmp_path / "test_semantic.db")
        return executor

    def test_store_recall_forget_cycle(self, tmp_path):
        executor = self._make_executor(tmp_path)

        # Store
        result = executor.execute_sync(
            {
                "action": "memory_store",
                "key": "test_fw",
                "value": "192.168.1.1",
                "category": "network",
            }
        )
        assert result["success"] is True

        # Recall
        result = executor.execute_sync(
            {
                "action": "memory_recall",
                "key": "test_fw",
            }
        )
        assert result["success"] is True
        assert result["fact"]["value"] == "192.168.1.1"

        # Search
        result = executor.execute_sync(
            {
                "action": "memory_search",
                "query": "192.168",
            }
        )
        assert result["success"] is True
        assert result["count"] >= 1

        # Forget
        result = executor.execute_sync(
            {
                "action": "memory_forget",
                "key": "test_fw",
            }
        )
        assert result["success"] is True

        # Verify gone
        result = executor.execute_sync(
            {
                "action": "memory_recall",
                "key": "test_fw",
            }
        )
        assert result["success"] is False

    def test_store_with_tags_searchable(self, tmp_path):
        executor = self._make_executor(tmp_path)

        executor.execute_sync(
            {
                "action": "memory_store",
                "key": "sw_default",
                "value": "admin/password",
                "category": "credentials",
                "tags": ["sonicwall", "default"],
            }
        )

        result = executor.execute_sync(
            {
                "action": "memory_search",
                "query": "sonicwall",
            }
        )
        assert result["success"] is True
        assert result["count"] >= 1

    def test_store_updates_existing(self, tmp_path):
        executor = self._make_executor(tmp_path)

        executor.execute_sync(
            {
                "action": "memory_store",
                "key": "fw_ip",
                "value": "192.168.1.1",
            }
        )

        executor.execute_sync(
            {
                "action": "memory_store",
                "key": "fw_ip",
                "value": "10.0.0.1",
            }
        )

        result = executor.execute_sync(
            {
                "action": "memory_recall",
                "key": "fw_ip",
            }
        )
        assert result["fact"]["value"] == "10.0.0.1"


# ---------------------------------------------------------------------------
# Tool schema coverage
# ---------------------------------------------------------------------------


class TestToolSchemas:
    """Verify new actions have tool schemas for LLM tool calling."""

    def test_memory_tools_in_tools_list(self):
        from core.tool_schemas import TOOLS

        tool_names = [t["function"]["name"] for t in TOOLS]
        assert "memory_store" in tool_names
        assert "memory_recall" in tool_names
        assert "memory_search" in tool_names
        assert "memory_forget" in tool_names

    def test_conductor_tools_in_tools_list(self):
        from core.tool_schemas import TOOLS

        tool_names = [t["function"]["name"] for t in TOOLS]
        assert "conductor_run" in tool_names

    def test_memory_store_tool_has_required_fields(self):
        from core.tool_schemas import TOOLS

        tool = next(t for t in TOOLS if t["function"]["name"] == "memory_store")
        assert "key" in tool["function"]["parameters"]["properties"]
        assert "value" in tool["function"]["parameters"]["properties"]
        assert "key" in tool["function"]["parameters"]["required"]
        assert "value" in tool["function"]["parameters"]["required"]

    def test_conductor_run_tool_has_required_fields(self):
        from core.tool_schemas import TOOLS

        tool = next(t for t in TOOLS if t["function"]["name"] == "conductor_run")
        assert "goal" in tool["function"]["parameters"]["properties"]
        assert "goal" in tool["function"]["parameters"]["required"]
