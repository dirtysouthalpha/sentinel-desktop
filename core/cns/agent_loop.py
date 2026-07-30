"""CNS Agent Loop — the main v2.0 cognitive loop.

Ties together the tool registry, memory backend, and reasoner into a
full cognitive loop:

  1. Plan (via v1.0 TaskPlanner)
  2. For each subtask: select tool from registry, execute, capture result
  3. Evaluate (via v1.0 Evaluator)
  4. Reason (via v1.0 Reasoner + CausalReasoner)
  5. If failures -> re-plan with memory of what went wrong
  6. Loop until all pass or max_iterations reached

The agent tracks iteration history for causal reasoning and persists
failures/successes to the memory backend for cross-run learning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.cns.evaluator import EvalResult, EvalStatus, Evaluator
from core.cns.memory_backend import InMemoryBackend, MemoryBackend
from core.cns.planner import Subtask, TaskPlanner
from core.cns.reasoner import Conclusion, Reasoner, ReasoningResult, default_reasoner
from core.cns.reasoner_v2 import CausalReasoner
from core.cns.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Snapshot of the agent's current state.

    Attributes:
        goal: The current goal being pursued.
        plan: The current list of subtasks.
        results: The latest evaluation results.
        iteration: The current iteration count (0-indexed).
        max_iterations: Maximum allowed iterations.
        history: List of past ReasoningResult for causal reasoning.
        status: Current status string (running, completed, failed).
    """
    goal: str = ""
    plan: list[Subtask] = field(default_factory=list)
    results: list[EvalResult] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 10
    history: list[ReasoningResult] = field(default_factory=list)
    status: str = "idle"


