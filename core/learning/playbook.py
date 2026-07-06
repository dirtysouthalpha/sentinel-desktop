"""
Sentinel Desktop v30.0.0 - Self-Learning Playbooks.
"""
from __future__ import annotations
import json, logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
PLAYBOOK_DIR = Path.home() / ".sentinel-desktop" / "playbooks"

@dataclass
class Playbook:
    id: str
    name: str
    goal_pattern: str
    actions: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    times_used: int = 0
    created_at: str = ""
    last_used: str = ""
    avg_steps: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "goal_pattern": self.goal_pattern,
                "actions": self.actions, "success_rate": self.success_rate,
                "times_used": self.times_used, "created_at": self.created_at,
                "last_used": self.last_used, "avg_steps": self.avg_steps}

class PlaybookManager:
    def __init__(self) -> None:
        PLAYBOOK_DIR.mkdir(parents=True, exist_ok=True)
        self._playbooks: dict[str, Playbook] = {}
        self._load()

    def _load(self) -> None:
        for f in PLAYBOOK_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                pb = Playbook(**data)
                self._playbooks[pb.id] = pb
            except Exception as e:
                logger.debug("Failed to load playbook %s: %s", f, e)

    def _save(self, playbook: Playbook) -> None:
        p = PLAYBOOK_DIR / f"{playbook.id}.json"
        try:
            p.write_text(json.dumps(playbook.to_dict(), indent=2))
        except Exception as e:
            logger.warning("Failed to save playbook %s: %s", playbook.id, e)

    def learn_from_telemetry(self, telemetry_summary, recent_runs):
        if not recent_runs:
            return 0
        created = 0
        goal_groups = {}
        for run in recent_runs:
            goal = run.get("goal", "")
            if not goal:
                continue
            words = goal.split()[:4]
            pattern = " ".join(words).lower()
            goal_groups.setdefault(pattern, []).append(run)
        for pattern, runs in goal_groups.items():
            if len(runs) < 2:
                continue
            completed = [r for r in runs if r.get("status") == "completed"]
            if not completed:
                continue
            success_rate = len(completed) / len(runs)
            avg_steps = sum(r.get("steps", 0) for r in completed) // max(len(completed), 1)
            existing = next((pb for pb in self._playbooks.values() if pb.goal_pattern == pattern), None)
            if existing:
                existing.times_used = len(runs)
                existing.success_rate = round(success_rate, 2)
                existing.avg_steps = avg_steps
                existing.last_used = datetime.now(timezone.utc).isoformat()
                self._save(existing)
                continue
            pb_id = f"pb-{pattern.replace(chr(32), chr(45))[:20]}"
            playbook = Playbook(
                id=pb_id, name=pattern.title(), goal_pattern=pattern,
                success_rate=round(success_rate, 2), times_used=len(runs),
                avg_steps=avg_steps,
                created_at=datetime.now(timezone.utc).isoformat(),
                last_used=datetime.now(timezone.utc).isoformat(),
            )
            self._playbooks[pb_id] = playbook
            self._save(playbook)
            created += 1
        return created

    def find_playbook(self, goal):
        words = goal.split()[:4]
        pattern = " ".join(words).lower()
        return self._playbooks.get(f"pb-{pattern.replace(chr(32), chr(45))[:20]}")

    def list_playbooks(self):
        return [pb.to_dict() for pb in sorted(self._playbooks.values(), key=lambda p: p.times_used, reverse=True)]

    def get_stats(self):
        return {
            "total_playbooks": len(self._playbooks),
            "total_uses": sum(p.times_used for p in self._playbooks.values()),
            "avg_success_rate": round(sum(p.success_rate for p in self._playbooks.values()) / max(len(self._playbooks), 1), 2),
        }

_manager = None

def get_manager():
    global _manager
    if _manager is None:
        _manager = PlaybookManager()
    return _manager
