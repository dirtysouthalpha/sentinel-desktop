"""Tests for the CNS 1.0 Task Planner."""
import pytest
from core.cns.planner import (
    TaskPlanner,
    Subtask,
    TaskType,
)


class TestSubtask:
    def test_subtask_creation(self):
        st = Subtask(id="a", description="Do X", type=TaskType.SHELL)
        assert st.id == "a"
        assert st.status == "pending"
        assert st.dependencies == []

    def test_subtask_with_deps(self):
        st = Subtask(id="b", description="Do Y", type=TaskType.REASONING, dependencies=["a"])
        assert st.dependencies == ["a"]


class TestTaskType:
    def test_task_types_defined(self):
        assert TaskType.SHELL.value == "shell"
        assert TaskType.REASONING.value == "reasoning"
        assert TaskType.EVALUATION.value == "evaluation"
        assert TaskType.DESKTOP.value == "desktop"


class TestTaskPlanner:
    def test_simple_goal_single_subtask(self):
        """A simple goal decomposes into a single subtask."""
        planner = TaskPlanner()
        subtasks = planner.decompose("list files in /tmp")
        assert len(subtasks) >= 1
        assert all(isinstance(s, Subtask) for s in subtasks)

    def test_multistep_goal_multiple_subtasks(self):
        """A multi-step goal ('then') decomposes into multiple subtasks."""
        planner = TaskPlanner()
        subtasks = planner.decompose("Check disk space then send alert if over 80%")
        assert len(subtasks) >= 2

    def test_decomposition_assigns_ids(self):
        """Each subtask gets a unique ID."""
        planner = TaskPlanner()
        subtasks = planner.decompose("Do X then do Y then do Z")
        ids = [s.id for s in subtasks]
        assert len(ids) == len(set(ids)), "Subtask IDs must be unique"

    def test_decomposition_links_dependencies(self):
        """Chained subtasks have sequential dependencies."""
        planner = TaskPlanner()
        subtasks = planner.decompose("First do A, then do B, finally do C")
        # At least some subtasks should have dependencies
        deps = [s.dependencies for s in subtasks if s.dependencies]
        assert len(deps) >= 1

    def test_empty_goal_returns_empty(self):
        """Empty goal returns no subtasks."""
        planner = TaskPlanner()
        subtasks = planner.decompose("")
        assert subtasks == []

    def test_goal_with_comma_separated_steps(self):
        """Comma-separated steps are decomposed."""
        planner = TaskPlanner()
        subtasks = planner.decompose("check CPU, check memory, check disk")
        assert len(subtasks) >= 2

    def test_detect_shell_task(self):
        """Shell-like goals get SHELL task type."""
        planner = TaskPlanner()
        subtasks = planner.decompose("run df -h")
        assert any(s.type == TaskType.SHELL for s in subtasks)

    def test_detect_reasoning_task(self):
        """Analysis-like goals get REASONING task type."""
        planner = TaskPlanner()
        subtasks = planner.decompose("analyze the fleet health and plan improvements")
        assert any(s.type == TaskType.REASONING for s in subtasks)

    def test_build_task_graph(self):
        """build_task_graph returns a connected graph."""
        planner = TaskPlanner()
        graph = planner.build_task_graph("do A then do B")
        assert graph is not None
        assert len(graph) >= 2
        # Graph is dict of id -> subtask
        assert all(isinstance(k, str) for k in graph)
        assert all(isinstance(v, Subtask) for v in graph.values())
