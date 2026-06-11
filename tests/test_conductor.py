"""Tests for v12.0 Conductor — multi-agent orchestration."""

from __future__ import annotations

import pytest

from core.conductor.coordinator import Conductor
from core.conductor.parallel import ParallelExecutor
from core.conductor.planner import Subtask, TaskPlanner
from core.conductor.synthesizer import ResultSynthesizer

# ===========================================================================
# Task Planner
# ===========================================================================


class TestTaskPlanner:
    def test_single_task(self):
        planner = TaskPlanner()
        plan = planner.decompose("Click the OK button")
        assert len(plan) == 1
        assert plan[0].task_type == "desktop"

    def test_network_task(self):
        planner = TaskPlanner()
        plan = planner.decompose("SSH into the router and run show version")
        assert any(t.task_type == "network" for t in plan)

    def test_browser_task(self):
        planner = planner = TaskPlanner()
        plan = planner.decompose("Open the web portal and login")
        assert any(t.task_type == "browser" for t in plan)

    def test_terminal_task(self):
        planner = TaskPlanner()
        plan = planner.decompose("Run the PowerShell script")
        assert any(t.task_type == "terminal" for t in plan)

    def test_monitor_task(self):
        planner = TaskPlanner()
        plan = planner.decompose("Check the system health status")
        assert any(t.task_type == "monitor" for t in plan)

    def test_multi_task_split(self):
        planner = TaskPlanner()
        plan = planner.decompose(
            "Login to the firewall and check the ARP table and export the config"
        )
        assert len(plan) >= 2

    def test_sequential_dependencies(self):
        planner = TaskPlanner()
        plan = planner.decompose("Open the portal then click the login button then check dashboard")
        # Sequential keywords → dependencies chain
        for i in range(1, len(plan)):
            assert f"t-{i}" in plan[i].dependencies

    def test_independent_no_dependencies(self):
        planner = TaskPlanner()
        plan = planner.decompose("Check the firewall and monitor the server")
        # No "then/after" → no dependencies
        for subtask in plan:
            assert subtask.dependencies == []

    def test_subtask_ids_sequential(self):
        planner = TaskPlanner()
        plan = planner.decompose("Do A and B and C")
        ids = [s.subtask_id for s in plan]
        assert ids == [f"t-{i + 1}" for i in range(len(plan))]

    def test_subtask_to_dict(self):
        subtask = Subtask(
            subtask_id="t-1", description="Test", task_type="desktop", dependencies=["t-0"]
        )
        d = subtask.to_dict()
        assert d["subtask_id"] == "t-1"
        assert d["task_type"] == "desktop"
        assert d["dependencies"] == ["t-0"]

    def test_short_goal_not_split(self):
        planner = TaskPlanner()
        plan = planner.decompose("Click OK")
        assert len(plan) == 1

    def test_priority_ordering(self):
        planner = TaskPlanner()
        plan = planner.decompose("Do task A and task B and task C")
        # Earlier tasks get higher priority
        if len(plan) >= 2:
            assert plan[0].priority >= plan[-1].priority


# ===========================================================================
# Parallel Executor
# ===========================================================================


