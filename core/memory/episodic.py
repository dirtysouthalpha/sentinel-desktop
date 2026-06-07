"""Sentinel Desktop v11.0 — Episodic Memory.

Stores timestamped interaction records (episodes) as JSONL.
Each episode captures: goal, actions taken, results, outcome.

Episodes older than 30 days are automatically compressed into
semantic summaries to keep storage manageable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_EPISODIC_PATH = Path("memory/episodes.jsonl")

# Episodes older than this many days get compressed into summaries.
COMPRESSION_THRESHOLD_DAYS = 30


class Episode:
    """A single interaction episode."""

    def __init__(
        self,
        goal: str,
        actions: list[dict[str, Any]] | None = None,
        outcome: str = "",
        success: bool = False,
        tags: list[str] | None = None,
        episode_id: str | None = None,
    ) -> None:
        self.episode_id = episode_id or datetime.utcnow().strftime("%Y%m%d%H%M%S") + f"_{id(self) % 10000:04d}"
        self.goal = goal
        self.actions = actions or []
        self.outcome = outcome
        self.success = success
        self.tags = tags or []
        self.created_at: str = datetime.utcnow().isoformat()
        self.step_count: int = len(self.actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "goal": self.goal,
            "actions": self.actions,
            "outcome": self.outcome,
            "success": self.success,
            "tags": self.tags,
            "created_at": self.created_at,
            "step_count": self.step_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Episode:
        ep = cls(
            goal=data["goal"],
            actions=data.get("actions", []),
            outcome=data.get("outcome", ""),
            success=data.get("success", False),
            tags=data.get("tags"),
            episode_id=data.get("episode_id"),
        )
        ep.created_at = data.get("created_at", ep.created_at)
        ep.step_count = data.get("step_count", len(ep.actions))
        return ep


class EpisodicMemory:
    """Persistent episodic memory stored as JSONL.

    Usage::

        memory = EpisodicMemory()
        memory.store("Login to firewall", actions=[...], outcome="Success", success=True)
        recent = memory.recall(limit=10)
        similar = memory.search("firewall")
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_EPISODIC_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        goal: str,
        actions: list[dict[str, Any]] | None = None,
        outcome: str = "",
        success: bool = False,
        tags: list[str] | None = None,
    ) -> str:
        """Store a new episode. Returns the episode ID."""
        episode = Episode(
            goal=goal, actions=actions, outcome=outcome,
            success=success, tags=tags,
        )
        self._append(episode)
        logger.info("Stored episode %s: %s", episode.episode_id, goal[:60])
        return episode.episode_id

    def recall(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """Recall recent episodes (most recent first)."""
        episodes = self._read_all()
        # Return most recent first
        episodes.reverse()
        return [ep.to_dict() for ep in episodes[offset:offset + limit]]

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search episodes by keyword matching in goal/outcome/tags."""
        query_lower = query.lower()
        results = []
        for ep in reversed(self._read_all()):
            if (query_lower in ep.goal.lower()
                    or query_lower in ep.outcome.lower()
                    or any(query_lower in tag.lower() for tag in ep.tags)):
                results.append(ep.to_dict())
                if len(results) >= limit:
                    break
        return results

    def count(self) -> int:
        """Count total episodes."""
        return len(self._read_all())

    def get_by_id(self, episode_id: str) -> dict[str, Any] | None:
        """Get a specific episode by ID."""
        for ep in self._read_all():
            if ep.episode_id == episode_id:
                return ep.to_dict()
        return None

    def delete(self, episode_id: str) -> bool:
        """Delete an episode by ID."""
        episodes = self._read_all()
        original_len = len(episodes)
        episodes = [ep for ep in episodes if ep.episode_id != episode_id]
        if len(episodes) == original_len:
            return False
        self._write_all(episodes)
        return True

    def compress_old(self, days: int = COMPRESSION_THRESHOLD_DAYS) -> int:
        """Compress episodes older than N days into summaries.

        Returns the number of episodes compressed.
        """
        cutoff = datetime.utcnow().timestamp() - (days * 86400)
        episodes = self._read_all()

        old_eps = []
        recent_eps = []
        for ep in episodes:
            try:
                ep_time = datetime.fromisoformat(ep.created_at).timestamp()
            except (ValueError, TypeError):
                recent_eps.append(ep)
                continue
            if ep_time < cutoff:
                old_eps.append(ep)
            else:
                recent_eps.append(ep)

        if not old_eps:
            return 0

        # Create a summary episode
        successes = sum(1 for ep in old_eps if ep.success)
        summary = Episode(
            goal=f"[Summary] {len(old_eps)} episodes from {days}+ days ago",
            outcome=f"{successes}/{len(old_eps)} successful",
            success=successes > len(old_eps) / 2,
            tags=["compressed", "summary"],
        )
        summary.actions = [{
            "type": "compression_summary",
            "episodes_count": len(old_eps),
            "success_rate": successes / max(len(old_eps), 1),
            "goals_sample": [ep.goal[:60] for ep in old_eps[:5]],
        }]

        self._write_all(recent_eps + [summary])
        logger.info("Compressed %d old episodes into summary", len(old_eps))
        return len(old_eps)

    def _append(self, episode: Episode) -> None:
        line = json.dumps(episode.to_dict(), ensure_ascii=False) + "\n"
        self._path.write_text(
            self._path.read_text(encoding="utf-8") + line if self._path.exists() else line,
            encoding="utf-8",
        )

    def _read_all(self) -> list[Episode]:
        if not self._path.exists():
            return []
        episodes = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                episodes.append(Episode.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue
        return episodes

    def _write_all(self, episodes: list[Episode]) -> None:
        lines = [json.dumps(ep.to_dict(), ensure_ascii=False) for ep in episodes]
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
