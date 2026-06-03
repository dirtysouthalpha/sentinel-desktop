"""Sentinel Desktop v3.0 — Workflow Engine.

Multi-step workflow execution with conditions, loops, and variables.

Chain scripts, actions, and sub-workflows with control flow.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Expected number of parts in a step reference (e.g., ["step", "s1", "output.field"])
_STEP_REF_PARTS_MIN = 3


class StepType(str, Enum):
    """Enumeration of workflow step types.

    Defines the kinds of operations a workflow step can perform,
    from running scripts to evaluating conditions.
    """

    SCRIPT = "script"
    ACTION = "action"
    CONDITION = "condition"
    LOOP = "loop"
    SUB_WORKFLOW = "sub_workflow"
    DELAY = "delay"
    NOTIFY = "notify"


class ErrorPolicy(str, Enum):
    """Policy for handling errors during workflow step execution."""

    STOP = "stop"
    SKIP = "skip"
    RETRY = "retry"


@dataclass
class WorkflowResult:
    """Result of a completed workflow run.

    Tracks success status, step counts, timing, and per-step outputs.
    """

    success: bool = False
    steps_completed: int = 0
    steps_total: int = 0
    error: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    step_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkflowStep:
    """A single step within a workflow definition.

    Each step has a type (script, action, condition, etc.), optional
    parameters, and control-flow links for branching.
    """

    id: str
    type: str
    path: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    action: dict[str, Any] | None = None
    check: str | None = None
    true_next: str | None = None
    false_next: str | None = None
    over: str | None = None
    body_step: str | None = None
    delay_seconds: float = 0.0
    message: str = ""
    level: str = "info"
    error_policy: str = "stop"
    max_retries: int = 0
    next_step: str | None = None


class WorkflowEngine:
    """Execute multi-step workflows with conditions, loops, and variables."""

    def __init__(self, action_executor: Any = None, script_engine: Any = None) -> None:
        """Initialize the workflow engine.

        Args:
            action_executor: :class:`ActionExecutor` used to run individual
                steps. Pass ``None`` to create a standalone engine that
                only evaluates workflow logic.
            script_engine: Optional :class:`ScriptEngine` for script-type
                workflow steps.

        """
        self.executor = action_executor
        self.script_engine = script_engine
        self._variables: dict[str, Any] = {}
        self._step_outputs: dict[str, Any] = {}
        self._callbacks: dict[str, Callable[..., Any]] = {}

    def set_callback(self, event: str, fn: Callable[..., Any]) -> None:
        """Register a callback function for a named workflow event."""
        self._callbacks[event] = fn

    def _fire(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Invoke the callback registered for *event*, if any, swallowing errors."""
        cb = self._callbacks.get(event)
        if cb:
            try:
                cb(*args, **kwargs)
            except (RuntimeError, OSError, ValueError) as exc:
                logger.warning("Callback %s error: %s", event, exc)

    @staticmethod
    def resolve_variables(
        text: str, variables: dict[str, Any], step_outputs: dict[str, Any],
    ) -> str:
        """Replace {{var}} and {{step.sN.output.field}} references."""
        if not isinstance(text, str):
            return text

        def _replacer(match: re.Match[str]) -> str:
            """Resolve a ``{{…}}`` placeholder inside a workflow step template."""
            ref = match.group(1).strip()

            # Step output reference: step.s1.output.field or step.s1.success
            if ref.startswith("step."):
                parts = ref.split(".", 2)
                step_id = parts[1]
                step_data = step_outputs.get(step_id, {})
                if len(parts) >= _STEP_REF_PARTS_MIN:
                    # Navigate nested keys
                    keys = parts[2].split(".")
                    val = step_data
                    for k in keys:
                        if isinstance(val, dict):
                            val = val.get(k, "")
                        else:
                            val = ""
                            break
                    return str(val) if val is not None else ""
                return str(step_data)

            # Simple variable
            val = variables.get(ref, "")
            return str(val) if val is not None else ""

        return re.sub(r"\{\{(.+?)\}\}", _replacer, text)

    @staticmethod
    def evaluate_condition(expression: str) -> bool:
        """Evaluate a condition expression."""
        expr = expression.strip().lower()

        if expr in ("true", "yes", "1", "success"):
            return True
        if expr in ("false", "no", "0", "failed"):
            return False

        for op in ("!=", "==", ">=", "<=", ">", "<", "contains"):
            if op in expr:
                parts = expr.split(op, 1)
                left = parts[0].strip()
                right = parts[1].strip()
                return WorkflowEngine._evaluate_comparison(op, left, right)

        return False

    @staticmethod
    def _evaluate_comparison(op: str, left: str, right: str) -> bool:
        """Evaluate a single comparison operation."""
        result = False

        # Handle string and equality operations
        if op == "==":
            result = left == right
        elif op == "!=":
            result = left != right
        elif op == "contains":
            result = right in left
        else:
            # Handle numeric operations
            try:
                left_num = float(left)
                right_num = float(right)
                if op == ">":
                    result = left_num > right_num
                elif op == "<":
                    result = left_num < right_num
                elif op == ">=":
                    result = left_num >= right_num
                elif op == "<=":
                    result = left_num <= right_num
                else:
                    logger.debug("Unknown comparison operator '%s'", op)
                    result = False
            except ValueError:
                logger.debug("Non-numeric comparison '%s' %s '%s'", left, op, right)
                result = False

        return result

    def run_workflow(self, path: str, variables: dict[str, Any] | None = None) -> WorkflowResult:
        """Execute a workflow from a JSON file.

        Orchestrates loading, validation, step execution, and finalization.
        Returns a WorkflowResult indicating overall success or failure.
        """
        start_time = time.time()

        loaded = self._validate_and_load_workflow(path, variables)
        if isinstance(loaded, WorkflowResult):
            return loaded

        steps, result = loaded
        self._execute_step_chain(steps, result)
        self._finalize_workflow(result, start_time)
        return result

    def _validate_and_load_workflow(
        self, path: str, variables: dict[str, Any] | None,
    ) -> tuple[list[WorkflowStep], WorkflowResult] | WorkflowResult:
        """Load, validate, and prepare a workflow for execution.

        Reads the workflow JSON file, checks that steps are defined,
        merges variables, and builds step objects. Returns a tuple of
        (steps, result) on success, or a WorkflowResult describing the
        load/validation error.
        """
        wf_data = self._load_workflow_file(path)
        if isinstance(wf_data, WorkflowResult):
            return wf_data

        steps_data = wf_data.get("steps", [])
        if not steps_data:
            return WorkflowResult(success=False, error="No steps in workflow")

        # Initialize execution context
        self._variables = {**wf_data.get("variables", {}), **(variables or {})}
        self._step_outputs = {}
        steps = self._build_steps(steps_data)
        result = WorkflowResult(steps_total=len(steps))
        return steps, result

    def _execute_step_chain(
        self, steps: list[WorkflowStep], result: WorkflowResult,
    ) -> None:
        """Execute the workflow step chain with cycle detection.

        Walks through steps by resolving the next-step pointer after each
        execution. Non-loop cycles are detected and broken. Errors are
        handled according to each step's error_policy.
        """
        step_map = {s.id: s for s in steps}
        current = steps[0].id if steps else None
        visited: set[str] = set()

        while current and current in step_map:
            if current in visited and step_map[current].type != StepType.LOOP:
                logger.warning("Cycle detected at step %s, stopping", current)
                break
            visited.add(current)

            step = step_map[current]
            self._fire("on_step_start", step.id)
            logger.info("Workflow step [%s] type=%s", step.id, step.type)

            try:
                step_result = self._execute_step(step)
                result.steps_completed += 1
                result.step_results.append(step_result)
                self._step_outputs[step.id] = step_result
                self._fire("on_step_complete", step.id, step_result)

                current = self._resolve_next_step(step, step_map)

            except (RuntimeError, OSError, ValueError, KeyError) as exc:
                logger.exception("Step [%s] failed", step.id)
                current = self._handle_step_error(step, exc, result)
                if current is None:
                    break

    def _finalize_workflow(
        self, result: WorkflowResult, start_time: float,
    ) -> None:
        """Set final outputs, success flag, elapsed time, and fire completion callback."""
        result.outputs = dict(self._step_outputs)
        result.success = not result.error
        result.elapsed_seconds = time.time() - start_time
        self._fire("on_workflow_complete", result)

    def _load_workflow_file(self, path: str) -> dict[str, Any] | WorkflowResult:
        """Load and parse a workflow JSON file.

        Returns the parsed dict on success, or a WorkflowResult on failure.
        """
        if not Path(path).exists():
            return WorkflowResult(success=False, error=f"Workflow not found: {path}")

        try:
            with Path(path).open(encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError) as exc:
            return WorkflowResult(success=False, error=f"Failed to load workflow: {exc}")

    @staticmethod
    def _build_steps(steps_data: list[dict[str, Any]]) -> list[WorkflowStep]:
        """Convert raw step dicts into WorkflowStep objects."""
        steps: list[WorkflowStep] = []
        for s in steps_data:
            steps.append(
                WorkflowStep(
                    id=s.get("id", f"s{len(steps) + 1}"),
                    type=s.get("type", "action"),
                    path=s.get("path"),
                    params=s.get("params", {}),
                    action=s.get("action"),
                    check=s.get("check"),
                    true_next=s.get("true_next"),
                    false_next=s.get("false_next"),
                    over=s.get("over"),
                    body_step=s.get("body_step"),
                    delay_seconds=s.get("delay_seconds", 0),
                    message=s.get("message", ""),
                    level=s.get("level", "info"),
                    error_policy=s.get("error_policy", "stop"),
                    max_retries=s.get("max_retries", 0),
                    next_step=s.get("next_step"),
                ),
            )
        return steps

    def _resolve_next_step(
        self,
        step: WorkflowStep,
        step_map: dict[str, WorkflowStep],
    ) -> str | None:
        """Determine the next step ID after a successful step execution.

        For conditions, evaluates the check expression and follows true_next/false_next.
        For loops, iterates over the resolved list and executes the body step.
        Returns the next step ID, or the step's default next_step otherwise.
        """
        next_id = step.next_step

        if step.type == StepType.CONDITION:
            expr = self.resolve_variables(
                step.check or "", self._variables, self._step_outputs,
            )
            cond_result = self.evaluate_condition(expr)
            next_id = step.true_next if cond_result else step.false_next
            logger.info("Condition [%s] = %s → next=%s", expr, cond_result, next_id)

        elif step.type == StepType.LOOP:
            over_ref = self.resolve_variables(
                step.over or "", self._variables, self._step_outputs,
            )
            items = self._parse_list(over_ref)
            body = step_map.get(step.body_step)  # type: ignore[arg-type]
            if body and items:
                loop_success = True
                for idx, item in enumerate(items):
                    self._variables["loop_item"] = item
                    self._variables["loop_index"] = idx
                    try:
                        lr = self._execute_step(body)
                        self._step_outputs[f"{step.id}_loop_{idx}"] = lr
                    except (RuntimeError, OSError, ValueError) as exc:
                        logger.warning("Loop step %s failed: %s", step.id, exc)
                        if body.error_policy == "stop":
                            loop_success = False
                            break
                self._step_outputs[step.id] = {
                    "success": loop_success,
                    "items_processed": len(items),
                }

        return next_id

    def _handle_step_error(
        self,
        step: WorkflowStep,
        exc: Exception,
        result: WorkflowResult,
    ) -> str | None:
        """Handle a step execution error based on the step's error policy.

        Returns the next step ID to continue with, or None to stop the workflow.
        """
        result.step_results.append({"success": False, "error": str(exc)})

        if step.error_policy == "stop":
            result.error = f"Step {step.id} failed: {exc}"
            return None

        if step.error_policy == "skip":
            return step.next_step

        if step.error_policy == "retry":
            retries = 0
            retried = False
            while retries < step.max_retries:
                retries += 1
                logger.info(
                    "Retrying step [%s] attempt %d/%d", step.id, retries, step.max_retries,
                )
                try:
                    sr = self._execute_step(step)
                    self._step_outputs[step.id] = sr
                    result.step_results[-1] = sr
                    retried = True
                    break
                except (RuntimeError, OSError, ValueError, KeyError) as retry_exc:
                    logger.warning(
                        "Step retry %d/%d failed: %s", retries, step.max_retries, retry_exc,
                    )
                    time.sleep(0.5)
            if not retried:
                result.error = f"Step {step.id} failed after {step.max_retries} retries"
                return None
            return step.next_step

        return None

    def _execute_step(self, step: WorkflowStep) -> dict[str, Any]:
        """Execute a single workflow step."""
        result = {}

        if step.type == StepType.SCRIPT:
            result = self._exec_script(step)
        elif step.type == StepType.ACTION:
            result = self._exec_action(step)
        elif step.type == StepType.CONDITION:
            result = {"success": True, "type": "condition"}
        elif step.type == StepType.LOOP:
            result = {"success": True, "type": "loop"}
        elif step.type == StepType.SUB_WORKFLOW:
            result = self._exec_sub_workflow(step)
        elif step.type == StepType.DELAY:
            seconds = max(0.0, min(step.delay_seconds, 3600.0))
            time.sleep(seconds)
            result = {"success": True, "type": "delay", "seconds": seconds}
        elif step.type == StepType.NOTIFY:
            result = self._exec_notify(step)
        else:
            result = {"success": False, "error": f"Unknown step type: {step.type}"}

        return result

    def _exec_script(self, step: WorkflowStep) -> dict[str, Any]:
        """Run a recorded script."""
        if not self.script_engine:
            return {"success": False, "error": "No script engine available"}

        path = self.resolve_variables(step.path or "", self._variables, self._step_outputs)
        params = {}
        for k, v in step.params.items():
            params[k] = self.resolve_variables(str(v), self._variables, self._step_outputs)

        try:
            result = self.script_engine.run_script(path, params or None)
            return {
                "success": result.success,
                "steps_completed": result.steps_completed,
                "steps_total": result.steps_total,
                "error": result.error,
            }
        except (RuntimeError, OSError, ValueError) as exc:
            logger.exception("Script execution failed in step %s", step.id)
            return {"success": False, "error": f"Script execution failed: {exc}"}

    def _exec_action(self, step: WorkflowStep) -> dict[str, Any]:
        """Execute a single action via the action executor."""
        if not self.executor:
            return {"success": False, "error": "No action executor available"}

        action = dict(step.action) if step.action else {}
        for k, v in action.items():
            if isinstance(v, str):
                action[k] = self.resolve_variables(v, self._variables, self._step_outputs)

        try:
            return self.executor.execute_sync(action)
        except (RuntimeError, OSError, ValueError, KeyError):
            logger.exception("Action execution failed in step %s", step.id)
            raise

    def _exec_sub_workflow(self, step: WorkflowStep) -> dict[str, Any]:
        """Run a nested workflow."""
        path = self.resolve_variables(step.path or "", self._variables, self._step_outputs)
        params = {}
        for k, v in step.params.items():
            params[k] = self.resolve_variables(str(v), self._variables, self._step_outputs)

        try:
            sub_result = self.run_workflow(path, params or None)
            return {
                "success": sub_result.success,
                "steps_completed": sub_result.steps_completed,
                "steps_total": sub_result.steps_total,
                "error": sub_result.error,
            }
        except (RuntimeError, OSError, ValueError) as exc:
            logger.exception("Sub-workflow execution failed in step %s", step.id)
            return {"success": False, "error": f"Sub-workflow failed: {exc}"}

    def _exec_notify(self, step: WorkflowStep) -> dict[str, Any]:
        """Send a notification."""
        try:
            from core.notifications import NotificationManager

            nm = NotificationManager()
            msg = self.resolve_variables(step.message, self._variables, self._step_outputs)
            nm.notify(title="Workflow", message=msg, level=step.level)
            return {"success": True, "type": "notify"}
        except (ImportError, OSError, RuntimeError):
            logger.exception("Notify step failed, logging message instead")
            logger.info("Notify step: %s", step.message)
            return {"success": True, "type": "notify", "note": "notification delivery failed"}

    @staticmethod
    def _parse_list(value: Any) -> list[Any]:
        """Parse a value into a list."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return [v.strip() for v in value.split(",") if v.strip()]
        return [value] if value else []

    @staticmethod
    def save_workflow(path: str, workflow_data: dict[str, Any]) -> None:
        """Save a workflow definition to JSON."""
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8") as f:
                json.dump(workflow_data, f, indent=2, ensure_ascii=False)
        except (OSError, TypeError):
            logger.exception("Failed to save workflow to %s", path)
            raise

    @staticmethod
    def list_workflows(directory: str = "workflows") -> list[dict[str, Any]]:
        """List all workflow files in a directory."""
        workflows: list[dict[str, Any]] = []
        dir_path = Path(directory)
        if not dir_path.is_dir():
            return workflows
        for filepath in sorted(dir_path.iterdir()):
            if filepath.suffix != ".json":
                continue
            try:
                with filepath.open(encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                workflows.append(
                    {
                        "name": data.get("name", filepath.name),
                        "description": data.get("description", ""),
                        "path": str(filepath),
                        "steps": len(data.get("steps", [])),
                        "variables": list(data.get("variables", {}).keys()),
                    },
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping invalid workflow %s: %s", filepath, exc)
        return workflows
