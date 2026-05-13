"""
Sentinel Desktop v2 — Forensic run log.

Provides a structured, per-step forensic audit trail — the desktop equivalent
of Sentinel Override's forensic log. Every agent step is recorded with full
context for compliance review and export.

Thread-safe. Uses only stdlib modules.
"""

import csv
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensitive field detection
# ---------------------------------------------------------------------------
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "key",
    "secret",
    "token",
    "credential",
    "api_key",
    "credit_card",
    "ssn",
    "social_security",
    "pin",
)


# ---------------------------------------------------------------------------
# Log directory
# ---------------------------------------------------------------------------
def _default_log_dir() -> str:
    """Return the platform-appropriate log directory under AppData."""
    if os.name == "nt":
        base = os.environ.get(
            "APPDATA",
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming"),
        )
    else:
        base = os.path.expanduser("~")
    return os.path.join(base, "sentinel-desktop", "logs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _redact_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *params* with sensitive values replaced.

    Any key that contains one of the SENSITIVE_KEY_PARTS substrings
    (case-insensitive) has its value replaced with '***REDACTED***'.
    """
    if not params:
        return {}
    redacted: dict[str, Any] = {}
    for k, v in params.items():
        kl = k.lower()
        if any(part in kl for part in SENSITIVE_KEY_PARTS):
            redacted[k] = "***REDACTED***"
        else:
            redacted[k] = v
    return redacted


def _preview(value: Any, max_len: int = 120) -> str:
    """Return a short string preview of *value* suitable for CSV cells."""
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# ForensicLog
# ---------------------------------------------------------------------------


class ForensicLog:
    """Structured forensic audit trail for a single agent run.

    Typical lifecycle::

        fl = ForensicLog()
        run_id = fl.start_run("Open Outlook", "openai", "gpt-4o")
        fl.log_step(1, "click", "New Email button", {}, "success")
        fl.log_event("pause", {"reason": "MFA prompt detected"})
        fl.end_run("success", "Completed", 1)
        fl.export_json("run.json")
        fl.export_csv("run.csv")
        print(fl.get_summary())

    All public methods are thread-safe.
    """

    def __init__(self, log_dir: str | None = None):
        self._lock = threading.Lock()
        self._log_dir = log_dir or _default_log_dir()
        self._run: dict[str, Any] = {}
        self._steps: list[dict[str, Any]] = []
        self._last_step_time: str | None = None

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def start_run(self, goal: str, provider: str, model: str) -> str:
        """Start a new forensic run. Returns the ``run_id`` (UUID)."""
        run_id = str(uuid.uuid4())
        now = _iso_now()

        with self._lock:
            self._run = {
                "run_id": run_id,
                "goal": goal,
                "provider": provider,
                "model": model,
                "status": "running",
                "start_time": now,
                "end_time": None,
                "summary": None,
                "total_steps": 0,
            }
            self._steps = []
            self._last_step_time = now

        logger.info("Forensic run started: %s  goal=%r", run_id[:8], goal)
        self._auto_save()
        return run_id

    def end_run(self, status: str, summary: str, total_steps: int) -> None:
        """Mark the current run as finished."""
        now = _iso_now()

        with self._lock:
            self._run["status"] = status
            self._run["summary"] = summary
            self._run["total_steps"] = total_steps
            self._run["end_time"] = now

        logger.info(
            "Forensic run ended: %s  status=%s  steps=%d",
            self._run["run_id"][:8],
            status,
            total_steps,
        )
        self._auto_save()

    # ------------------------------------------------------------------
    # Step logging
    # ------------------------------------------------------------------

    def log_step(
        self,
        step_num: int,
        action_type: str,
        target: str,
        params: dict[str, Any],
        result: str,
        screenshot_path: str | None = None,
    ) -> str:
        """Record a single agent step. Returns the ``step_id`` (UUID).

        Args:
            step_num: 1-based step counter.
            action_type: e.g. "click", "type", "press_key", "hotkey",
                "scroll", "screenshot", etc.
            target: Element name, coordinates, or window title.
            params: Arbitrary action parameters. Sensitive values are
                automatically redacted.
            result: "success" or "fail", possibly with output text.
            screenshot_path: Optional path to a screenshot taken during
                this step.
        """
        step_id = str(uuid.uuid4())
        now = _iso_now()

        # Compute duration since last step
        with self._lock:
            if self._last_step_time:
                try:
                    prev = datetime.fromisoformat(self._last_step_time)
                    curr = datetime.fromisoformat(now)
                    duration_ms = int((curr - prev).total_seconds() * 1000)
                except (ValueError, TypeError):
                    duration_ms = 0
            else:
                duration_ms = 0

            # Determine event_type from result
            event_type = self._infer_event_type(result)

            step: dict[str, Any] = {
                "step_id": step_id,
                "run_id": self._run.get("run_id", ""),
                "step_num": step_num,
                "timestamp": now,
                "action_type": action_type,
                "target": target,
                "params": _redact_params(params),
                "result": result,
                "screenshot_path": screenshot_path,
                "duration_ms": duration_ms,
                "event_type": event_type,
            }

            self._steps.append(step)
            self._last_step_time = now

        logger.debug(
            "Step %d %s → %s  target=%r  step_id=%s",
            step_num,
            action_type,
            result,
            target,
            step_id[:8],
        )
        self._auto_save()
        return step_id

    def log_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Record a non-action event (override, pause, error, timeout, etc.).

        Args:
            event_type: One of "override", "pause", "resume", "error",
                "timeout", or any custom event string.
            details: Arbitrary metadata about the event.
        """
        now = _iso_now()

        with self._lock:
            if self._last_step_time:
                try:
                    prev = datetime.fromisoformat(self._last_step_time)
                    curr = datetime.fromisoformat(now)
                    duration_ms = int((curr - prev).total_seconds() * 1000)
                except (ValueError, TypeError):
                    duration_ms = 0
            else:
                duration_ms = 0

            step_num = len(self._steps) + 1
            step_id = str(uuid.uuid4())

            step: dict[str, Any] = {
                "step_id": step_id,
                "run_id": self._run.get("run_id", ""),
                "step_num": step_num,
                "timestamp": now,
                "action_type": "event",
                "target": "",
                "params": _redact_params(details) if isinstance(details, dict) else {},
                "result": event_type,
                "screenshot_path": None,
                "duration_ms": duration_ms,
                "event_type": event_type,
            }

            self._steps.append(step)
            self._last_step_time = now

        logger.info(
            "Forensic event: %s  details=%r  run=%s",
            event_type,
            details,
            self._run.get("run_id", "???")[:8],
        )
        self._auto_save()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_run(self) -> dict[str, Any]:
        """Return a copy of the full run metadata dict."""
        with self._lock:
            return dict(self._run)

    def get_steps(self) -> list[dict[str, Any]]:
        """Return a list of copies of all recorded step dicts."""
        with self._lock:
            return [dict(s) for s in self._steps]

    def get_summary(self) -> str:
        """Return a brief human-readable summary for display."""
        with self._lock:
            run = self._run
            steps = self._steps

        if not run:
            return "No forensic run recorded."

        run_id_short = run.get("run_id", "???")[:8]
        status = run.get("status", "unknown")
        goal = run.get("goal", "(no goal)")
        provider = run.get("provider", "?")
        model = run.get("model", "?")
        total = run.get("total_steps", len(steps))
        start = run.get("start_time", "?")
        end = run.get("end_time", "—")
        summary = run.get("summary", "")

        # Count event types
        action_count = sum(1 for s in steps if s.get("event_type") == "action")
        error_count = sum(1 for s in steps if s.get("event_type") == "error")
        override_count = sum(1 for s in steps if s.get("event_type") == "override")

        lines = [
            f"Run {run_id_short}  [{status}]  goal: {goal}",
            f"  Provider: {provider} / {model}",
            f"  Started:  {start}",
            f"  Ended:    {end}",
            f"  Steps:    {total}  (actions={action_count}  errors={error_count}  overrides={override_count})",
        ]
        if summary:
            lines.append(f"  Summary:  {summary}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_json(self, path: str) -> bool:
        """Write the full run (metadata + steps) to a JSON file.

        Creates parent directories automatically.
        Returns ``True`` on success.
        """
        with self._lock:
            payload = {
                "run": dict(self._run),
                "steps": [dict(s) for s in self._steps],
            }

        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str, ensure_ascii=False)
            logger.debug("Forensic JSON exported to %s", path)
            return True
        except Exception as exc:
            logger.error("export_json failed: %s", exc)
            return False

    def export_csv(self, path: str) -> bool:
        """Write all steps to an RFC-4180 quoted CSV file.

        Columns: run_id, step_num, timestamp, action_type, target,
        params_preview, result_preview, success, event_type.

        Returns ``True`` on success.
        """
        columns = [
            "run_id",
            "step_num",
            "timestamp",
            "action_type",
            "target",
            "params_preview",
            "result_preview",
            "success",
            "event_type",
        ]

        with self._lock:
            steps = [dict(s) for s in self._steps]
            run_id = self._run.get("run_id", "")

        rows = []
        for s in steps:
            params_preview = _preview(s.get("params", {}))
            result_raw = s.get("result", "")
            result_preview = _preview(result_raw)

            # Determine success boolean
            result_lower = str(result_raw).lower()
            success = "true" if "success" in result_lower or "ok" in result_lower else "false"

            rows.append(
                {
                    "run_id": run_id,
                    "step_num": s.get("step_num", ""),
                    "timestamp": s.get("timestamp", ""),
                    "action_type": s.get("action_type", ""),
                    "target": s.get("target", ""),
                    "params_preview": params_preview,
                    "result_preview": result_preview,
                    "success": success,
                    "event_type": s.get("event_type", ""),
                }
            )

        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=columns,
                    quoting=csv.QUOTE_ALL,  # RFC-4180
                )
                writer.writeheader()
                writer.writerows(rows)
            logger.debug("Forensic CSV exported to %s (%d rows)", path, len(rows))
            return True
        except Exception as exc:
            logger.error("export_csv failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_event_type(result: str) -> str:
        """Derive an event_type from the result string."""
        r = str(result).lower()
        if "error" in r or "fail" in r or "exception" in r:
            return "error"
        if "timeout" in r:
            return "error"
        return "action"

    def _auto_save(self) -> None:
        """Persist the current run to ``<log_dir>/<run_id>.json``."""
        if not self._run:
            return
        run_id = self._run.get("run_id")
        if not run_id:
            return
        dest = os.path.join(self._log_dir, f"{run_id}.json")
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            with self._lock:
                payload = {
                    "run": dict(self._run),
                    "steps": [dict(s) for s in self._steps],
                }
            with open(dest, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Forensic auto-save failed: %s", exc)
