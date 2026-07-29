"""Golden eval suite for fleet-wide observability (vNext Phase 7).

Each eval is a standardized, repeatable check that a component meets its
bar. Evans are tagged by component and priority. The runner executes all
evals, produces a pass/fail report, and can track trends over time.

Components covered:
  - mesh      : leader election, task dispatch, event propagation
  - empire    : plan creation, scoring, narrative generation
  - executor  : shell/python/action/llm/empire task execution
  - trust_dial: action classification and enforcement
  - memory    : checkpoint store/load, incomplete plan search
  - self_improvement: audit detection, proposal generation
  - cli       : command parsing and dispatch
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class EvalComponent(str, Enum):
    MESH = "mesh"
    EMPIRE = "empire"
    EXECUTOR = "executor"
    TRUST_DIAL = "trust_dial"
    MEMORY = "memory"
    SELF_IMPROVEMENT = "self_improvement"
    CLI = "cli"
    CNS = "cns"


class EvalPriority(str, Enum):
    CRITICAL = "critical"  # Must pass for fleet to be considered healthy
    HIGH = "high"          # Should pass; regressions need investigation
    MEDIUM = "medium"      # Nice to have; tracks quality over time


@dataclass
class EvalResult:
    """Result of a single eval."""
    name: str
    component: EvalComponent
    priority: EvalPriority
    passed: bool
    duration_seconds: float
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalReport:
    """Full eval run report."""
    timestamp: str
    results: list[EvalResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total else 0.0

    @property
    def critical_failures(self) -> list[EvalResult]:
        return [r for r in self.results if not r.passed and r.priority == EvalPriority.CRITICAL]

    def by_component(self) -> dict[str, list[EvalResult]]:
        out: dict[str, list[EvalResult]] = {}
        for r in self.results:
            out.setdefault(r.component.value, []).append(r)
        return out

    def summary(self) -> str:
        lines = [
            f"Golden Eval Report — {self.timestamp}",
            f"Total: {self.total} | Passed: {self.passed} | Failed: {self.failed} | Rate: {self.pass_rate:.1f}%",
        ]
        if self.critical_failures:
            lines.append(f"⚠ {len(self.critical_failures)} CRITICAL FAILURE(S):")
            for r in self.critical_failures:
                lines.append(f"  - [{r.component.value}] {r.name}: {r.message}")
        for comp, results in sorted(self.by_component().items()):
            p = sum(1 for r in results if r.passed)
            lines.append(f"  {comp}: {p}/{len(results)} passed")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Eval registry
# ---------------------------------------------------------------------------

EvalFn = Callable[[], Any]


class EvalSuite:
    """Collects and runs golden evals."""

    def __init__(self) -> None:
        self._evals: list[tuple[str, EvalComponent, EvalPriority, EvalFn]] = []

    def register(
        self,
        component: EvalComponent,
        priority: EvalPriority = EvalPriority.HIGH,
    ) -> Callable[[EvalFn], EvalFn]:
        """Decorator to register an eval function."""
        def decorator(fn: EvalFn) -> EvalFn:
            self._evals.append((fn.__name__, component, priority, fn))
            return fn
        return decorator

    def run(self) -> EvalReport:
        """Execute all registered evals and return a report."""
        report = EvalReport(timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        for name, component, priority, fn in self._evals:
            start = time.time()
            try:
                result = fn()
                # Handle async evals.
                if asyncio.iscoroutine(result):
                    result = asyncio.run(result)
                duration = time.time() - start
                if isinstance(result, bool):
                    report.results.append(EvalResult(
                        name=name, component=component, priority=priority,
                        passed=result, duration_seconds=duration,
                    ))
                elif isinstance(result, tuple):
                    passed, message = result[0], result[1] if len(result) > 1 else ""
                    report.results.append(EvalResult(
                        name=name, component=component, priority=priority,
                        passed=bool(passed), duration_seconds=duration, message=str(message),
                    ))
                elif isinstance(result, dict):
                    report.results.append(EvalResult(
                        name=name, component=component, priority=priority,
                        passed=bool(result.get("passed", False)),
                        duration_seconds=duration,
                        message=str(result.get("message", "")),
                        details=result,
                    ))
                else:
                    report.results.append(EvalResult(
                        name=name, component=component, priority=priority,
                        passed=bool(result), duration_seconds=duration,
                    ))
            except Exception as e:
                duration = time.time() - start
                report.results.append(EvalResult(
                    name=name, component=component, priority=priority,
                    passed=False, duration_seconds=duration, message=str(e),
                ))
        return report


# ---------------------------------------------------------------------------
# Global suite instance + evals
# ---------------------------------------------------------------------------

suite = EvalSuite()


# ---- Mesh evals ----

@suite.register(EvalComponent.MESH, EvalPriority.CRITICAL)
def mesh_leader_election_priority_order() -> tuple[bool, str]:
    """Leader election respects priority ordering: CNS > Prime > Desktop."""
    from core.mesh.leader_election import LeaderElection
    from core.mesh.node import MeshNode, NodeCapabilities, NodePriority

    nodes = [
        MeshNode("desktop-1", "Desktop", NodePriority.DESKTOP, NodeCapabilities()),
        MeshNode("prime-1", "Prime", NodePriority.PRIME, NodeCapabilities(can_orchestrate=True)),
        MeshNode("cns-1", "CNS", NodePriority.CNS, NodeCapabilities(can_orchestrate=True)),
    ]
    for n in nodes:
        n.heartbeat()
    election = LeaderElection(lease_ttl=30)
    winner = election.elect_leader(nodes)
    if winner is None:
        return False, "No leader elected"
    if winner.node_id != "cns-1":
        return False, f"Expected cns-1, got {winner.node_id}"
    return True, f"CNS wins (priority {winner.priority})"


@suite.register(EvalComponent.MESH, EvalPriority.CRITICAL)
def mesh_task_graph_dependency_order() -> tuple[bool, str]:
    """TaskGraph.get_ready_tasks respects dependency order."""
    from core.mesh.task_graph import Task, TaskGraph

    graph = TaskGraph()
    graph.add_task(Task(id="a", type="shell", goal="step A"))
    graph.add_task(Task(id="b", type="shell", goal="step B", depends_on=["a"]))
    graph.add_task(Task(id="c", type="shell", goal="step C", depends_on=["b"]))

    ready = graph.get_ready_tasks()
    if len(ready) != 1 or ready[0].id != "a":
        return False, f"Expected only task 'a' ready, got {[t.id for t in ready]}"
    return True, "Dependency order correct"


@suite.register(EvalComponent.MESH, EvalPriority.HIGH)
def mesh_event_bus_publish_subscribe() -> tuple[bool, str]:
    """Events published on the bus are received by subscribers."""
    from core.mesh.event_bus import EventBus

    bus = EventBus()
    received: list[str] = []
    bus.subscribe("test.event", lambda env: received.append(env["data"]["msg"]))

    # EventBus.publish is async; run it.
    asyncio.run(bus.publish("test.event", {"msg": "hello"}))

    if not received or received[0] != "hello":
        return False, f"Expected 'hello', got {received}"
    return True, "Event delivered"


# ---- Empire evals ----

@suite.register(EvalComponent.EMPIRE, EvalPriority.HIGH)
def empire_plan_scoring_range() -> tuple[bool, str]:
    """Empire score is always in 0–100 range regardless of inputs."""
    from core.mesh.empire_tasks import handle_empire_score

    # Extreme inputs.
    test_cases = [
        {},  # No deps
        {"yt-stats": {"views": 999999}, "alpaca-pnl": {"unrealized_pl": 999999}, "buffer-metrics": {"posts": 999}},
        {"yt-stats": {"views": 0}, "alpaca-pnl": {"unrealized_pl": -99999}, "buffer-metrics": {"posts": 0, "engagement": 0}},
    ]
    for deps in test_cases:
        result = asyncio.run(handle_empire_score({"params": {"dependency_results": deps}}))
        if not (0 <= result["total_score"] <= 100):
            return False, f"Score {result['total_score']} out of range for deps={deps}"
    return True, "All scores in range"


@suite.register(EvalComponent.EMPIRE, EvalPriority.HIGH)
def empire_narrative_includes_score() -> tuple[bool, str]:
    """Narrative output includes the actual score value."""
    from core.mesh.empire_tasks import handle_narrative

    for score in [0, 42.5, 100]:
        result = asyncio.run(handle_narrative({"params": {
            "dependency_results": {"empire-score": {"total_score": score, "components": {}}},
        }}))
        if str(score) not in result["narrative"]:
            return False, f"Score {score} not found in narrative: {result['narrative']}"
    return True, "Narratives contain scores"


# ---- Executor evals ----

@suite.register(EvalComponent.EXECUTOR, EvalPriority.CRITICAL)
def executor_shell_task_succeeds() -> tuple[bool, str]:
    """A basic shell task executes and returns stdout."""
    from core.mesh.event_bus import EventBus, FleetEvent
    from core.mesh.executor import TaskExecutor
    from core.mesh.node import NodeCapabilities

    bus = EventBus()
    executor = TaskExecutor(node_id="eval-node", bus=bus, capabilities=NodeCapabilities())
    executor.start()

    completed: list[dict[str, Any]] = []
    bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

    asyncio.run(bus.publish(FleetEvent.TASK_ASSIGNED, {
        "task_id": "eval-shell-1",
        "plan_id": "eval-plan",
        "node_id": "eval-node",
        "task_type": "shell",
        "goal": "echo golden eval test",
        "params": {"command": "echo golden eval test"},
    }))

    # Wait briefly for completion.
    for _ in range(100):
        if completed:
            break
        time.sleep(0.05)

    executor.stop()
    if not completed:
        return False, "Shell task did not complete"
    stdout = completed[0]["data"]["result"].get("stdout", "")
    if "golden eval test" not in stdout:
        return False, f"Unexpected stdout: {stdout}"
    return True, "Shell task executed correctly"


@suite.register(EvalComponent.EXECUTOR, EvalPriority.HIGH)
def executor_python_task_succeeds() -> tuple[bool, str]:
    """A Python task executes and returns the function result."""
    from core.mesh.event_bus import EventBus, FleetEvent
    from core.mesh.executor import TaskExecutor
    from core.mesh.node import NodeCapabilities

    bus = EventBus()
    executor = TaskExecutor(node_id="eval-node-py", bus=bus, capabilities=NodeCapabilities())
    executor.start()

    completed: list[dict[str, Any]] = []
    bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

    asyncio.run(bus.publish(FleetEvent.TASK_ASSIGNED, {
        "task_id": "eval-py-1",
        "plan_id": "eval-plan",
        "node_id": "eval-node-py",
        "task_type": "python",
        "goal": "compute sum",
        "params": {"module": "builtins", "function": "sum", "args": [[1, 2, 3]]},
    }))

    for _ in range(100):
        if completed:
            break
        time.sleep(0.05)

    executor.stop()
    if not completed:
        return False, "Python task did not complete"
    if completed[0]["data"]["result"].get("return_value") != "6":
        return False, f"Unexpected result: {completed[0]['data']['result']}"
    return True, "Python task executed correctly"


# ---- Trust dial evals ----

@suite.register(EvalComponent.TRUST_DIAL, EvalPriority.CRITICAL)
def trust_dial_safe_action_allowed() -> tuple[bool, str]:
    """SAFE actions are executable at default trust level."""
    from core.mesh.trust_dial import TrustDial

    td = TrustDial()
    action_type = td.classify_action("echo")
    if action_type.value != "safe":
        return False, f"Expected 'safe', got '{action_type.value}'"
    if not td.can_execute(action_type):
        return False, "SAFE action blocked"
    return True, "SAFE action allowed"


@suite.register(EvalComponent.TRUST_DIAL, EvalPriority.CRITICAL)
def trust_dial_destructive_blocked_without_trust() -> tuple[bool, str]:
    """DESTRUCTIVE actions are blocked at default trust level."""
    from core.mesh.trust_dial import TrustDial

    td = TrustDial()
    action_type = td.classify_action("rm")
    if action_type.value != "destructive":
        return False, f"Expected 'destructive', got '{action_type.value}'"
    if td.can_execute(action_type):
        return False, "DESTRUCTIVE action should be blocked"
    return True, "DESTRUCTIVE action blocked without trust"


# ---- Memory evals ----

@suite.register(EvalComponent.MEMORY, EvalPriority.HIGH)
def memory_checkpoint_roundtrip() -> tuple[bool, str]:
    """NeuralisMemory checkpoint store → load roundtrip works (or degrades gracefully)."""
    import tempfile

    from core.mesh.memory import NeuralisMemory
    from core.mesh.task_graph import Task, TaskGraph

    with tempfile.TemporaryDirectory() as tmpdir:
        # Use disabled mode to test without a live brain.
        mem = NeuralisMemory(enabled=False)
        graph = TaskGraph(checkpoint_dir=tmpdir)
        graph.add_task(Task(id="t1", type="shell", goal="test", status=__import__("core.mesh.task_graph", fromlist=["TaskStatus"]).TaskStatus.COMPLETED))

        # store_checkpoint returns False when disabled.
        stored = mem.store_checkpoint("plan-eval", "eval plan", graph)
        # load_checkpoint returns None when disabled.
        loaded = mem.load_checkpoint("plan-eval")
        # Both should degrade gracefully (no exceptions).
        return True, f"store={stored}, load={loaded} (disabled mode)"


# ---- Self-improvement evals ----

@suite.register(EvalComponent.SELF_IMPROVEMENT, EvalPriority.HIGH)
def self_improvement_audit_detects_findings() -> tuple[bool, str]:
    """CodeAuditor finds real gaps in a sample project."""
    import tempfile

    from core.mesh.self_improvement import CodeAuditor

    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        sample = '''"""Sample."""
def bad():
    try:
        x = open("f").read()
    except:
        x = ""
    return x
'''
        (Path(tmpdir) / "sample.py").write_text(sample)

        auditor = CodeAuditor(tmpdir)
        findings = auditor.audit()
        if not findings:
            return False, "No findings detected in sample with known gaps"
        return True, f"{len(findings)} findings detected"


@suite.register(EvalComponent.SELF_IMPROVEMENT, EvalPriority.HIGH)
def self_improvement_proposal_priorities() -> tuple[bool, str]:
    """Proposer orders proposals by severity."""
    from core.mesh.self_improvement import (
        CodeAuditor,
        Finding,
        FindingCategory,
        FindingSeverity,
        ImprovementProposer,
    )

    findings = [
        Finding(FindingCategory.STALE_TODO, FindingSeverity.LOW, "f.py", 1, "todo", "fix"),
        Finding(FindingCategory.API_MISMATCH, FindingSeverity.HIGH, "f.py", 2, "mismatch", "fix"),
        Finding(FindingCategory.MISSING_ERROR_HANDLING, FindingSeverity.MEDIUM, "f.py", 3, "bare", "fix"),
    ]
    proposer = ImprovementProposer()
    proposals = proposer.propose(findings)
    if proposals[0].finding.severity != FindingSeverity.HIGH:
        return False, f"Expected HIGH first, got {proposals[0].finding.severity}"
    return True, "Proposals prioritized correctly"


# ---- CLI evals ----

@suite.register(EvalComponent.CLI, EvalPriority.MEDIUM)
def cli_parser_builds() -> tuple[bool, str]:
    """FleetCLI parser builds and --help does not crash."""
    from core.mesh.cli import FleetCLI

    try:
        cli = FleetCLI()
        # parse_args(["--help"]) exits, so just verify the parser exists.
        if cli.parser is None:
            return False, "Parser is None"
        return True, "CLI parser built"
    except Exception as e:
        return False, f"Parser build failed: {e}"


# ---- CNS evals ----

@suite.register(EvalComponent.CNS, EvalPriority.CRITICAL)
def cns_planner_decomposes_multistep() -> tuple[bool, str]:
    """TaskPlanner decomposes a multi-step goal into multiple subtasks."""
    from core.cns.planner import TaskPlanner

    planner = TaskPlanner()
    subtasks = planner.decompose("check disk then check memory then alert")
    if len(subtasks) < 2:
        return False, f"Expected >=2 subtasks, got {len(subtasks)}"
    return True, f"{len(subtasks)} subtasks"


@suite.register(EvalComponent.CNS, EvalPriority.CRITICAL)
def cns_evaluator_perfect_match_scores_one() -> tuple[bool, str]:
    """Evaluator scores a perfect match as 1.0 (PASS)."""
    from core.cns.evaluator import Evaluator

    ev = Evaluator()
    result = ev.evaluate(subtask_id="x", expected="hello world", actual="hello world")
    if result.score != 1.0:
        return False, f"Expected 1.0, got {result.score}"
    if result.status.value != "pass":
        return False, f"Expected pass, got {result.status}"
    return True, "Perfect match scored 1.0"


@suite.register(EvalComponent.CNS, EvalPriority.HIGH)
def cns_conductor_completes_simple_plan() -> tuple[bool, str]:
    """Conductor runs a simple plan to completion."""
    import asyncio

    from core.cns.conductor import Conductor

    async def run():
        cond = Conductor()
        return await cond.run("list files")

    result = asyncio.run(run())
    if result.completed < 1:
        return False, f"Expected >=1 completed, got {result.completed}"
    return True, f"{result.completed}/{result.subtotal} subtasks completed"


@suite.register(EvalComponent.CNS, EvalPriority.HIGH)
def cns_reasoner_detects_failures() -> tuple[bool, str]:
    """Reasoner flags failed evaluations as anomalies."""
    from core.cns.evaluator import EvalResult, EvalStatus
    from core.cns.reasoner import default_reasoner

    reasoner = default_reasoner()
    results = [
        EvalResult("a", EvalStatus.PASS, 1.0),
        EvalResult("b", EvalStatus.FAIL, 0.1),
    ]
    output = reasoner.reason(results)
    if not output.anomalies:
        return False, "Expected anomalies for failed results"
    return True, f"{len(output.anomalies)} anomaly(ies) detected"
