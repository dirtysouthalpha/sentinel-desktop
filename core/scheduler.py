"""
Sentinel Desktop v26.0.0 — Cron-like Task Scheduler.

Runs tasks on a time-based schedule using a background thread that checks
every 30 seconds. Supports preset schedules and standard 5-field cron
expressions (minute hour day-of-month month day-of-week). Persists task
definitions to ``config/scheduled_tasks.json``.

Task types delegate to the appropriate subsystem:
  - script    → ScriptEngine.run_script
  - workflow  → ScriptEngine.run_script (alias for script)
  - goal      → AgentEngine.run(goal)
  - powershell→ PowerShellRunner.run_script / run_command
"""

import json
import logging
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TASKS_PATH = Path("config/scheduled_tasks.json")
CHECK_INTERVAL = 30  # seconds between scheduler ticks

VALID_TASK_TYPES = {"script", "workflow", "goal", "powershell"}

# ── Preset schedules → cron expressions ─────────────────────────────────
PRESETS: dict[str, str] = {
    "every_5m": "*/5 * * * *",
    "every_1h": "0 * * * *",
    "daily_9am": "0 9 * * *",
    "weekly_mon_9am": "0 9 * * 1",
    "monthly_1st": "0 9 1 * *",
}

# ---------------------------------------------------------------------------
# Simple cron matcher (no external dependencies)
# ---------------------------------------------------------------------------


def _parse_cron_field(field: str, value: int, ranges: tuple[int, int]) -> bool:
    """Return True if *value* matches a single cron *field*.

    Supports ``*``, ``*/N``, ``N``, ``N-M``, and ``N,M`` syntax.
    """
    lo, hi = ranges

    for part in field.split(","):
        part = part.strip()
        if part == "*":
            return True
        try:
            if part.startswith("*/"):
                step = int(part[2:])
                if step <= 0:
                    continue
                return value % step == 0
            if "-" in part:
                a, b = part.split("-", 1)
                if int(a) <= value <= int(b):
                    return True
            else:
                if value == int(part):
                    return True
        except (ValueError, ZeroDivisionError):
            continue
    return False


def cron_matches(expr: str, dt: datetime | None = None) -> bool:
    """Return True if *dt* (default: now) matches the 5-field cron *expr*.

    Fields: minute  hour  day-of-month  month  day-of-week (0=Sun).
    """
    if dt is None:
        dt = datetime.now()

    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 fields): {expr!r}")

    minute, hour, dom, month, dow = parts

    return (
        _parse_cron_field(minute, dt.minute, (0, 59))
        and _parse_cron_field(hour, dt.hour, (0, 23))
        and _parse_cron_field(dom, dt.day, (1, 31))
        and _parse_cron_field(month, dt.month, (1, 12))
        and _parse_cron_field(dow, dt.weekday() + 1 if dt.weekday() != 6 else 0, (0, 6))
    )


def resolve_cron(schedule: str) -> str:
    """Convert a preset name to its cron expression, or return as-is."""
    return PRESETS.get(schedule, schedule)


# ---------------------------------------------------------------------------
# Next-run calculator
# ---------------------------------------------------------------------------


def _next_run_after(cron_expr: str, after: datetime | None = None) -> datetime:
    """Brute-force find the next datetime matching *cron_expr* after *after*.

    Scans minute-by-minute for up to 2 years (covers monthly/annual schedules).
    """
    if after is None:
        after = datetime.now()
    probe = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = probe + timedelta(days=730)
    while probe < limit:
        if cron_matches(cron_expr, probe):
            return probe
        probe += timedelta(minutes=1)
    return after + timedelta(days=730)


# ---------------------------------------------------------------------------
# TaskScheduler
# ---------------------------------------------------------------------------


