# Fleet Mesh Phase 3 — Agent Integration, Neuralis Memory, Observability

**Date:** 2026-07-29
**Goal:** Make the mesh execute real work (desktop actions + LLM), survive restarts (Neuralis memory), and self-monitor (fleet observability).
**Depends on:** Phase 1 (11 modules) + Phase 2 (transport, executor, dashboard)

---

## Task 1: Real Agent Execution

**Files:**
- Modify: `core/mesh/executor.py` — wire `_exec_action` and `_exec_llm` to real backends
- Test: `tests/test_mesh_executor_integration.py`

### Design

The executor's `_exec_action` and `_exec_llm` are currently stubs. Wire them to `ActionExecutor` and `LLMClient`.

The executor needs config for LLM calls (provider, api_key, model). Add an optional `llm_config` parameter to the constructor.

### Modify `core/mesh/executor.py`

**Constructor change:**
```python
def __init__(
    self,
    node_id: str,
    bus: EventBus,
    capabilities: NodeCapabilities,
    llm_config: dict[str, str] | None = None,
) -> None:
    self.node_id = node_id
    self.bus = bus
    self.capabilities = capabilities
    self.llm_config = llm_config or {}
    self._handlers: dict[str, Callable] = {...}
    self._executor: ActionExecutor | None = None  # lazy-init
    self._llm: LLMClient | None = None  # lazy-init
    self._running = False
```

**Lazy-init properties:**
```python
@property
def action_executor(self) -> ActionExecutor:
    if self._executor is None:
        from core.action_executor import ActionExecutor
        self._executor = ActionExecutor()
    return self._executor

@property
def llm_client(self) -> LLMClient:
    if self._llm is None:
        from core.llm_client import LLMClient
        self._llm = LLMClient()
    return self._llm
```

**Real `_exec_action`:**
```python
async def _exec_action(self, task: dict[str, Any]) -> dict[str, Any]:
    """Execute a Sentinel Desktop action via ActionExecutor."""
    action_name = task.get("params", {}).get("action", "")
    action_params = task.get("params", {}).get("action_params", {})
    if not action_name:
        raise ValueError("Action task requires 'action' param")

    # Build the action dict in the format ActionExecutor expects
    action = {"action": action_name, **action_params}

    # Execute (run in thread pool since execute_sync is blocking)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, self.action_executor.execute_sync, action
    )
    return result
```

**Real `_exec_llm`:**
```python
async def _exec_llm(self, task: dict[str, Any]) -> dict[str, Any]:
    """Execute an LLM call via LLMClient."""
    prompt = task.get("goal", "")
    model = task.get("params", {}).get("model", self.llm_config.get("model", "gpt-4o"))
    provider = task.get("params", {}).get("provider", self.llm_config.get("provider", "openai"))
    api_key = self.llm_config.get("api_key", "")
    api_base_url = self.llm_config.get("api_base_url")

    if not prompt:
        raise ValueError("LLM task requires a goal/prompt")

    messages = [{"role": "user", "content": prompt}]

    # Run in thread pool since LLMClient.chat is blocking
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: self.llm_client.chat(
            provider=provider,
            api_key=api_key,
            model=model,
            messages=messages,
            custom_url=api_base_url,
        )
    )
    return {"model": model, "provider": provider, "prompt": prompt, "response": response}
```

### `tests/test_mesh_executor_integration.py`

```python
"""Integration tests for the task executor with real backends."""
import pytest
from unittest.mock import patch, MagicMock
from core.mesh.executor import TaskExecutor
from core.mesh.event_bus import EventBus, FleetEvent
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

            await executor._exec_llm({
                "task_id": "t1",
                "goal": "test prompt",
                "params": {},
            })
            call_kwargs = mock_instance.chat.call_args
            assert call_kwargs.kwargs["model"] == "gpt-4o"
            assert call_kwargs.kwargs["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_action_task_end_to_end(self, executor):
        """Action task assignment → execution → TASK_COMPLETED."""
        bus = executor.bus
        completed = []
        bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

        with patch.object(executor, "action_executor") as mock_ae:
            mock_ae.execute_sync.return_value = {"success": True}
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
```

---

## Task 2: Neuralis Cross-Session Memory

**Files:**
- Create: `core/mesh/memory.py` — `NeuralisMemory` adapter
- Modify: `core/mesh/orchestrator.py` — auto-checkpoint to Neuralis
- Test: `tests/test_mesh_memory.py`

### Design