class CNSAgent:
    """CNS v2.0 agent loop — full cognitive cycle.

    Orchestrates planning, tool execution, evaluation, reasoning, and
    re-planning with memory. Uses the CausalReasoner for trend detection
    across iterations.

    Example:
        registry = ToolRegistry()
        registry.register("echo", lambda text: text, "Echo tool")
        agent = CNSAgent(tool_registry=registry)
        state = agent.run("echo hello then echo world")
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        memory_backend: MemoryBackend | None = None,
        reasoner: Reasoner | None = None,
        causal_reasoner: CausalReasoner | None = None,
        planner: TaskPlanner | None = None,
        evaluator: Evaluator | None = None,
        max_iterations: int = 10,
    ) -> None:
        self.tool_registry = (
            tool_registry if tool_registry is not None else ToolRegistry()
        )
        self.memory = (
            memory_backend if memory_backend is not None else InMemoryBackend()
        )
        self.reasoner = reasoner or default_reasoner()
        self.causal_reasoner = causal_reasoner or CausalReasoner()
        self.planner = planner or TaskPlanner()
        self.evaluator = evaluator or Evaluator()
        self.max_iterations = max_iterations
        self._state = AgentState(max_iterations=max_iterations)

    def run(self, goal: str, max_iterations: int | None = None) -> AgentState:
        """Run the full cognitive loop for a goal.

        Args:
            goal: The natural-language goal to accomplish.
            max_iterations: Override the default max iterations.

        Returns:
            The final AgentState after the loop completes.
        """
        if max_iterations is not None:
            self.max_iterations = max_iterations

        self._state = AgentState(
            goal=goal,
            max_iterations=self.max_iterations,
            status="running",
        )

        for iteration in range(self.max_iterations):
            self._state.iteration = iteration
            logger.info(
                "CNS Agent iteration %d/%d for goal: %s",
                iteration + 1, self.max_iterations, goal[:60],
            )

            # Step 1: Plan (decompose goal, incorporating memory of past failures).
            plan = self._plan(goal)
            self._state.plan = plan

            if not plan:
                logger.info("No subtasks generated — goal considered done.")
                self._state.status = "completed"
                break

            # Step 2: Execute subtasks using tools from the registry.
            outputs = self._execute(plan)

            # Step 3: Evaluate results.
            results = self._evaluate(plan, outputs)
            self._state.results = results

            # Step 4: Reason about results (v1.0 rules + causal).
            reasoning = self._reason(results)
            self._state.history.append(reasoning)

            # Step 5: Check if all passed.
            all_passed = all(r.status == EvalStatus.PASS for r in results)
            if all_passed:
                logger.info("All subtasks passed — goal complete.")
                self._state.status = "completed"
                self.memory.remember(
                    f"success:{goal[:50]}",
                    {"iteration": iteration, "subtasks": len(plan)},
                )
                break

            # Step 6: Remember failures for re-planning.
            failures = [r for r in results if r.status == EvalStatus.FAIL]
            self.memory.remember(
                f"failure:{goal[:50]}:iter{iteration}",
                {
                    "failures": len(failures),
                    "iteration": iteration,
                    "anomalies": reasoning.anomalies,
                },
            )
            logger.warning(
                "Iteration %d: %d/%d subtasks failed — re-planning.",
                iteration + 1, len(failures), len(results),
            )
        else:
            # Loop exhausted max_iterations without full success.
            self._state.status = "failed"
            logger.error(
                "CNS Agent exhausted %d iterations without completing goal.",
                self.max_iterations,
            )

        return self._state

    def _plan(self, goal: str) -> list[Subtask]:
        """Decompose the goal into subtasks, enriching with memory context.

        Before planning, checks memory for past failures on similar goals
        and appends context to the goal description to guide re-planning.
        """
        enriched_goal = goal
        # Check memory for past failure context.
        past = self.memory.recall(f"failure:{goal[:50]}:iter{self._state.iteration - 1}")
        if past and isinstance(past, dict):
            failures = past.get("failures", 0)
            if failures > 0:
                enriched_goal = (
                    f"{goal} (note: previous attempt had {failures} failures; "
                    f"try a different approach)"
                )
                logger.debug("Enriched goal with failure context from memory.")

        return self.planner.decompose(enriched_goal)

    def _execute(self, plan: list[Subtask]) -> dict[str, str]:
        """Execute each subtask using a tool from the registry.

        Returns a dict mapping subtask ID to output string.
        """
        outputs: dict[str, str] = {}
        for subtask in plan:
            tool_name = self._select_tool(subtask)
            if tool_name is None:
                # No matching tool — use the description as output (fallback).
                outputs[subtask.id] = subtask.description
                continue

            call = self.tool_registry.call(tool_name, text=subtask.description)
            outputs[subtask.id] = call.result.output
            if not call.result.success:
                logger.warning(
                    "Tool '%s' failed for subtask %s: %s",
                    tool_name, subtask.id, call.result.error,
                )
        return outputs

    def _select_tool(self, subtask: Subtask) -> str | None:
        """Select the best tool for a subtask.

        Strategy: look for a tool whose name appears in the subtask
        description. If none found, fall back to a "default" tool if
        registered. Returns None if no tool matches.
        """
        desc_lower = subtask.description.lower()

        # Direct name match.
        for tool_info in self.tool_registry.list_tools():
            name = tool_info["name"]
            if name in desc_lower:
                return name

        # Fallback: use "default" tool if available.
        if "default" in self.tool_registry:
            return "default"

        return None

    def _evaluate(
        self, plan: list[Subtask], outputs: dict[str, str]
    ) -> list[EvalResult]:
        """Evaluate each subtask's output against its description."""
        results: list[EvalResult] = []
        for subtask in plan:
            output = outputs.get(subtask.id, "")
            eval_result = self.evaluator.evaluate(
                subtask_id=subtask.id,
                expected=subtask.description,
                actual=output,
            )
            results.append(eval_result)
        return results

    def _reason(self, results: list[EvalResult]) -> ReasoningResult:
        """Apply both v1.0 rules and causal reasoning.

        Merges conclusions from the standard Reasoner and the
        CausalReasoner into a single ReasoningResult.
        """
        # Standard v1.0 reasoning.
        std_result = self.reasoner.reason(
            results,
            findings={"retried": 0},
        )

        # Causal reasoning with history.
        causal_result = self.causal_reasoner.reason(
            results,
            findings={},
            history=self._state.history,
        )

        # Merge conclusions.
        merged = ReasoningResult()
        merged.conclusions = std_result.conclusions + causal_result.conclusions
        merged.anomalies = std_result.anomalies + causal_result.anomalies
        merged.recommendations = (
            std_result.recommendations + causal_result.recommendations
        )
        return merged

    def get_state(self) -> AgentState:
        """Return the current agent state.

        Returns:
            A snapshot of the current plan, results, iteration count, etc.
        """
        return self._state
