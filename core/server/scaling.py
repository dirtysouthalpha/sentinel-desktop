"""Automation scaling — queue tasks, limit parallelism, track metrics.

Ensures the system doesn't overload when many automations fire at once.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """An automation task waiting in the queue."""

    name: str
    fn: Callable[..., Any]
    args: tuple = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    submitted_at: float = field(default_factory=time.time)
    result: Any = None
    error: str = ""
    done: bool = False


@dataclass
class ServerMetrics:
    """Enterprise-grade automation metrics."""

    tasks_submitted: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_duration_ms: float = 0.0
    queue_depth: int = 0
    workers_active: int = 0
    success_rate: float = 1.0


class ScalingController:
    """Queue + worker pool for automated tasks."""

    def __init__(self, max_workers: int = 4) -> None:
        self._max_workers = max_workers
        self._queue: deque[Task] = deque()
        self._workers: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._metrics = ServerMetrics()
        self._running = False
        self._durations: deque[float] = deque(maxlen=100)

    def start(self) -> None:
        """Start the worker pool."""
        self._running = True
        for i in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"sentinel-worker-{i}")
            t.start()
            self._workers.append(t)
        logger.info("Scaling controller started with %d workers", self._max_workers)

    def stop(self) -> None:
        self._running = False
        for t in self._workers:
            t.join(timeout=5)
        self._workers.clear()

    def submit(self, name: str, fn: Callable[..., Any], *args: Any, priority: int = 0, **kwargs: Any) -> Task:
        """Submit a task to the queue."""
        task = Task(name=name, fn=fn, args=args, kwargs=kwargs, priority=priority)
        with self._lock:
            # Insert by priority (higher = sooner)
            inserted = False
            for i, existing in enumerate(self._queue):
                if task.priority > existing.priority:
                    self._queue.insert(i, task)
                    inserted = True
                    break
            if not inserted:
                self._queue.append(task)
            self._metrics.tasks_submitted += 1
            self._metrics.queue_depth = len(self._queue)
        return task

    def _worker_loop(self) -> None:
        while self._running:
            task = None
            with self._lock:
                if self._queue:
                    task = self._queue.popleft()
                    self._metrics.queue_depth = len(self._queue)
            if task is None:
                time.sleep(0.1)
                continue

            start = time.time()
            try:
                task.result = task.fn(*task.args, **task.kwargs)
                task.done = True
                with self._lock:
                    self._metrics.tasks_completed += 1
            except Exception as exc:
                task.error = str(exc)
                task.done = True
                with self._lock:
                    self._metrics.tasks_failed += 1
                logger.error("Task %s failed: %s", task.name, exc)

            duration = (time.time() - start) * 1000  # ms
            self._durations.append(duration)
            with self._lock:
                self._metrics.avg_duration_ms = sum(self._durations) / len(self._durations)
                total = self._metrics.tasks_completed + self._metrics.tasks_failed
                self._metrics.success_rate = self._metrics.tasks_completed / total if total > 0 else 1.0

    @property
    def metrics(self) -> ServerMetrics:
        with self._lock:
            self._metrics.workers_active = sum(1 for t in self._workers if t.is_alive())
            return ServerMetrics(
                tasks_submitted=self._metrics.tasks_submitted,
                tasks_completed=self._metrics.tasks_completed,
                tasks_failed=self._metrics.tasks_failed,
                avg_duration_ms=self._metrics.avg_duration_ms,
                queue_depth=len(self._queue),
                workers_active=sum(1 for t in self._workers if t.is_alive()),
                success_rate=self._metrics.success_rate,
            )


__all__ = ["Task", "ServerMetrics", "ScalingController"]
