"""
Sentinel Desktop v3.0 — Script replay engine.

Loads recorded script files (JSON), performs parameter substitution,
validates required parameters and action types, then replays each step
through the ActionExecutor with configurable error handling.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ScriptResult:
    """Outcome of a script replay run."""

    success: bool
    steps_completed: int
    steps_total: int
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


@dataclass
class _StepPreview:
    """Lightweight description of what *would* run (used by dry_run)."""

    step_number: int
    action: str
    params: dict[str, Any]
    wait_after_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "action": self.action,
            "params": self.params,
            "wait_after_ms": self.wait_after_ms,
        }


# ---------------------------------------------------------------------------
# Parameter substitution
# ---------------------------------------------------------------------------

_PARAM_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _substitute_params(value: Any, params: dict[str, Any]) -> Any:
    """Replace ``{{param_name}}`` placeholders in *value* using *params*.

    Only strings are scanned; other types are returned unchanged.
    """
    if not isinstance(value, str):
        return value

    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        if key not in params:
            # Leave the placeholder intact if no substitution provided.
            return match.group(0)
        return str(params[key])

    return _PARAM_RE.sub(_replacer, value)


def _substitute_step(step_params: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *step_params* with all placeholders resolved."""
    return {k: _substitute_params(v, params) for k, v in step_params.items()}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _extract_required_params(script: dict[str, Any]) -> set[str]:
    """Scan all steps and return the set of param names inside ``{{…}}``."""
    required: set[str] = set()
    for step in script.get("steps", []):
        for value in step.get("params", {}).values():
            if isinstance(value, str):
                for m in _PARAM_RE.finditer(value):
                    required.add(m.group(1))
    return required


def _validate_script(
    script: dict[str, Any], params: dict[str, Any] | None, executor: Any
) -> list[str]:
    """Return a list of validation error strings (empty == valid)."""
    errors: list[str] = []

    if "steps" not in script or not isinstance(script["steps"], list):
        errors.append("Script must contain a 'steps' list.")
        return errors

    if not script["steps"]:
        errors.append("Script has zero steps.")
        return errors

    # Required parameter coverage
    required = _extract_required_params(script)
    provided = set(params.keys()) if params else set()
    missing = required - provided
    if missing:
        errors.append(f"Missing required parameters: {sorted(missing)}")

    # Action type existence
    known_actions: set[str] | None = None
    if executor is not None and hasattr(executor, "_dispatch_table"):
        known_actions = set(executor._dispatch_table.keys())

    for idx, step in enumerate(script["steps"]):
        if "action" not in step:
            errors.append(f"Step {idx + 1} missing 'action' field.")
            continue
        if known_actions is not None and step["action"] not in known_actions:
            errors.append(f"Step {idx + 1}: unknown action '{step['action']}'.")
        if "params" not in step:
            errors.append(f"Step {idx + 1} missing 'params' field.")

    return errors


# ---------------------------------------------------------------------------
# ScriptEngine
# ---------------------------------------------------------------------------


