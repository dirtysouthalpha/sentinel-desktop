"""Tests for the CNS 2.0 Agent Loop."""
from unittest.mock import MagicMock, patch

import pytest

from core.cns.agent_loop import AgentState, CNSAgent
from core.cns.evaluator import EvalResult, EvalStatus, Evaluator
from core.cns.memory_backend import InMemoryBackend
from core.cns.planner import Subtask, TaskPlanner, TaskType
from core.cns.reasoner import Reasoner, ReasoningResult, default_reasoner
from core.cns.reasoner_v2 import CausalReasoner
from core.cns.tool_registry import ToolRegistry


def _make_registry_with_echo() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("echo", lambda text: text, "Echo the input text")
    return reg


def _make_registry_with_default() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("default", lambda text: text, "Default passthrough tool")
    return reg


class TestAgentState:
    def test_default_state(self):
        s = AgentState()
        assert s.goal == ""
        assert s.iteration == 0
        assert s.status == "idle"
        assert s.plan == []
        assert s.results == []

    def test_state_with_values(self):
        s = AgentState(goal="test", iteration=3, status="running")
        assert s.goal == "test"
        assert s.iteration == 3
        assert s.status == "running"


class TestCNSAgentInit:
    def test_default_init(self):
        agent = CNSAgent()
        assert agent.tool_registry is not None
        assert agent.memory is not None
        assert agent.reasoner is not None
        assert agent.causal_reasoner is not None
        assert agent.planner is not None
        assert agent.evaluator is not None

    def test_custom_init(self):
        reg = ToolRegistry()
        mem = InMemoryBackend()
        agent = CNSAgent(tool_registry=reg, memory_backend=mem)
        assert agent.tool_registry is reg
        assert agent.memory is mem

    def test_max_iterations_default(self):
        agent = CNSAgent()
        assert agent.max_iterations == 10

    def test_max_iterations_custom(self):
        agent = CNSAgent(max_iterations=5)
        assert agent.max_iterations == 5


class TestCNSAgentRun:
    def test_run_with_echo_tool_completes(self):
        """When the echo tool returns the description, eval should pass."""
        reg = _make_registry_with_echo()
        # Use a high-threshold evaluator that always passes.
        evaluator = Evaluator(pass_threshold=0.0)
        agent = CNSAgent(tool_registry=reg, evaluator=evaluator)
        state = agent.run("echo hello")
        assert state.status == "completed"

    def test_run_empty_goal(self):
        """An empty goal produces no subtasks and completes."""
        agent = CNSAgent()
        state = agent.run("")
        assert state.status == "completed"
        assert state.plan == []

    def test_run_exhausts_max_iterations(self):
        """If nothing passes, the agent exhausts max_iterations."""
        reg = ToolRegistry()
        # Register a "default" tool that returns garbage (won't match description).
        reg.register("default", lambda text: "completely unrelated output")
        evaluator = Evaluator(pass_threshold=0.95)  # very high threshold
        agent = CNSAgent(
            tool_registry=reg,
            evaluator=evaluator,
            max_iterations=3,
        )
        state = agent.run("do something hard", max_iterations=3)
        assert state.status == "failed"
        assert state.iteration == 2  # 0-indexed, last was 2

    def test_run_stops_when_all_pass(self):
        """Agent stops early when all subtasks pass."""
        reg = _make_registry_with_echo()
        evaluator = Evaluator(pass_threshold=0.0)
        agent = CNSAgent(tool_registry=reg, evaluator=evaluator, max_iterations=10)
        state = agent.run("echo test")
        assert state.status == "completed"
        # Should complete in 1 iteration.
        assert state.iteration == 0

    def test_run_with_default_tool(self):
        """When no tool name matches, falls back to 'default' tool."""
        reg = _make_registry_with_default()
        evaluator = Evaluator(pass_threshold=0.0)
        agent = CNSAgent(tool_registry=reg, evaluator=evaluator)
        state = agent.run("do a thing")
        assert state.status == "completed"

    def test_run_stores_success_in_memory(self):
        """Successful runs are remembered."""
        reg = _make_registry_with_echo()
        mem = InMemoryBackend()
        evaluator = Evaluator(pass_threshold=0.0)
        agent = CNSAgent(tool_registry=reg, memory_backend=mem, evaluator=evaluator)
        agent.run("echo success")
        # Should have stored a success entry.
        results = mem.search("success")
        assert len(results) >= 1

    def test_run_stores_failures_in_memory(self):
        """Failed iterations are remembered."""
        reg = ToolRegistry()
        reg.register("default", lambda text: "garbage")
        mem = InMemoryBackend()
        evaluator = Evaluator(pass_threshold=0.99)
        agent = CNSAgent(
            tool_registry=reg,
            memory_backend=mem,
            evaluator=evaluator,
            max_iterations=2,
        )
        agent.run("do hard thing")
        results = mem.search("failure")
        assert len(results) >= 1

    def test_run_enriches_goal_with_past_failures(self):
        """On re-planning, past failures are appended to the goal."""
        reg = ToolRegistry()
        reg.register("default", lambda text: "garbage")
        mem = InMemoryBackend()
        evaluator = Evaluator(pass_threshold=0.99)
        agent = CNSAgent(
            tool_registry=reg,
            memory_backend=mem,
            evaluator=evaluator,
            max_iterations=3,
        )
        state = agent.run("do task")
        # The planner should have been called with enriched goal on iter 2.
        # We verify by checking that memory has the failure stored.
        assert state.status == "failed"
        assert len(mem.search("failure")) >= 1


