"""Daily digest generator for the fleet mesh."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.mesh.task_graph import TaskStatus

logger = logging.getLogger(__name__)


class DailyDigest:
    def generate(self, tasks, nodes, lessons, max_lessons=3) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        completed = sum(1 for t in tasks if getattr(t, "status", None) == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if getattr(t, "status", None) == TaskStatus.FAILED)
        retried = sum(1 for t in tasks if getattr(t, "retry_count", 0) > 0)
        total = len(tasks)
        lines = [
            f"FLEET DAILY DIGEST — {now}",
            "=" * 40,
            f"Tasks: {completed} completed, {retried} retried, {failed} failed (total {total})",
        ]
        if nodes:
            lines.append("")
            lines.append("Fleet Health:")
            for node in nodes:
                node_id = node.get("node_id", "?")
                status = node.get("status", "?")
                cpu = node.get("cpu")
                cpu_str = f" | CPU {cpu:.0f}%" if cpu is not None else ""
                lines.append(f"  {node_id}: {status}{cpu_str}")
        if lessons:
            lines.append("")
            lines.append("Top Lessons:")
            for i, lesson in enumerate(lessons[:max_lessons], 1):
                lines.append(f'  {i}. "{lesson.get("content", "")}"')
        return "\n".join(lines)
