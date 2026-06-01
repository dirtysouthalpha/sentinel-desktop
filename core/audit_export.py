"""Sentinel Desktop — Audit Log Export Module.

Generates professional audit reports in HTML, text, CSV, and JSON formats.
Each report includes session metadata, a step timeline, and summary statistics.
Sensitive fields (password, token, key, secret) are automatically masked.
"""

import csv
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from core.utils import iso_now as _now_iso

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensitive-field masking
# ---------------------------------------------------------------------------

_SENSITIVE_KEY_NAMES = re.compile(
    r"(password|passwd|pwd|token|key|secret|api_key|apikey|access_key|auth)",
    re.IGNORECASE,
)

_SENSITIVE_VALUES = re.compile(
    r"(password|passwd|pwd|token|secret|api_key|apikey|access_key)",
    re.IGNORECASE,
)


def _mask_value(value: Any) -> Any:
    """Recursively mask sensitive values inside nested dicts/lists."""
    if isinstance(value, dict):
        return {
            k: "***" if _SENSITIVE_KEY_NAMES.search(k) else _mask_value(v) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    if isinstance(value, str) and _SENSITIVE_VALUES.search(value):
        return "***"
    return value


def _mask_log(log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of *log* with sensitive fields masked."""
    masked = []
    for entry in log:
        entry_copy = dict(entry)
        if "params" in entry_copy:
            entry_copy["params"] = _mask_value(entry_copy["params"])
        if "result" in entry_copy:
            entry_copy["result"] = _mask_value(entry_copy["result"])
        masked.append(entry_copy)
    return masked


# ---------------------------------------------------------------------------
# Summary statistics helper
# ---------------------------------------------------------------------------


def _compute_summary(masked_log: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    """Compute success rate, per-action counts, and total elapsed time."""
    total = len(masked_log)
    success_count = sum(
        1
        for e in masked_log
        if str(e.get("result", "")).lower() not in ("fail", "error", "false", "none")
        and e.get("result") is not None
    )
    fail_count = total - success_count
    success_rate = (success_count / total * 100) if total else 0.0

    action_counts: dict[str, int] = {}
    for entry in masked_log:
        action = entry.get("action", "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1

    total_duration = sum(e.get("duration", 0) for e in masked_log)

    return {
        "total_steps": total,
        "success_count": success_count,
        "fail_count": fail_count,
        "success_rate": round(success_rate, 1),
        "action_counts": action_counts,
        "total_duration": round(total_duration, 3),
        "status": metadata.get("status", "unknown"),
    }




_TEXT_COL_WIDTHS = (6, 22, 18, 30)
_TEXT_HEADER_FMT = (
    f"  {{:<{_TEXT_COL_WIDTHS[0]}}} {{:<{_TEXT_COL_WIDTHS[1]}}} "
    f"{{:<{_TEXT_COL_WIDTHS[2]}}} {{:<{_TEXT_COL_WIDTHS[3]}}}"
)


def _text_header_lines() -> list[str]:
    return [
        "=" * 72,
        "  Sentinel Desktop — Audit Report",
        "=" * 72,
        f"  Generated : {_now_iso()}",
        "",
    ]


def _text_metadata_lines(metadata: dict[str, Any]) -> list[str]:
    rows = [
        ("Goal", metadata.get("goal", "N/A")),
        ("Start Time", metadata.get("start_time", "N/A")),
        ("End Time", metadata.get("end_time", "N/A")),
        ("Total Steps", str(metadata.get("total_steps", 0))),
        ("Status", metadata.get("status", "N/A")),
    ]
    lines = ["-" * 72, "  Session Metadata", "-" * 72]
    lines += [f"  {label:<16}: {value}" for label, value in rows]
    lines.append("")
    return lines


def _text_timeline_lines(masked: list[dict[str, Any]]) -> list[str]:
    lines = ["-" * 72, "  Step Timeline", "-" * 72]
    lines.append(_TEXT_HEADER_FMT.format("Step", "Timestamp", "Action", "Result"))
    lines.append("  " + "-" * (sum(_TEXT_COL_WIDTHS) - 1))
    result_max = _TEXT_COL_WIDTHS[3]
    for entry in masked:
        result_str = str(entry.get("result", ""))
        if len(result_str) > result_max - 1:
            result_str = result_str[: result_max - 4] + "..."
        lines.append(
            _TEXT_HEADER_FMT.format(
                entry.get("step", ""),
                str(entry.get("timestamp", "")),
                entry.get("action", ""),
                result_str,
            )
        )
    lines.append("")
    return lines


def _text_summary_lines(summary: dict[str, Any]) -> list[str]:
    lines = [
        "-" * 72,
        "  Summary Statistics",
        "-" * 72,
        f"  Total Steps   : {summary['total_steps']}",
        f"  Successful    : {summary['success_count']}",
        f"  Failed        : {summary['fail_count']}",
        f"  Success Rate  : {summary['success_rate']}%",
        f"  Total Duration: {summary['total_duration']}s",
        f"  Status        : {summary['status']}",
        "",
    ]
    if summary["action_counts"]:
        lines.append("  Action Counts:")
        for action, count in summary["action_counts"].items():
            lines.append(f"    {action:<28}: {count}")
    lines += ["", "=" * 72, "  End of Report", "=" * 72]
    return lines


# ===================================================================
# AuditExporter
# ===================================================================


class AuditExporter:
    """Export forensic / audit logs to HTML, text, CSV, or JSON.

    Parameters
    ----------
    output_dir : str
        Directory where report files are written.  Created on first use.

    """

    def __init__(self, output_dir: str = "reports") -> None:
        """Initialize the exporter and ensure the output directory exists.

        Args:
            output_dir: Directory where generated report files are written.

        """
        self.output_dir = output_dir
        self._dir_ready = False
        try:
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
            self._dir_ready = True
        except OSError:
            logger.exception(
                "Failed to create output dir %s — all exports will fail", self.output_dir
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_report(
        self,
        log: list[dict[str, Any]],
        metadata: dict[str, Any],
        fmt: str = "html",
        format: str | None = None,
    ) -> str:
        """Dispatch to the appropriate exporter and return the file path.

        Parameters
        ----------
        log : list[dict]
            Audit entries with keys: step, timestamp, action, params, result, duration.
        metadata : dict
            Session info with keys: goal, start_time, end_time, total_steps, status.
        fmt : str
            One of ``html``, ``text``, ``csv``, ``json``.
        format : str, optional
            Alternative keyword for ``fmt`` for backwards compatibility.

        Returns
        -------
        str
            Absolute path to the generated report file.

        """
        # Support both `fmt` and `format` keyword args for backwards compat
        if format is not None:
            fmt = format
        dispatch = {
            "html": self.export_html,
            "text": self.export_text,
            "txt": self.export_text,
            "csv": self.export_csv,
            "json": self.export_json,
        }
        handler = dispatch.get(fmt.lower())
        if handler is None:
            _msg = f"Unsupported format '{fmt}'. Choose from: {', '.join(dispatch)}"
            raise ValueError(_msg)
        if not self._dir_ready:
            raise OSError(
                f"Output directory {self.output_dir!r} is not available — check permissions"
            )
        return handler(log, metadata)

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def export_json(self, log: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        """Export audit data as a pretty-printed JSON file."""
        masked = _mask_log(log)
        summary = _compute_summary(masked, metadata)

        report = {
            "header": "Sentinel Desktop — Audit Report",
            "generated_at": _now_iso(),
            "metadata": metadata,
            "steps": masked,
            "summary": summary,
        }

        filename = self._filename("audit_report", "json")
        filepath = Path(filename)
        try:
            with filepath.open("w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
        except OSError:
            logger.exception("Failed to write JSON report %s", filename)
            raise
        else:
            return str(filepath.resolve())

    # ------------------------------------------------------------------
    # CSV  (RFC 4180)
    # ------------------------------------------------------------------

    def export_csv(self, log: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        """Export audit data as an RFC-4180-compliant CSV file."""
        masked = _mask_log(log)
        filename = self._filename("audit_report", "csv")

        fieldnames = ["step", "timestamp", "action", "params", "result", "duration"]
        filepath = Path(filename)
        try:
            with filepath.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=fieldnames,
                    quoting=csv.QUOTE_ALL,
                    quotechar='"',
                    doublequote=True,
                )
                writer.writeheader()

                for entry in masked:
                    row = {
                        "step": entry.get("step", ""),
                        "timestamp": entry.get("timestamp", ""),
                        "action": entry.get("action", ""),
                        "params": json.dumps(entry.get("params", {}), default=str),
                        "result": json.dumps(entry.get("result"), default=str),
                        "duration": entry.get("duration", ""),
                    }
                    writer.writerow(row)
        except OSError:
            logger.exception("Failed to write CSV report %s", filename)
            raise
        else:
            return str(filepath.resolve())

    # ------------------------------------------------------------------

    def export_text(self, log: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        """Export audit data as a plain-text report with ASCII tables."""
        masked = _mask_log(log)
        summary = _compute_summary(masked, metadata)
        lines = (
            _text_header_lines()
            + _text_metadata_lines(metadata)
            + _text_timeline_lines(masked)
            + _text_summary_lines(summary)
        )
        filename = self._filename("audit_report", "txt")
        filepath = Path(filename)
        try:
            with filepath.open("w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
        except OSError:
            logger.exception("Failed to write text report %s", filename)
            raise
        else:
            return str(filepath.resolve())

    # ------------------------------------------------------------------
    # HTML (dark sentinel theme)
    # ------------------------------------------------------------------

    def export_html(self, log: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        """Export audit data as a styled HTML report (dark sentinel theme)."""
        masked = _mask_log(log)
        summary = _compute_summary(masked, metadata)

        html = self._html_preamble()
        html += self._html_metadata_section(metadata)
        html += self._html_timeline(masked)
        html += self._html_summary(summary)
        html += self._html_postamble()

        filename = self._filename("audit_report", "html")
        filepath = Path(filename)
        try:
            with filepath.open("w", encoding="utf-8") as fh:
                fh.write(html)
        except OSError:
            logger.exception("Failed to write HTML report %s", filename)
            raise
        else:
            return str(filepath.resolve())

    # ------------------------------------------------------------------
    # HTML helpers
    # ------------------------------------------------------------------

    @staticmethod
    @staticmethod
    def _html_css() -> str:
        """Return the CSS block for the dark-themed audit report."""
        css_parts = [
            AuditExporter._css_variables(),
            AuditExporter._css_base_styles(),
            AuditExporter._css_components(),
            AuditExporter._css_print_styles(),
        ]
        return "<style>\n" + "\n".join(css_parts) + "\n</style>\n"

    @staticmethod
    def _css_variables() -> str:
        """Return CSS custom properties (variables)."""
        return """  /* ---- Dark Sentinel Theme ---- */
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --accent: #58a6ff;
    --text: #c9d1d9;
    --text-dim: #8b949e;
    --success: #3fb950;
    --fail: #f85149;
    --warn: #d29922;
  }"""

    @staticmethod
    def _css_base_styles() -> str:
        """Return base CSS styles for typography and layout."""
        return """  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', Consolas, 'Courier New', monospace;
    background: var(--bg);
    color: var(--text);
    padding: 2rem;
    line-height: 1.6;
  }
  h1, h2, h3 { color: var(--accent); font-weight: 600; }
  h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
  h2 { font-size: 1.2rem; margin: 1.5rem 0 0.75rem; border-bottom: 1px solid var(--border); padding-bottom: 0.35rem; }
  .timestamp { color: var(--text-dim); font-size: 0.85rem; margin-bottom: 1.5rem; }"""

    @staticmethod
    def _css_components() -> str:
        """Return CSS styles for UI components (tables, badges, cards, etc)."""
        return """  table { width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }
  th, td { text-align: left; padding: 0.55rem 0.75rem; border: 1px solid var(--border); }
  th { background: var(--surface); color: var(--accent); }
  tr:nth-child(even) td { background: rgba(22,27,34,0.6); }
  tr:nth-child(odd)  td { background: var(--bg); }
  tr:hover td { background: rgba(88,166,255,0.07); }
  .badge {
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 600;
  }
  .badge-success { background: rgba(63,185,80,0.18); color: var(--success); }
  .badge-fail    { background: rgba(248,81,73,0.18); color: var(--fail); }
  .badge-warn    { background: rgba(210,153,34,0.18); color: var(--warn); }
  .meta-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .meta-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem 1rem;
  }
  .meta-card .label { color: var(--text-dim); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; }
  .meta-card .value { color: var(--text); font-size: 0.95rem; margin-top: 0.15rem; word-break: break-word; }
  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1.5rem;
  }
  .summary-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    text-align: center;
  }
  .summary-card .num { font-size: 1.6rem; font-weight: 700; color: var(--accent); }
  .summary-card .lbl { font-size: 0.78rem; color: var(--text-dim); margin-top: 0.2rem; }
  .result-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .params-cell { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.85rem; color: var(--text-dim); }
  .action-list { list-style: none; padding: 0; }
  .action-list li { padding: 0.2rem 0; }
  .action-list li::before { content: '▸ '; color: var(--accent); }"""

    @staticmethod
    def _css_print_styles() -> str:
        """Return print-specific CSS overrides."""
        return """  @media print {
    body { background: #fff; color: #000; padding: 1rem; }
    h1, h2, h3 { color: #1a1a2e; }
    th { background: #eee; color: #1a1a2e; }
    td { border-color: #ccc; }
    tr:nth-child(even) td { background: #f7f7f7; }
    tr:nth-child(odd)  td { background: #fff; }
    .badge { border: 1px solid #999; }
    .meta-card, .summary-card { border-color: #ccc; background: #f9f9f9; }
    .meta-card .label, .summary-card .lbl { color: #555; }
    .meta-card .value, .summary-card .num { color: #111; }
    .summary-card .num { color: #1a1a2e; }
  }"""

    @staticmethod
    def _html_preamble() -> str:
        """Return the HTML boilerplate and CSS for the dark-themed audit report."""
        return (
            '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            "<title>Sentinel Desktop — Audit Report</title>\n"
            + AuditExporter._html_css()
            + "</head>\n<body>\n"
            "<h1>Sentinel Desktop — Audit Report</h1>\n"
        )

    @staticmethod
    def _html_metadata_section(metadata: dict[str, Any]) -> str:
        """Render the goal, timing, and model metadata cards as HTML."""
        gen_ts = _now_iso()
        cards = [
            ("Goal", metadata.get("goal", "N/A")),
            ("Start Time", metadata.get("start_time", "N/A")),
            ("End Time", metadata.get("end_time", "N/A")),
            ("Total Steps", str(metadata.get("total_steps", 0))),
            ("Status", metadata.get("status", "N/A")),
        ]
        cards_html = "\n".join(
            f'  <div class="meta-card"><div class="label">{label}</div>'
            f'<div class="value">{value}</div></div>'
            for label, value in cards
        )
        return (
            f'<div class="timestamp">Generated: {gen_ts}</div>\n'
            "<h2>Session Metadata</h2>\n"
            '<div class="meta-grid">\n'
            f"{cards_html}\n"
            "</div>\n"
        )

    @staticmethod
    def _html_timeline(masked_log: list[dict[str, Any]]) -> str:
        """Render the step-by-step timeline table from the masked audit log."""
        rows = []
        for entry in masked_log:
            result_raw = str(entry.get("result", ""))
            is_fail = (
                result_raw.lower() in ("fail", "error", "false", "none") or result_raw == "None"
            )
            badge_cls = "badge-fail" if is_fail else "badge-success"
            badge_label = "FAIL" if is_fail else "OK"
            result_display = (
                f'<span class="badge {badge_cls}">{badge_label}</span> {_esc(result_raw[:60])}'
            )
            params_str = _esc(json.dumps(entry.get("params", {}), default=str)[:80])
            rows.append(
                f"<tr>"
                f"<td>{entry.get('step', '')}</td>"
                f"<td>{_esc(str(entry.get('timestamp', '')))}</td>"
                f"<td>{_esc(entry.get('action', ''))}</td>"
                f'<td class="params-cell">{params_str}</td>'
                f'<td class="result-cell">{result_display}</td>'
                f"<td>{entry.get('duration', '')}s</td>"
                f"</tr>"
            )
        return (
            "<h2>Step Timeline</h2>\n"
            "<table>\n"
            "<thead><tr>"
            "<th>#</th><th>Timestamp</th><th>Action</th>"
            "<th>Params</th><th>Result</th><th>Duration</th>"
            "</tr></thead>\n"
            "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>\n"
        )

    @staticmethod
    def _html_summary(summary: dict[str, Any]) -> str:
        """Render the summary cards (total/success/fail/warnings) as HTML."""
        cards = [
            (str(summary["total_steps"]), "Total Steps"),
            (str(summary["success_count"]), "Successful"),
            (str(summary["fail_count"]), "Failed"),
            (f"{summary['success_rate']}%", "Success Rate"),
            (f"{summary['total_duration']}s", "Total Duration"),
            (str(summary["status"]), "Status"),
        ]
        cards_html = "\n".join(
            f'  <div class="summary-card"><div class="num">{num}</div>'
            f'<div class="lbl">{lbl}</div></div>'
            for num, lbl in cards
        )
        action_items = "\n".join(
            f"<li>{_esc(action)}: {count}</li>"
            for action, count in summary["action_counts"].items()
        )
        return (
            "<h2>Summary Statistics</h2>\n"
            '<div class="summary-grid">\n'
            f"{cards_html}\n"
            "</div>\n"
            "<h2>Action Breakdown</h2>\n"
            '<ul class="action-list">\n'
            f"{action_items}\n"
            "</ul>\n"
        )

    @staticmethod
    def _html_postamble() -> str:
        """Return the closing HTML tags and footer for the audit report."""
        return (
            '<hr style="border:none;border-top:1px solid var(--border);margin:2rem 0 1rem;">'
            '<p style="color:var(--text-dim);font-size:0.78rem;">'
            "End of Report — Sentinel Desktop</p>\n"
            "</body>\n</html>"
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _filename(self, base: str, ext: str) -> str:
        """Build a timestamped output path under ``self.output_dir``."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return str(Path(self.output_dir) / f"{base}_{ts}.{ext}")


# ---------------------------------------------------------------------------
# HTML entity escaping
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def export_audit(
    log: list[dict[str, Any]],
    metadata: dict[str, Any],
    fmt: str = "html",
    output_dir: str = "reports",
) -> str:
    """One-shot convenience wrapper around :class:`AuditExporter`.

    Returns the path to the generated report file.
    """
    exporter = AuditExporter(output_dir=output_dir)
    return exporter.generate_report(log, metadata, fmt=fmt)
