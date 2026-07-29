"""Tests for task budget enforcement."""
import pytest
from core.mesh.budget import BudgetEnforcer
from core.mesh.task_graph import Task, TaskBudget, TaskStatus


class TestBudgetEnforcer:
    def test_within_budget(self):
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_api_calls=10))
        assert BudgetEnforcer().check_budget(task, api_calls=5) is True

    def test_exceeded_budget(self):
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_api_calls=5))
        assert BudgetEnforcer().check_budget(task, api_calls=10) is False

    def test_runtime_budget(self):
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_runtime_seconds=60))
        assert BudgetEnforcer().check_budget(task, runtime_seconds=120) is False

    def test_cost_budget(self):
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_cost_usd=1.0))
        assert BudgetEnforcer().check_budget(task, cost_usd=2.0) is False

    def test_budget_status(self):
        task = Task(id="t1", type="reasoning", goal="test", budget=TaskBudget(max_api_calls=100))
        status = BudgetEnforcer().get_budget_status(task, api_calls=75)
        assert status["api_calls_remaining"] == 25
        assert status["api_calls_pct"] == 75.0