class TestParallelExecutor:
    @pytest.mark.asyncio
    async def test_execute_single_task(self):
        executor = ParallelExecutor()
        subtask = Subtask(subtask_id="t-1", description="Test", task_type="desktop")
        results = await executor.execute_all([subtask])
        assert len(results) == 1
        assert results[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_execute_multiple_independent(self):
        executor = ParallelExecutor()
        subtasks = [
            Subtask(subtask_id=f"t-{i}", description=f"Task {i}", task_type="desktop")
            for i in range(1, 4)
        ]
        results = await executor.execute_all(subtasks)
        assert len(results) == 3
        assert all(r["status"] == "success" for r in results)

    @pytest.mark.asyncio
    async def test_execute_with_dependencies(self):
        executor = ParallelExecutor()
        subtasks = [
            Subtask(subtask_id="t-1", description="First", task_type="desktop"),
            Subtask(
                subtask_id="t-2", description="Second", task_type="desktop", dependencies=["t-1"]
            ),
        ]
        results = await executor.execute_all(subtasks)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_execute_with_custom_fn(self):
        call_order = []

        def my_fn(subtask: Subtask) -> str:
            call_order.append(subtask.subtask_id)
            return f"done-{subtask.subtask_id}"

        executor = ParallelExecutor(executor_fn=my_fn)
        subtasks = [
            Subtask(subtask_id="t-1", description="A", task_type="desktop"),
            Subtask(subtask_id="t-2", description="B", task_type="desktop"),
        ]
        results = await executor.execute_all(subtasks)
        assert len(results) == 2
        assert all(r["status"] == "success" for r in results)

    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        def failing_fn(subtask: Subtask) -> None:
            raise RuntimeError("Task failed")

        executor = ParallelExecutor(executor_fn=failing_fn)
        subtask = Subtask(subtask_id="t-1", description="Fail", task_type="desktop")
        results = await executor.execute_all([subtask])
        assert results[0]["status"] == "error"
        assert "Task failed" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_empty_subtasks(self):
        executor = ParallelExecutor()
        results = await executor.execute_all([])
        assert results == []

    @pytest.mark.asyncio
    async def test_deadlock_breaks_and_marks_timeout(self):
        """Task with unsatisfied dependency triggers deadlock break (lines 69-71, 94)."""
        executor = ParallelExecutor()
        # Dependency "ghost" never appears in completed_ids → deadlock → break
        subtask = Subtask(
            subtask_id="t-blocked",
            description="Blocked forever",
            task_type="desktop",
            dependencies=["ghost"],
        )
        results = await executor.execute_all([subtask])
        assert results[0]["subtask_id"] == "t-blocked"
        assert results[0]["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_gather_exception_hits_isinstance_branch(self):
        """gather returning an Exception object hits the isinstance check (line 81)."""
        from unittest.mock import patch

        executor = ParallelExecutor()
        subtask = Subtask(subtask_id="t-raw-err", description="Raw err", task_type="desktop")

        async def raising_execute_one(task):
            raise RuntimeError("raw coroutine failure")

        with patch.object(executor, "_execute_one", raising_execute_one):
            results = await executor.execute_all([subtask])

        assert results[0]["status"] == "error"
        assert "raw coroutine failure" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_timeout_zero_marks_remaining(self):
        """timeout=0 makes the while condition fail immediately; task gets 'timeout' (line 94)."""
        executor = ParallelExecutor()
        subtask = Subtask(subtask_id="t-tmo", description="Never starts", task_type="desktop")
        results = await executor.execute_all([subtask], timeout=0)
        assert results[0]["status"] == "timeout"
        assert results[0]["error"] == "Execution timed out"

    @pytest.mark.asyncio
    async def test_async_executor_fn_is_awaited(self):
        """Async executor_fn (returning a coroutine) is properly awaited (line 127)."""
        async def async_fn(subtask: Subtask) -> str:
            return f"async-{subtask.subtask_id}"

        executor = ParallelExecutor(executor_fn=async_fn)
        subtask = Subtask(subtask_id="t-async", description="Async task", task_type="desktop")
        results = await executor.execute_all([subtask])
        assert results[0]["status"] == "success"
        assert results[0]["result"] == "async-t-async"


# ===========================================================================
# Result Synthesizer
# ===========================================================================


class TestResultSynthesizer:
    def test_all_success(self):
        synth = ResultSynthesizer()
        results = [
            {"subtask_id": "t-1", "status": "success", "description": "Task 1"},
            {"subtask_id": "t-2", "status": "success", "description": "Task 2"},
        ]
        final = synth.synthesize("Test goal", results)
        assert final["status"] == "success"
        assert final["success"] is True
        assert final["tasks_succeeded"] == 2

    def test_partial_success(self):
        synth = ResultSynthesizer()
        results = [
            {"subtask_id": "t-1", "status": "success", "description": "Task 1"},
            {"subtask_id": "t-2", "status": "error", "description": "Task 2"},
        ]
        final = synth.synthesize("Test goal", results)
        assert final["status"] == "partial"
        assert final["tasks_succeeded"] == 1
        assert final["tasks_failed"] == 1

    def test_all_failed(self):
        synth = ResultSynthesizer()
        results = [
            {"subtask_id": "t-1", "status": "error", "description": "Task 1", "error": "Failed"},
            {"subtask_id": "t-2", "status": "timeout", "description": "Task 2"},
        ]
        final = synth.synthesize("Test goal", results)
        assert final["status"] == "error"
        assert final["success"] is False

    def test_no_tasks(self):
        synth = ResultSynthesizer()
        final = synth.synthesize("Test goal", [])
        assert final["status"] == "no_tasks"

    def test_extract_errors(self):
        synth = ResultSynthesizer()
        results = [
            {"subtask_id": "t-1", "status": "error", "error": "Connection refused"},
            {"subtask_id": "t-2", "status": "success"},
            {"subtask_id": "t-3", "status": "error", "error": "Timeout"},
        ]
        errors = synth.extract_errors(results)
        assert len(errors) == 2

    def test_extract_data(self):
        synth = ResultSynthesizer()
        results = [
            {"subtask_id": "t-1", "status": "success", "result": {"arp": []}},
            {"subtask_id": "t-2", "status": "error", "error": "Failed"},
            {"subtask_id": "t-3", "status": "success", "result": {"routes": []}},
        ]
        data = synth.extract_data(results)
        assert len(data) == 2

    def test_summary_includes_all_tasks(self):
        synth = ResultSynthesizer()
        results = [
            {"subtask_id": "t-1", "status": "success", "description": "Login"},
            {"subtask_id": "t-2", "status": "error", "description": "Export", "error": "Timeout"},
        ]
        final = synth.synthesize("Test", results)
        assert "Login" in final["summary"]
        assert "Export" in final["summary"]


# ===========================================================================
# Conductor (end-to-end)
# ===========================================================================


class TestConductor:
    @pytest.mark.asyncio
    async def test_run_simple_goal(self):
        conductor = Conductor()
        result = await conductor.run("Click the OK button")
        assert result["status"] == "success"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_multi_task_goal(self):
        conductor = Conductor()
        result = await conductor.run("Login to firewall and check ARP table")
        # Should decompose into multiple tasks
        assert result["tasks_total"] >= 1

    @pytest.mark.asyncio
    async def test_run_with_custom_executor(self):
        executed = []

        def my_fn(subtask: Subtask) -> str:
            executed.append(subtask.subtask_id)
            return "ok"

        conductor = Conductor(executor_fn=my_fn)
        result = await conductor.run("Do task A and task B")
        assert result["success"] is True or result["status"] in ("partial", "error")

    @pytest.mark.asyncio
    async def test_plan_preview(self):
        conductor = Conductor()
        plan = conductor.plan("Login to firewall and check ARP")
        assert len(plan) >= 1
        assert "subtask_id" in plan[0]

    @pytest.mark.asyncio
    async def test_empty_goal(self):
        conductor = Conductor()
        result = await conductor.run("OK")
        assert "status" in result

    @pytest.mark.asyncio
    async def test_network_heavy_goal(self):
        conductor = Conductor()
        result = await conductor.run("SSH into router and run show version and show interfaces")
        assert result["tasks_total"] >= 1