class TestCNSAgentGetState:
    def test_get_state_returns_current(self):
        agent = CNSAgent()
        state = agent.get_state()
        assert isinstance(state, AgentState)
        assert state.status == "idle"

    def test_get_state_after_run(self):
        reg = _make_registry_with_echo()
        evaluator = Evaluator(pass_threshold=0.0)
        agent = CNSAgent(tool_registry=reg, evaluator=evaluator)
        agent.run("echo hi")
        state = agent.get_state()
        assert state.status == "completed"
        assert state.goal == "echo hi"


class TestCNSAgentReasoning:
    def test_reason_merges_standard_and_causal(self):
        """The _reason method merges v1.0 and causal conclusions."""
        reg = _make_registry_with_echo()
        evaluator = Evaluator(pass_threshold=0.0)
        agent = CNSAgent(tool_registry=reg, evaluator=evaluator)
        # Set up state with a history entry.
        agent._state.history.append(ReasoningResult())
        results = [EvalResult("a", EvalStatus.PASS, 0.9)]
        merged = agent._reason(results)
        assert isinstance(merged, ReasoningResult)
        # Should have conclusions from the standard reasoner (all_passed).
        rules = [c.rule for c in merged.conclusions]
        assert "all_passed" in rules

    def test_history_accumulates(self):
        """History grows across iterations."""
        reg = ToolRegistry()
        reg.register("bad", lambda text: "garbage")
        evaluator = Evaluator(pass_threshold=0.99)
        agent = CNSAgent(
            tool_registry=reg,
            evaluator=evaluator,
            max_iterations=3,
        )
        agent.run("do task")
        # Should have history entries from each iteration.
        assert len(agent._state.history) >= 1


class TestCNSAgentToolSelection:
    def test_select_tool_by_name_match(self):
        reg = ToolRegistry()
        reg.register("deploy", lambda text: text)
        reg.register("test", lambda text: text)
        agent = CNSAgent(tool_registry=reg)
        subtask = Subtask(id="1", description="deploy the app", type=TaskType.SHELL)
        assert agent._select_tool(subtask) == "deploy"

    def test_select_tool_fallback_to_default(self):
        reg = ToolRegistry()
        reg.register("default", lambda text: "default")
        agent = CNSAgent(tool_registry=reg)
        subtask = Subtask(id="1", description="do something", type=TaskType.SHELL)
        assert agent._select_tool(subtask) == "default"

    def test_select_tool_returns_none_if_no_match(self):
        reg = ToolRegistry()
        reg.register("deploy", lambda text: text)
        agent = CNSAgent(tool_registry=reg)
        subtask = Subtask(id="1", description="analyze data", type=TaskType.REASONING)
        assert agent._select_tool(subtask) is None