The orchestrator creates plans and manages task graphs. For cross-session resilience, we persist checkpoints to Neuralis neurons. On startup, we search for incomplete plans and resume them.

Neuron format for checkpoints:
```
Topic: "orchestrator-checkpoint:<plan_id>"
Content: JSON-serialized TaskGraph checkpoint
Region: "fleet" (or "context" for events)
```

### `core/mesh/memory.py`

```python
"""Neuralis-backed cross-session memory for the fleet mesh."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from core.mesh.task_graph import TaskGraph

logger = logging.getLogger(__name__)

DEFAULT_BRAIN_URL = os.environ.get("NEURALIS_BRAIN_URL", "http://100.64.0.2:8001")


class NeuralisMemory:
    """Stores and retrieves fleet state via the Neuralis brain.

    Each plan checkpoint is a neuron:
    - topic: "orchestrator-checkpoint:<plan_id>"
    - content: JSON with plan metadata + serialized task graph
    - region: "fleet"
    """

    def __init__(self, brain_url: str = DEFAULT_BRAIN_URL, enabled: bool = True) -> None:
        self.brain_url = brain_url
        self.enabled = enabled
        self._brain = None
        if enabled:
            try:
                from core.legacy_brain import BrainClient
                self._brain = BrainClient(url=brain_url)
                logger.info("Neuralis memory initialized: %s", brain_url)
            except Exception as e:
                logger.warning("Neuralis memory init failed: %s", e)
                self.enabled = False

    def store_checkpoint(self, plan_id: str, name: str, graph: TaskGraph) -> bool:
        """Persist a plan checkpoint to Neuralis."""
        if not self.enabled or not self._brain:
            return False
        try:
            tasks_data = []
            for task in graph.tasks.values():
                tasks_data.append({
                    "id": task.id,
                    "type": task.type,
                    "goal": task.goal,
                    "status": task.status.value,
                    "assigned_node": task.assigned_node,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                    "result": task.result,
                    "error": task.error,
                    "depends_on": task.depends_on,
                    "params": task.params,
                })
            checkpoint = {
                "plan_id": plan_id,
                "name": name,
                "tasks": tasks_data,
                "is_complete": graph.is_complete(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._brain.think(
                topic=f"orchestrator-checkpoint:{plan_id}",
                content=json.dumps(checkpoint),
                region="fleet",
            )
            logger.debug("Checkpoint stored for plan %s", plan_id)
            return True
        except Exception as e:
            logger.warning("Failed to store checkpoint for %s: %s", plan_id, e)
            return False

    def load_checkpoint(self, plan_id: str) -> dict[str, Any] | None:
        """Load a specific plan checkpoint."""
        if not self.enabled or not self._brain:
            return None
        try:
            results = self._brain.search(q=f"orchestrator-checkpoint:{plan_id}")
            if not results:
                return None
            # Find exact match
            for neuron in results:
                topic = neuron.get("topic", "")
                if topic == f"orchestrator-checkpoint:{plan_id}":
                    content = neuron.get("content", "{}")
                    if isinstance(content, str):
                        return json.loads(content)
                    return content
            return None
        except Exception as e:
            logger.warning("Failed to load checkpoint for %s: %s", plan_id, e)
            return None

    def find_incomplete_plans(self) -> list[dict[str, Any]]:
        """Find all plans that are not yet complete."""
        if not self.enabled or not self._brain:
            return []
        try:
            results = self._brain.search(q="orchestrator-checkpoint:")
            incomplete = []
            for neuron in results:
                content = neuron.get("content", "{}")
                try:
                    if isinstance(content, str):
                        data = json.loads(content)
                    else:
                        data = content
                    if not data.get("is_complete", True):
                        incomplete.append(data)
                except (json.JSONDecodeError, TypeError):
                    continue
            return incomplete
        except Exception as e:
            logger.warning("Failed to search for incomplete plans: %s", e)
            return []

    def store_event(self, event_type: str, data: dict[str, Any]) -> bool:
        """Store a fleet event as a neuron."""
        if not self.enabled or not self._brain:
            return False
        try:
            content = json.dumps({
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._brain.think(
                topic=f"fleet-event:{event_type}",
                content=content,
                region="context",
            )
            return True
        except Exception as e:
            logger.warning("Failed to store event: %s", e)
            return False
```

### Modify `core/mesh/orchestrator.py`

Add optional `memory: NeuralisMemory | None = None` to constructor.