class ScriptEngine:
    """Replay recorded scripts through an :class:`ActionExecutor`.

    Parameters
    ----------
    action_executor:
        An ``ActionExecutor`` instance used to dispatch each step.
    """

    def __init__(self, action_executor: Any) -> None:
        self._executor = action_executor
        self._progress_callback: Callable[[int, int, str, dict[str, Any]], None] | None = None
        self._on_error: str = "stop"  # 'stop' | 'skip' | 'retry_once'

    # -- configuration ------------------------------------------------------

    def set_progress_callback(
        self,
        fn: Callable[[int, int, str, dict[str, Any]], None],
    ) -> None:
        """Register *fn(step_num, total, action, result)* called after each step."""
        self._progress_callback = fn

    def set_on_error_policy(self, policy: str) -> None:
        """Set error policy: ``'stop'``, ``'skip'``, or ``'retry_once'``."""
        if policy not in ("stop", "skip", "retry_once"):
            raise ValueError(
                f"Invalid on_error policy '{policy}'; expected 'stop', 'skip', or 'retry_once'."
            )
        self._on_error = policy

    # -- public API ---------------------------------------------------------

    def run_script(
        self,
        script_path: str,
        params: dict[str, Any] | None = None,
    ) -> ScriptResult:
        """Load a JSON script from *script_path* and replay it.

        Returns a :class:`ScriptResult` summarising the run.
        """
        path = Path(script_path)
        if not path.is_file():
            return ScriptResult(
                success=False,
                steps_completed=0,
                steps_total=0,
                error=f"Script file not found: {script_path}",
            )
        try:
            script = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            return ScriptResult(
                success=False,
                steps_completed=0,
                steps_total=0,
                error=f"Failed to load script: {exc}",
            )
        return self.run_script_from_dict(script, params)

    def run_script_from_dict(
        self,
        script: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> ScriptResult:
        """Replay a script provided as a *dict*."""
        start = time.monotonic()
        params = params or {}

        # --- validate -------------------------------------------------------
        validation_errors = _validate_script(script, params, self._executor)
        if validation_errors:
            duration_ms = int((time.monotonic() - start) * 1000)
            return ScriptResult(
                success=False,
                steps_completed=0,
                steps_total=len(script.get("steps", [])),
                error="Validation failed: " + "; ".join(validation_errors),
                duration_ms=duration_ms,
            )

        steps: list[dict[str, Any]] = script["steps"]
        total = len(steps)
        results: list[dict[str, Any]] = []
        steps_completed = 0
        first_error: str | None = None
        success = True

        for idx, step in enumerate(steps):
            step_num = idx + 1
            action = step["action"]
            raw_params = step.get("params", {})

            # Parameter substitution
            resolved_params = _substitute_step(raw_params, params)

            # Execute (with optional retry)
            result = self._execute_step(action, resolved_params, step_num)

            # Progress callback
            if self._progress_callback is not None:
                try:
                    self._progress_callback(step_num, total, action, result)
                except Exception:
                    logger.debug("Progress callback raised; ignoring.")

            results.append(result)

            if result.get("success", False):
                steps_completed += 1
            else:
                # Step failed — apply error policy
                success = False
                if first_error is None:
                    first_error = (
                        f"Step {step_num} ({action}) failed: "
                        f"{result.get('output', result.get('error', 'unknown'))}"
                    )
                if self._on_error == "stop":
                    steps_completed += 1  # count the failed step as completed
                    break
                elif self._on_error == "skip":
                    steps_completed += 1
                    continue
                elif self._on_error == "retry_once":
                    steps_completed += 1
                    # Already retried inside _execute_step; continue
                    continue

            # Respect wait_after_ms
            wait_ms = step.get("wait_after_ms", 0)
            if wait_ms > 0:
                time.sleep(wait_ms / 1000.0)

        duration_ms = int((time.monotonic() - start) * 1000)
        return ScriptResult(
            success=success,
            steps_completed=steps_completed,
            steps_total=total,
            results=results,
            error=first_error,
            duration_ms=duration_ms,
        )

    def dry_run(
        self,
        script: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Validate *script* without executing and return the step list.

        Each entry is a dict with ``step_number``, ``action``, ``params``
        (after substitution), and ``wait_after_ms``.

        Raises ``ValueError`` on validation failure.
        """
        params = params or {}
        validation_errors = _validate_script(script, params, self._executor)
        if validation_errors:
            raise ValueError("Script validation failed: " + "; ".join(validation_errors))

        previews: list[dict[str, Any]] = []
        for idx, step in enumerate(script.get("steps", [])):
            resolved = _substitute_step(step.get("params", {}), params)
            preview = _StepPreview(
                step_number=idx + 1,
                action=step["action"],
                params=resolved,
                wait_after_ms=step.get("wait_after_ms", 0),
            )
            previews.append(preview.to_dict())
        return previews

    # -- internal -----------------------------------------------------------

    def _execute_step(
        self,
        action: str,
        params: dict[str, Any],
        step_num: int,
    ) -> dict[str, Any]:
        """Dispatch one step through the executor, retrying once if needed."""
        action_dict = {"action": action, **params}
        try:
            result = self._executor.execute_sync(action_dict)
        except Exception as exc:
            logger.error("Executor raised on step %d (%s): %s", step_num, action, exc)
            return {"success": False, "error": str(exc)}

        if not isinstance(result, dict):
            logger.error("Executor returned non-dict for step %d: %s", step_num, type(result))
            return {
                "success": False,
                "error": f"Executor returned {type(result).__name__}, expected dict",
            }

        if result.get("success", False):
            return result

        # Retry logic
        if self._on_error == "retry_once":
            logger.info("Retrying step %d (%s)…", step_num, action)
            try:
                result = self._executor.execute_sync(action_dict)
            except Exception as exc:
                logger.error("Executor raised on retry of step %d (%s): %s", step_num, action, exc)
                return {"success": False, "error": str(exc)}

        return result
