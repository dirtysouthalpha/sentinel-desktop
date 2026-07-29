"""Tests for the CNS 1.0 Conductor."""
import asyncio
import pytest
from core.cns.conductor import Conductor, PlanResult
from core.cns.evaluator import EvalStatus
from core.cns.planner import Subtask, TaskType


class TestPlanResult:
    def test_empty_result_score_zero(self):
        result = PlanResult(goal="test")
        assert result.overall_score == 0.0

    def test_all_passed_empty(self):
        result = PlanResult(goal="test")
        assert result.all_passed is True  # vacuously true

    def test_overall_score_average(self):
        from core.cns.evaluator import EvalResult
        result = PlanResult(goal="test")
        result.eval_results = [
            EvalResult("a", EvalStatus.PASS, 1.0),
            EvalResult("b", EvalStatus.PASS, 0.5),
        ]
        assert result.overall_score == pytest.approx(0.75)


class TestConductor:
    @pytest.mark.asyncio
    async def test_simple_goal_completes(self):
        """A simple goal runs to completion."""
        cond = Conductor()
        result = await cond.run("list files")
        assert result.status == "completed"
        assert result.completed >= 1

    @pytest.mark.asyncio
    async def test_empty_goal_noop(self):
        """Empty goal returns immediately."""
        cond = Conductor()
        result = await cond.run("")
        assert result.subtotal == 0
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_multistep_goal(self):
        """Multi-step goal decomposes and runs."""
        cond = Conductor()
        result = await cond.run("check disk then check memory")
        assert result.subtotal >= 2
        assert result.completed >= 2

    @pytest.mark.asyncio
    async def test_custom_handler(self):
        """Custom handler is called for each subtask."""
        calls = []

        async def handler(subtask):
            calls.append(subtask.id)
            return {"output": "done: " + subtask.description}

        cond = Conductor()
        result = await cond.run("do A then do B", handler=handler)
        assert len(calls) == result.subtotal
        assert result.completed == result.subtotal

    @pytest.mark.asyncio
    async def test_failed_subtask_retried(self):
        """Failed subtask is retried up to max_retries."""
        attempts = {}

        async def handler(subtask):
            count = attempts.get(subtask.id, 0) + 1
            attempts[subtask.id] = count
            if count < 3:
                return {"output": "fail"}
            return {"output": "success"}

        cond = Conductor(max_retries=3)
        result = await cond.run(
            "do task",
            handler=handler,
            expected={"": "success"},  # won't match, handler uses subtask.id
        )
        # All tasks eventually pass on 3rd attempt
        assert result.retried >= 1

    @pytest.mark.asyncio
    async def test_evaluation_results_populated(self):
        """Evaluation results are collected for each subtask."""
        cond = Conductor()
        result = await cond.run("analyze fleet health")
        assert len(result.eval_results) >= 1
        assert all(r.subtask_id for r in result.eval_results)

    @pytest.mark.asyncio
    async def test_overall_score_in_range(self):
        """Overall score is between 0 and 1."""
        cond = Conductor()
        result = await cond.run("check status")
        assert 0.0 <= result.overall_score <= 1.0

    @pytest.mark.asyncio
    async def test_handler_receives_subtask(self):
        """Handler receives the Subtask object."""
        received = []

        async def handler(subtask):
            received.append(subtask)
            return {"output": subtask.description}

        cond = Conductor()
        await cond.run("test goal", handler=handler)
        assert all(isinstance(s, Subtask) for s in received)

    @pytest.mark.asyncio
    async def test_conductor_sync_handler(self):
        """Conductor works with sync handlers too."""
        def handler(subtask):
            # Return description as output → perfect eval match
            return {"output": subtask.description}

        cond = Conductor()
        result = await cond.run("do something", handler=handler)
        assert result.status == "completed"