After `graph.checkpoint(task_id)` in `complete_task`, `fail_task`, store checkpoint:
```python
if self.memory:
    graph = self._plans.get(plan_id)
    if graph:
        self.memory.store_checkpoint(plan_id, "", graph)
```

### `tests/test_mesh_memory.py`

```python
"""Tests for Neuralis-backed cross-session memory."""
import json
import pytest
from unittest.mock import MagicMock, patch
from core.mesh.memory import NeuralisMemory
from core.mesh.task_graph import TaskGraph, Task, TaskStatus


class TestNeuralisMemory:
    def test_construct_disabled(self):
        mem = NeuralisMemory(enabled=False)
        assert mem.enabled is False
        assert mem._brain is None

    def test_construct_enabled(self):
        with patch("core.mesh.memory.BrainClient") as MockBrain:
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
```

---

## Task 3: Fleet Observability

**Files:**
- Create: `core/mesh/metrics.py` — System metrics collector + reporter
- Modify: `gui/tabs/fleet_tab.py` — show live metrics
- Test: `tests/test_mesh_metrics.py`

### Design

Each node collects CPU/memory/disk via psutil and publishes `NODE_METRICS` events. The leader (or any node) can aggregate. The dashboard displays per-node metrics.

### `core/mesh/metrics.py`

```python
"""Fleet observability — system metrics collection and reporting."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.mesh.event_bus import EventBus, FleetEvent

logger = logging.getLogger(__name__)


@dataclass
class NodeMetrics:
    """Snapshot of a node's system state."""
    node_id: str
    timestamp: float = 0.0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    tasks_active: int = 0
    tasks_completed: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_used_mb": self.memory_used_mb,
            "memory_total_mb": self.memory_total_mb,
            "disk_percent": self.disk_percent,
            "disk_used_gb": self.disk_used_gb,
            "disk_total_gb": self.disk_total_gb,
            "tasks_active": self.tasks_active,
            "tasks_completed": self.tasks_completed,
            "uptime_seconds": self.uptime_seconds,
        }


class MetricsCollector:
    """Collects system metrics for a mesh node."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self._start_time = time.time()

    def collect(self, tasks_active: int = 0, tasks_completed: int = 0) -> NodeMetrics:
        """Collect current system metrics."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            cpu = psutil.cpu_percent(interval=0.1)
            return NodeMetrics(
                node_id=self.node_id,
                timestamp=time.time(),
                cpu_percent=cpu,
                memory_percent=mem.percent,
                memory_used_mb=mem.used / (1024 * 1024),
                memory_total_mb=mem.total / (1024 * 1024),
                disk_percent=disk.percent,
                disk_used_gb=disk.used / (1024 * 1024 * 1024),
                disk_total_gb=disk.total / (1024 * 1024 * 1024),
                tasks_active=tasks_active,
                tasks_completed=tasks_completed,
                uptime_seconds=time.time() - self._start_time,
            )
        except ImportError:
            return NodeMetrics(
                node_id=self.node_id,
                timestamp=time.time(),
                uptime_seconds=time.time() - self._start_time,
            )


class MetricsReporter:
    """Periodically publishes NODE_METRICS events."""

    def __init__(
        self,
        node_id: str,
        bus: EventBus,
        interval_seconds: float = 30.0,
        task_counter: Callable[[], tuple[int, int]] | None = None,
    ) -> None:
        self.node_id = node_id
        self.bus = bus
        self.interval = interval_seconds
        self._task_counter = task_counter
        self._collector = MetricsCollector(node_id)
        self._running = False

    async def start(self) -> None:
        """Start periodic metrics reporting."""
        self._running = True
        while self._running:
            try:
                active, completed = self._task_counter() if self._task_counter else (0, 0)
                metrics = self._collector.collect(active, completed)
                await self.bus.publish(FleetEvent.NODE_METRICS, metrics.to_dict())
            except Exception as e:
                logger.debug("Metrics publish error: %s", e)
            await asyncio.sleep(self.interval)

    def stop(self) -> None:
        self._running = False


class FleetMetricsAggregator:
    """Aggregates metrics from all nodes (runs on any node, typically leader)."""

    def __init__(self) -> None:
        self._node_metrics: dict[str, NodeMetrics] = {}

    def update(self, metrics_dict: dict[str, Any]) -> None:
        node_id = metrics_dict.get("node_id", "unknown")
        self._node_metrics[node_id] = NodeMetrics(**{
            k: v for k, v in metrics_dict.items() if k in NodeMetrics.__dataclass_fields__
        })

    def get_fleet_summary(self) -> dict[str, Any]:
        nodes = list(self._node_metrics.values())
        if not nodes:
            return {"total_nodes": 0, "healthy_nodes": 0, "avg_cpu": 0, "avg_memory": 0}
        return {
            "total_nodes": len(nodes),
            "healthy_nodes": sum(1 for n in nodes if n.memory_percent < 90 and n.cpu_percent < 90),
            "avg_cpu": sum(n.cpu_percent for n in nodes) / len(nodes),
            "avg_memory": sum(n.memory_percent for n in nodes) / len(nodes),
            "total_tasks_active": sum(n.tasks_active for n in nodes),
            "total_tasks_completed": sum(n.tasks_completed for n in nodes),
            "nodes": {n.node_id: n.to_dict() for n in nodes},
        }

    def get_stuck_nodes(self, cpu_threshold: float = 95.0, memory_threshold: float = 95.0) -> list[str]:
        """Find nodes that may need intervention."""
        stuck = []
        for node_id, metrics in self._node_metrics.items():
            if metrics.cpu_percent > cpu_threshold or metrics.memory_percent > memory_threshold:
                stuck.append(node_id)
        return stuck
```

