"""
Sentinel Desktop v29.0.0 - Vector Memory Store.

Lightweight semantic memory using TF-IDF similarity.
Stores agent experiences and recalls relevant ones for new goals.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".sentinel-desktop" / "vector_memory.json"


def _tokenize(text: str) -> list[str]:
    """Simple tokenization: lowercase, split on non-word chars."""
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 1]


def _cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    if not v1 or not v2:
        return 0.0
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in v1 if k in v2)
    mag1 = math.sqrt(sum(v * v for v in v1.values()))
    mag2 = math.sqrt(sum(v * v for v in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


@dataclass
class MemoryEntry:
    """A single memory entry in the vector store."""
    id: str
    goal: str
    actions: list[str] = field(default_factory=list)
    outcome: str = ""
    success: bool = False
    timestamp: str = ""
    _vector: dict[str, float] = field(default_factory=dict)


class VectorMemoryStore:
    """TF-IDF based semantic memory for agent experiences."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[MemoryEntry] = []
        self._lock = threading.Lock()
        self._document_freq: dict[str, int] = {}
        self._load()

    def _compute_tfidf(self, text: str) -> dict[str, float]:
        """Compute TF-IDF vector for a text string."""
        tokens = _tokenize(text)
        if not tokens:
            return {}
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total_docs = max(len(self._entries), 1)
        result: dict[str, float] = {}
        for term, count in tf.items():
            df = self._document_freq.get(term, 0) + 1
            idf = math.log(total_docs / df + 1)
            result[term] = (count / len(tokens)) * idf
        return result

    def add(self, goal: str, actions: list[str] | None = None, outcome: str = "", success: bool = False) -> str:
        """Add a new memory entry."""
        import uuid
        entry_id = str(uuid.uuid4())[:8]
        entry = MemoryEntry(
            id=entry_id,
            goal=goal,
            actions=actions or [],
            outcome=outcome,
            success=success,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        # Compute vector
        combined = goal + " " + outcome + " " + " ".join(actions or [])
        entry._vector = self._compute_tfidf(combined)
        # Update document frequencies
        for term in entry._vector:
            self._document_freq[term] = self._document_freq.get(term, 0) + 1
        with self._lock:
            self._entries.append(entry)
            self._save()
        logger.info("Added memory entry '%s' for goal: %s", entry_id, goal[:50])
        return entry_id

    def search(self, query: str, limit: int = 5, min_score: float = 0.01) -> list[dict[str, Any]]:
        """Search for similar past experiences."""
        query_vec = self._compute_tfidf(query)
        scored = []
        with self._lock:
            for entry in self._entries:
                score = _cosine_similarity(query_vec, entry._vector)
                if score >= min_score:
                    scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": e.id,
                "goal": e.goal,
                "actions": e.actions,
                "outcome": e.outcome,
                "success": e.success,
                "timestamp": e.timestamp,
                "score": round(s, 4),
            }
            for s, e in scored[:limit]
        ]

    def get_stats(self) -> dict[str, Any]:
        """Return memory store statistics."""
        return {
            "total_entries": len(self._entries),
            "successful": sum(1 for e in self._entries if e.success),
            "failed": sum(1 for e in self._entries if not e.success),
            "vocabulary_size": len(self._document_freq),
        }

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
            self._document_freq.clear()
            self._save()

    def _save(self) -> None:
        """Persist to disk."""
        try:
            data = [
                {"id": e.id, "goal": e.goal, "actions": e.actions, "outcome": e.outcome, "success": e.success, "timestamp": e.timestamp}
                for e in self._entries
            ]
            with self.db_path.open("w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save vector memory: %s", e)

    def _load(self) -> None:
        """Load from disk."""
        try:
            if self.db_path.exists():
                with self.db_path.open() as f:
                    data = json.load(f)
                for item in data:
                    entry = MemoryEntry(
                        id=item["id"],
                        goal=item["goal"],
                        actions=item.get("actions", []),
                        outcome=item.get("outcome", ""),
                        success=item.get("success", False),
                        timestamp=item.get("timestamp", ""),
                    )
                    combined = entry.goal + " " + entry.outcome + " " + " ".join(entry.actions)
                    entry._vector = self._compute_tfidf(combined)
                    self._entries.append(entry)
                logger.info("Loaded %d memory entries", len(self._entries))
        except Exception as e:
            logger.warning("Failed to load vector memory: %s", e)


_store: VectorMemoryStore | None = None


def get_store() -> VectorMemoryStore:
    """Get or create the singleton vector memory store."""
    global _store
    if _store is None:
        _store = VectorMemoryStore()
    return _store
