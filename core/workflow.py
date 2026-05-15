"""
Sentinel Desktop v3.0 — Workflow Engine
Multi-step workflow execution with conditions, loops, and variables.

Chain scripts, actions, and sub-workflows with control flow.
"""

import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class StepType(str, Enum):
    SCRIPT = "script"
    ACTION = "action"
    CONDITION = "condition"
    LOOP = "loop"
    SUB_WORKFLOW = "sub_workflow"
    DELAY = "delay"
    NOTIFY = "notify"


class ErrorPolicy(str, Enum):
    STOP = "stop"
    SKIP = "skip"
    RETRY = "retry"


@dataclass
class WorkflowResult:
    success: bool = False
    steps_completed: int = 0
    steps_total: int = 0
    error: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    step_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WorkflowStep:
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
        self.executor = action_executor
        self.script_engine = script_engine
        self._variables: dict[str, Any] = {}
        self._step_outputs: dict[str, Any] = {}
        self._callbacks: dict[str, Callable[..., Any]] = {}

    def set_callback(self, event: str, fn: Callable[..., Any]) -> None:
        self._callbacks[event] = fn

    def _fire(self, event: str, *args: Any, **kwargs: Any) -> None:
        cb = self._callbacks.get(event)
        if cb:
            try:
                cb(*args, **kwargs)
            except Exception as exc:
                logger.warning("Callback %s error: %s", event, exc)

    @staticmethod
    def resolve_variables(
        text: str, variables: dict[str, Any], step_outputs: dict[str, Any]
    ) -> str:
        """Replace {{var}} and {{step.sN.output.field}} references."""
        if not isinstance(text, str):
            return text

        def _replacer(match: re.Match) -> str:
            ref = match.group(1).strip()

            # Step output reference: step.s1.output.field or step.s1.success
            if ref.startswith("step."):
                parts = ref.split(".", 2)
                if len(parts) >= 2:
                    step_id = parts[1]
                    step_data = step_outputs.get(step_id, {})
                    if len(parts) >= 3:
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

        # Comparison operators
        for op in ("!=", "==", ">=", "<=", ">", "<", "contains"):
            if op in expr:
                parts = expr.split(op, 1)
                left = parts[0].strip()
                right = parts[1].strip()
                if op == "==":
                    return left == right
                elif op == "!=":
                    return left != right
                elif op == "contains":
                    return right in left
                elif op == ">":
                    try:
                        return float(left) > float(right)
                    except ValueError:
                        return False
                elif op == "<":
                    try:
                        return float(left) < float(right)
                    except ValueError:
                        return False
                elif op == ">=":
                    try:
                        return float(left) >= float(right)
                    except ValueError:
                        return False
                elif op == "<=":
                    try:
                        return float(left) <= float(right)
                    except ValueError:
                        return False

        return bool(expr)

    def run_workflow(self, path: str, variables: dict[str, Any] | None = None) -> WorkflowResult:
        """Execute a workflow from a JSON file."""
        start_time = time.time()

        if not os.path.exists(path):
            return WorkflowResult(success=False, error=f"Workflow not found: {path}")

        try:
            with open(path, encoding="utf-8") as f:
                wf_data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            return WorkflowResult(success=False, error=f"Failed to load workflow: {exc}")

        steps_data = wf_data.get("steps", [])
        if not steps_data:
            return WorkflowResult(success=False, error="No steps in workflow")

        # Merge variables
        self._variables = {**wf_data.get("variables", {}), **(variables or {})}
        self._step_outputs = {}

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
                )
            )

        result = WorkflowResult(
            steps_total=len(steps),
        )

        # Execute steps in order, following condition branches
        step_map = {s.id: s for s in steps}
        current = steps[0].id if steps else None
        visited = set()

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

                # Determine next step
                next_id = step.next_step

                if step.type == StepType.CONDITION:
                    expr = self.resolve_variables(
                        step.check or "", self._variables, self._step_outputs
                    )
                    cond_result = self.evaluate_condition(expr)
                    next_id = step.true_next if cond_result else step.false_next
                    logger.info("Condition [%s] = %s → next=%s", expr, cond_result, next_id)

                elif step.type == StepType.LOOP:
                    over_ref = self.resolve_variables(
                        step.over or "", self._variables, self._step_outputs
                    )
                    items = self._parse_list(over_ref)
                    body = step_map.get(step.body_step)  # type: ignore[arg-type]
                    if body and items:
                        loop_success = True
                        for item in items:
                            self._variables["loop_item"] = item
                            self._variables["loop_index"] = items.index(item)
                            try:
                                lr = self._execute_step(body)
                                self._step_outputs[f"{step.id}_loop_{items.index(item)}"] = lr
                            except Exception as exc:
                                logger.debug("Loop step %s failed: %s", step.id, exc)
                                if body.error_policy == "stop":
                                    loop_success = False
                                    break
                        self._step_outputs[step.id] = {
                            "success": loop_success,
                            "items_processed": len(items),
                        }

                current = next_id

            except Exception as exc:
                logger.error("Step [%s] failed: %s", step.id, exc)
                result.step_results.append({"success": False, "error": str(exc)})

                if step.error_policy == "stop":
                    result.error = f"Step {step.id} failed: {exc}"
                    break
                elif step.error_policy == "skip":
                    current = step.next_step
                    continue
                elif step.error_policy == "retry":
                    retries = 0
                    retried = False
                    while retries < step.max_retries:
                        retries += 1
                        logger.info(
                            "Retrying step [%s] attempt %d/%d", step.id, retries, step.max_retries
                        )
                        try:
                            sr = self._execute_step(step)
                            self._step_outputs[step.id] = sr
                            result.step_results[-1] = sr
                            retried = True
                            break
                        except Exception as exc:
                            logger.debug(
                                "Step retry %d/%d failed: %s", retries, step.max_retries, exc
                            )
                            time.sleep(0.5)
                    if not retried:
                        result.error = f"Step {step.id} failed after {step.max_retries} retries"
                        break
                    current = step.next_step
                    continue

        result.outputs = dict(self._step_outputs)
        result.success = not result.error
        result.elapsed_seconds = time.time() - start_time

        self._fire("on_workflow_complete", result)
        return result

    def _execute_step(self, step: WorkflowStep) -> dict[str, Any]:
        """Execute a single workflow step."""
        if step.type == StepType.SCRIPT:
            return self._exec_script(step)
        elif step.type == StepType.ACTION:
            return self._exec_action(step)
        elif step.type == StepType.CONDITION:
            return {"success": True, "type": "condition"}
        elif step.type == StepType.LOOP:
            return {"success": True, "type": "loop"}
        elif step.type == StepType.SUB_WORKFLOW:
            return self._exec_sub_workflow(step)
        elif step.type == StepType.DELAY:
            time.sleep(step.delay_seconds)
            return {"success": True, "type": "delay", "seconds": step.delay_seconds}
        elif step.type == StepType.NOTIFY:
            return self._exec_notify(step)
        else:
            return {"success": False, "error": f"Unknown step type: {step.type}"}

    def _exec_script(self, step: WorkflowStep) -> dict[str, Any]:
        """Run a recorded script."""
        if not self.script_engine:
            return {"success": False, "error": "No script engine available"}

        path = self.resolve_variables(step.path or "", self._variables, self._step_outputs)
        params = {}
        for k, v in step.params.items():
            params[k] = self.resolve_variables(str(v), self._variables, self._step_outputs)

        result = self.script_engine.run_script(path, params or None)
        return {
            "success": result.success,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "error": result.error,
        }

    def _exec_action(self, step: WorkflowStep) -> dict[str, Any]:
        """Execute a single action via the action executor."""
        if not self.executor:
            return {"success": False, "error": "No action executor available"}

        action = dict(step.action) if step.action else {}
        for k, v in action.items():
            if isinstance(v, str):
                action[k] = self.resolve_variables(v, self._variables, self._step_outputs)

        return self.executor.execute_sync(action)

    def _exec_sub_workflow(self, step: WorkflowStep) -> dict[str, Any]:
        """Run a nested workflow."""
        path = self.resolve_variables(step.path or "", self._variables, self._step_outputs)
        params = {}
        for k, v in step.params.items():
            params[k] = self.resolve_variables(str(v), self._variables, self._step_outputs)

        sub_result = self.run_workflow(path, params or None)
        return {
            "success": sub_result.success,
            "steps_completed": sub_result.steps_completed,
            "steps_total": sub_result.steps_total,
            "error": sub_result.error,
        }

    def _exec_notify(self, step: WorkflowStep) -> dict[str, Any]:
        """Send a notification."""
        try:
            from core.notifications import NotificationManager

            nm = NotificationManager()
            msg = self.resolve_variables(step.message, self._variables, self._step_outputs)
            nm.notify(title="Workflow", message=msg, level=step.level)
            return {"success": True, "type": "notify"}
        except ImportError:
            logger.info("Notify step: %s", step.message)
            return {"success": True, "type": "notify", "note": "notifications module not available"}

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
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(workflow_data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def list_workflows(directory: str = "workflows") -> list[dict[str, Any]]:
        """List all workflow files in a directory."""
        workflows: list[dict[str, Any]] = []
        if not os.path.isdir(directory):
            return workflows
        for fname in sorted(os.listdir(directory)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(directory, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                workflows.append(
                    {
                        "name": data.get("name", fname),
                        "description": data.get("description", ""),
                        "path": fpath,
                        "steps": len(data.get("steps", [])),
                        "variables": list(data.get("variables", {}).keys()),
                    }
                )
            except Exception:
                logger.warning("Skipping invalid workflow: %s", fpath)
        return workflows