### Add `NODE_METRICS` to `core/mesh/event_bus.py`

Add to `FleetEvent` enum:
```python
NODE_METRICS = "fleet.event.node.metrics"
```

### Modify `gui/tabs/fleet_tab.py`

Add a metrics display section. Add `_metrics_aggregator` and subscribe to `NODE_METRICS`:

```python
from core.mesh.metrics import FleetMetricsAggregator

# In __init__:
self._metrics_aggregator = FleetMetricsAggregator()
self.bus.subscribe(FleetEvent.NODE_METRICS, self._on_metrics)

# Add method:
async def _on_metrics(self, envelope: dict[str, Any]) -> None:
    data = envelope.get("data", {})
    self._metrics_aggregator.update(data)
```

### `tests/test_mesh_metrics.py`

```python
"""Tests for fleet observability metrics."""
import pytest
from core.mesh.metrics import MetricsCollector, FleetMetricsAggregator, NodeMetrics
from core.mesh.event_bus import EventBus, FleetEvent


class TestMetricsCollector:
    def test_collect(self):
        collector = MetricsCollector("test-node")
        metrics = collector.collect(tasks_active=3, tasks_completed=10)
        assert metrics.node_id == "test-node"
        assert metrics.tasks_active == 3
        assert metrics.tasks_completed == 10
        assert metrics.cpu_percent >= 0
        assert metrics.memory_percent >= 0

    def test_to_dict(self):
        metrics = NodeMetrics(node_id="n1", cpu_percent=50.0, memory_percent=75.0)
        d = metrics.to_dict()
        assert d["node_id"] == "n1"
        assert d["cpu_percent"] == 50.0


class TestFleetMetricsAggregator:
    def test_update_and_summary(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 50.0, "memory_percent": 60.0})
        agg.update({"node_id": "n2", "cpu_percent": 30.0, "memory_percent": 40.0})

        summary = agg.get_fleet_summary()
        assert summary["total_nodes"] == 2
        assert summary["avg_cpu"] == 40.0
        assert summary["avg_memory"] == 50.0

    def test_empty_summary(self):
        agg = FleetMetricsAggregator()
        summary = agg.get_fleet_summary()
        assert summary["total_nodes"] == 0

    def test_get_stuck_nodes(self):
        agg = FleetMetricsAggregator()
        agg.update({"node_id": "n1", "cpu_percent": 98.0, "memory_percent": 50.0})
        agg.update({"node_id": "n2", "cpu_percent": 10.0, "memory_percent": 20.0})
        stuck = agg.get_stuck_nodes()
        assert "n1" in stuck
        assert "n2" not in stuck
```

---

## Task 4: Integration & Full Test Suite

1. Update `core/mesh/__init__.py` to export `NeuralisMemory`, `MetricsCollector`, `MetricsReporter`, `FleetMetricsAggregator`
2. Update `main.py` mesh mode to start metrics reporter and wire Neuralis memory
3. Run `pytest tests/ -q --tb=short`
4. Run `ruff check core/mesh/`
5. Commit

---

## Self-Review Checklist

1. Executor: real action execution via ActionExecutor, real LLM calls via LLMClient
2. Memory: checkpoint storage/retrieval, incomplete plan discovery, graceful degradation when brain is down
3. Metrics: collection via psutil, periodic reporting, fleet aggregation, stuck node detection
4. Tests: all new code covered, existing tests still pass
