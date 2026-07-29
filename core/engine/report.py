"""Run report generation — structured dicts and human-readable text blocks."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class RunReporter:
    """Generates structured run reports for MSP work notes.

    Stateless — all state is passed in via the *engine* reference and method
    arguments so it can be used with a bare ``__new__``-created engine in tests.
    """

    def generate(self, engine: Any, goal: str, elapsed: float) -> dict[str, Any]:
        """Generate a structured run report for MSP work notes.

        Machine-parseable JSON with a human-readable text block for ticketing.
        An MSP tech reading this at 8am should know: what was attempted, what
        succeeded, what failed, and what to do next.
        """
        now = datetime.now()
        success = bool(engine.finish_summary)
        errors = [e for e in engine.forensic_log if not e.get("result", {}).get("ok", True)]
        provider = engine.config.get("provider", "unknown")
        model = engine.config.get("model", "unknown")

        action_counts = self.compute_action_counts(engine.forensic_log)
        step_trace = self.build_step_trace(engine.forensic_log)

        report: dict[str, Any] = {
            "session_id": now.strftime("%Y%m%d-%H%M%S"),
            "status": "success" if success else "failed",
            "started_at": step_trace[0]["timestamp"] if step_trace else now.isoformat(),
            "finished_at": now.isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "goal": goal,
            "provider": provider,
            "model": model,
            "steps_total": engine.step,
            "steps_failed": len(errors),
            "actions": action_counts,
            "summary": engine.finish_summary or "Run ended without completion",
            "notes": engine.notes,
            "step_trace": step_trace,
            "error_list": self.build_error_list(errors),
        }

        report["text"] = self.build_report_text(
            report,
            goal,
            elapsed,
            success,
            errors,
            provider,
            model,
            engine.step,
            engine.notes,
        )
        return report

    def compute_action_counts(self, forensic_log: list[dict[str, Any]]) -> dict[str, int]:
        """Count occurrences of each action type in the forensic log."""
        counts: dict[str, int] = {}
        for entry in forensic_log:
            a = entry.get("action", "unknown")
            counts[a] = counts.get(a, 0) + 1
        return counts

    @staticmethod
    def strip_screenshot_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Remove screenshot data from action params for report output."""
        if not params:
            return {}
        return {k: v for k, v in params.items() if k not in ("screenshot",)}

    def build_step_trace(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build the step_trace summary list from forensic log entries.

        Each entry is sanitized to remove bulky screenshot params and
        truncates the output preview to keep reports compact.
        """
        return [
            {
                "step": e.get("step"),
                "action": e.get("action"),
                "params": self.strip_screenshot_params(e.get("params")),
                "ok": e.get("result", {}).get("ok", True),
                "output_preview": str(e.get("result", {}).get("msg", ""))[:200],
                "timestamp": e.get("timestamp"),
            }
            for e in entries
        ]

    def build_error_list(self, errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build a capped error summary from failed forensic log entries.

        Returns at most 20 entries to prevent unbounded report growth on
        runs with many failures.
        """
        return [
            {
                "step": e.get("step"),
                "action": e.get("action"),
                "params": self.strip_screenshot_params(e.get("params")),
                "error": e.get("result", {}).get("msg", "")[:300],
                "timestamp": e.get("timestamp"),
            }
            for e in errors[:20]
        ]

    def build_report_text(
        self,
        report: dict[str, Any],
        goal: str,
        elapsed: float,
        success: bool,
        errors: list[dict[str, Any]],
        provider: str,
        model: str,
        step: int,
        notes: list[str],
    ) -> str:
        """Format the human-readable ticketing block for the run report.

        Generates a plain-text summary suitable for pasting into an MSP
        ticket or change-management log.
        """
        lines = [
            "SENTINEL DESKTOP — AUTOMATION REPORT",
            f"Session: {report['session_id']}",
            f"Status: {'COMPLETED' if success else 'FAILED'}",
            f"Time: {report['started_at']} → {report['finished_at']} ({elapsed:.1f}s)",
            f"Provider: {provider} / {model}",
            f"Goal: {goal}",
            f"Steps: {step} ({len(errors)} failed)",
            f"Summary: {report['summary']}",
        ]
        if notes:
            lines.append("Notes:")
            for n in notes[:10]:
                lines.append(f"  - {n[:200]}")
        if errors:
            lines.append("Errors:")
            for e in errors[:5]:
                msg = e.get("result", {}).get("msg", "")[:150]
                lines.append(f"  Step {e.get('step')}: {e.get('action')} — {msg}")
        return "\n".join(lines)