class TaskScheduler:
    """Cron-like task scheduler for Sentinel Desktop.

    Parameters
    ----------
    engine:
        Optional :class:`AgentEngine` instance used to execute tasks.
        If ``None``, only tasks that don't require the engine can run.
    tasks_path:
        File path for JSON persistence. Defaults to
        ``config/scheduled_tasks.json``.
    """

    def __init__(
        self,
        engine: Any | None = None,
        tasks_path: str | None = None,
    ) -> None:
        self.engine = engine
        self._tasks_path = Path(tasks_path) if tasks_path else DEFAULT_TASKS_PATH
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._on_task_complete: Callable[[dict[str, Any]], None] | None = None

        # Load persisted tasks on init
        self.load()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._running:
            logger.warning("Scheduler is already running.")
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._scheduler_loop, name="sentinel-scheduler", daemon=True)
        self._thread.start()
        logger.info("Scheduler started (check interval=%ds).", CHECK_INTERVAL)

    def stop(self) -> None:
        """Stop the background scheduler thread and persist tasks."""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        self.save()
        logger.info("Scheduler stopped.")

    # ── Task CRUD ───────────────────────────────────────────────────────

    def add_task(
        self,
        name: str,
        task_type: str,
        schedule: str,
        *,
        path: str | None = None,
        goal: str | None = None,
        command: str | None = None,
        params: dict[str, Any] | None = None,
        on_complete: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create and register a new scheduled task.

        Returns the full task dict (with generated ``id`` and timestamps).
        """
        task_type = task_type.lower()
        if task_type not in VALID_TASK_TYPES:
            raise ValueError(f"Invalid task type {task_type!r}; expected one of {VALID_TASK_TYPES}")

        cron_expr = resolve_cron(schedule)
        # Validate the cron expression
        cron_matches(cron_expr, datetime.now())

        now = datetime.now()
        task: dict[str, Any] = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "type": task_type,
            "path": path,
            "goal": goal,
            "command": command,
            "schedule": schedule,
            "cron_expr": cron_expr,
            "enabled": enabled,
            "last_run": None,
            "next_run": _next_run_after(cron_expr, now).isoformat(),
            "params": params or {},
            "on_complete": on_complete,
            "created": now.isoformat(),
        }

        with self._lock:
            self._tasks[task["id"]] = task

        self.save()
        logger.info("Task added: %s (%s) [%s]", name, task_type, task["id"])
        return dict(task)

    def remove_task(self, task_id: str) -> bool:
        """Remove a task by its ID. Returns True if found and removed."""
        with self._lock:
            removed = self._tasks.pop(task_id, None)
        if removed is None:
            logger.warning("remove_task: task %s not found.", task_id)
            return False
        self.save()
        logger.info("Task removed: %s (%s)", removed["name"], task_id)
        return True

    def update_task(self, task_id: str, **updates: Any) -> dict[str, Any] | None:
        """Update fields of an existing task. Returns the updated task or None."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None

            # Validate type if being changed
            if "type" in updates:
                t = updates["type"].lower()
                if t not in VALID_TASK_TYPES:
                    raise ValueError(f"Invalid task type: {t!r}")
                updates["type"] = t

            # Recompute cron if schedule changed
            if "schedule" in updates:
                cron_expr = resolve_cron(updates["schedule"])
                cron_matches(cron_expr, datetime.now())  # validate
                updates["cron_expr"] = cron_expr
                updates["next_run"] = _next_run_after(cron_expr).isoformat()

            task.update(updates)

        self.save()
        logger.info("Task updated: %s (%s)", task["name"], task_id)
        return dict(task)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Return a single task dict by ID, or None."""
        with self._lock:
            task = self._tasks.get(task_id)
        return dict(task) if task else None

    def list_tasks(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """Return all tasks, optionally filtered to enabled only."""
        with self._lock:
            tasks = list(self._tasks.values())
        if enabled_only:
            tasks = [t for t in tasks if t.get("enabled", True)]
        return [dict(t) for t in tasks]

    def enable_task(self, task_id: str) -> bool:
        """Enable a task. Returns True if found."""
        return self._set_enabled(task_id, True)

    def disable_task(self, task_id: str) -> bool:
        """Disable a task. Returns True if found."""
        return self._set_enabled(task_id, False)

    # ── Immediate execution ─────────────────────────────────────────────

    def run_task_now(self, task_id: str) -> dict[str, Any] | None:
        """Execute a task immediately, regardless of schedule.

        Returns a result dict with ``success``, ``output``, and ``error`` keys,
        or None if the task was not found.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            # Snapshot so we don't hold the lock during execution
            task_copy = dict(task)

        result = self._execute_task(task_copy)

        # Update last_run and recompute next_run
        now = datetime.now()
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["last_run"] = now.isoformat()
                cron_expr = self._tasks[task_id].get("cron_expr", "")
                self._tasks[task_id]["next_run"] = _next_run_after(cron_expr, now).isoformat()

        self.save()
        return result

    # ── Callbacks ───────────────────────────────────────────────────────

    def set_on_task_complete(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register *callback* invoked after every task execution (success or fail).

        The callback receives the result dict from ``_execute_task``.
        """
        self._on_task_complete = callback

    # ── Persistence ─────────────────────────────────────────────────────

    def save(self) -> None:
        """Persist all tasks to the JSON file."""
        try:
            self._tasks_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Failed to create tasks directory %s", self._tasks_path.parent)
            return
        with self._lock:
            data = list(self._tasks.values())
        try:
            self._tasks_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.exception("Failed to save tasks to %s", self._tasks_path)

    def load(self) -> None:
        """Load tasks from the JSON file (replaces in-memory state)."""
        if not self._tasks_path.exists():
            self._tasks.clear()
            return
        try:
            raw = self._tasks_path.read_text(encoding="utf-8")
            items = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load tasks from %s", self._tasks_path)
            return

        if not isinstance(items, list):
            logger.error("Task file %s is not a JSON array.", self._tasks_path)
            return

        with self._lock:
            self._tasks.clear()
            for item in items:
                if isinstance(item, dict) and "id" in item:
                    # Ensure cron_expr exists (back-compat with older files)
                    if "cron_expr" not in item:
                        item["cron_expr"] = resolve_cron(item.get("schedule", ""))
                    self._tasks[item["id"]] = item

        logger.info("Loaded %d task(s) from %s.", len(self._tasks), self._tasks_path)

    # ── Internal helpers ────────────────────────────────────────────────

    def _set_enabled(self, task_id: str, value: bool) -> bool:
        """Enable or disable a scheduled task by ID and persist the change.

        Returns ``True`` if the task was found, ``False`` otherwise.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task["enabled"] = value
        self.save()
        logger.info("Task %s %s.", task_id, "enabled" if value else "disabled")
        return True

    def _execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a single task to the appropriate executor.

        Returns ``{success, output, error, task_id, task_name}``.
        """
        task_type = task.get("type", "")
        base = {
            "success": False,
            "output": None,
            "error": None,
            "task_id": task["id"],
            "task_name": task.get("name", ""),
        }
        try:
            if task_type in ("script", "workflow"):
                return self._exec_script(task)
            elif task_type == "goal":
                return self._exec_goal(task)
            elif task_type == "powershell":
                return self._exec_powershell(task)
            base["error"] = f"Unknown task type: {task_type!r}"
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            base["error"] = f"{type(exc).__name__}: {exc}"
            logger.exception("Task %s raised an exception.", task.get("id"))
        return base

    def _exec_script(self, task: dict[str, Any]) -> dict[str, Any]:
        """Run a pre-built IT-support script via the engine's script runner."""
        r = {
            "success": False,
            "output": None,
            "error": "No engine available.",
            "task_id": task["id"],
            "task_name": task.get("name", ""),
        }
        if self.engine and hasattr(self.engine, "script_engine"):
            try:
                sr = self.engine.script_engine.run_script(task.get("path", ""), task.get("params", {}))
                r.update(
                    success=sr.success,
                    error=sr.error,
                    output={
                        "steps_completed": sr.steps_completed,
                        "steps_total": sr.steps_total,
                        "duration_ms": sr.duration_ms,
                    },
                )
            except (RuntimeError, OSError, ValueError, KeyError) as exc:
                r["error"] = f"Script execution failed: {exc}"
                logger.exception("Script execution failed for task %s", task.get("id"))
        return r

    def _exec_goal(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a free-form natural-language goal through the agent engine."""
        r = {
            "success": False,
            "output": None,
            "error": "No engine available.",
            "task_id": task["id"],
            "task_name": task.get("name", ""),
        }
        goal = task.get("goal", "")
        if not goal:
            r["error"] = "Task has no goal specified."
        elif self.engine and hasattr(self.engine, "run"):
            try:
                er = self.engine.run(goal)
                r.update(success=er.get("success", True), output=er, error=er.get("error"))
            except (RuntimeError, OSError, ValueError, KeyError) as exc:
                r["error"] = f"Goal execution failed: {exc}"
                logger.exception("Goal execution failed for task %s", task.get("id"))
        return r

    def _exec_powershell(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a PowerShell command via the engine's powershell runner."""
        r = {
            "success": False,
            "output": None,
            "error": "No engine available.",
            "task_id": task["id"],
            "task_name": task.get("name", ""),
        }
        if self.engine and hasattr(self.engine, "powershell"):
            ps = self.engine.powershell
            sp = task.get("path")
            cmd = task.get("command", "")
            try:
                if sp:
                    pr = ps.run_script(sp)
                elif cmd:
                    pr = ps.run_command(cmd)
                else:
                    r["error"] = "PowerShell task needs 'path' or 'command'."
                    return r
                r.update(
                    success=pr.success,
                    error=pr.stderr or None,
                    output={"exit_code": pr.exit_code, "stdout": pr.stdout, "objects": pr.objects},
                )
            except (RuntimeError, OSError, ValueError) as exc:
                r["error"] = f"PowerShell execution failed: {exc}"
                logger.exception("PowerShell execution failed for task %s", task.get("id"))
        return r

    def _handle_on_complete(self, task: dict[str, Any], result: dict[str, Any]) -> None:
        """Process the ``on_complete`` directive of a task."""
        directive = task.get("on_complete")
        if not directive:
            return
        directive = directive.lower().strip()
        if directive == "disable":
            self.disable_task(task["id"])
            logger.info("Task %s auto-disabled after completion.", task["id"])
        elif directive == "remove":
            self.remove_task(task["id"])
            logger.info("Task %s auto-removed after completion.", task["id"])
        # Future: "notify", "chain:task_id", etc.

    # ── Scheduler loop (background thread) ──────────────────────────────

    def _scheduler_loop(self) -> None:
        """Main loop: wake every CHECK_INTERVAL and run due tasks."""
        logger.debug("Scheduler loop entered.")
        while not self._stop_event.is_set():
            try:
                self._tick()
            except (RuntimeError, OSError, ValueError) as exc:
                logger.exception("Unexpected error in scheduler tick: %s", exc)
            self._stop_event.wait(CHECK_INTERVAL)
        logger.debug("Scheduler loop exited.")

    def _tick(self) -> None:
        """Check all enabled tasks and execute any that are due."""
        now = datetime.now()
        now_iso = now.isoformat()
        tasks_to_run: list[dict[str, Any]] = []

        with self._lock:
            for task in list(self._tasks.values()):
                if not task.get("enabled", True):
                    continue
                cron_expr = task.get("cron_expr", "")
                if not cron_expr:
                    continue
                try:
                    if cron_matches(cron_expr, now):
                        tasks_to_run.append(dict(task))
                except ValueError as exc:
                    logger.warning("Invalid cron for task %s: %s (%s)", task["id"], cron_expr, exc)

        for task in tasks_to_run:
            logger.info("Running scheduled task: %s (%s)", task["name"], task["id"])
            result = self._execute_task(task)

            # Update last_run / next_run
            with self._lock:
                tid = task["id"]
                if tid in self._tasks:
                    self._tasks[tid]["last_run"] = now_iso
                    cron_expr = self._tasks[tid].get("cron_expr", "")
                    try:
                        self._tasks[tid]["next_run"] = _next_run_after(cron_expr, now).isoformat()
                    except ValueError as exc:
                        logger.warning("Failed to compute next_run for task %s: %s", tid, exc)
                        self._tasks[tid]["next_run"] = None

            self._handle_on_complete(task, result)

            if self._on_task_complete is not None:
                try:
                    self._on_task_complete(result)
                except (RuntimeError, OSError, ValueError) as exc:
                    logger.exception("on_task_complete callback raised: %s", exc)

        if tasks_to_run:
            self.save()
