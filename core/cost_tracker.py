"""Sentinel Desktop v21 — Cost Tracker.

Per-run token and dollar accounting across all LLM providers.
Tracks prompt/completion tokens and estimates cost using provider pricing.
Records to in-memory session and persists to JSONL for history.

Usage::

    from core.cost_tracker import get_cost_tracker

    tracker = get_cost_tracker()
    tracker.record("openai", "gpt-4o", usage_dict)
    print(tracker.session_summary())
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing table — cost per 1M tokens (input_usd, output_usd)
# Sources: provider docs as of June 2026
# ---------------------------------------------------------------------------
_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.10, 0.40),
        "gpt-4.1-nano": (0.05, 0.20),
        "o3": (10.00, 40.00),
        "o3-mini": (1.10, 4.40),
        "o4-mini": (1.10, 4.40),
    },
    "anthropic": {
        "claude-opus-4-8": (15.00, 75.00),
        "claude-sonnet-4-6": (3.00, 15.00),
        "claude-haiku-4-5-20251001": (0.25, 1.25),
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
        "claude-3-5-haiku-20241022": (0.80, 4.00),
        "claude-3-haiku-20240307": (0.25, 1.25),
        "claude-3-opus-20240229": (15.00, 75.00),
    },
    "google": {
        "gemini-1.5-pro": (3.50, 10.50),
        "gemini-1.5-flash": (0.075, 0.30),
        "gemini-2.0-flash": (0.10, 0.40),
        "gemini-2.0-flash-lite": (0.075, 0.30),
    },
    "xai": {
        "grok-2": (2.00, 10.00),
        "grok-2-mini": (0.20, 1.00),
    },
}

_PER_MILLION = 1_000_000


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD for a call with the given token counts.

    Returns 0.0 for unknown provider/model combinations.
    """
    provider_prices = _PRICING.get(provider, {})
    price_pair = provider_prices.get(model)
    if price_pair is None:
        # Fuzzy match: model contains a known key as prefix or substring
        for key, val in provider_prices.items():
            if model.startswith(key) or key in model:
                price_pair = val
                break
    if price_pair is None:
        return 0.0
    input_rate, output_rate = price_pair
    return (prompt_tokens * input_rate + completion_tokens * output_rate) / _PER_MILLION


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class UsageRecord:
    """One LLM API call's token usage and estimated cost."""

    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: str
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class CostTracker:
    """Thread-safe per-session and persistent LLM cost tracker.

    Maintains an in-memory list for the current session and appends each
    record to a JSONL file for cross-session history.

    Obtain the process-wide instance via :func:`get_cost_tracker`.
    """

    def __init__(self, history_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._session: list[UsageRecord] = []
        self._history_path: Path = history_path or (
            Path.home() / ".sentinel" / "cost_history.jsonl"
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        provider: str,
        model: str,
        usage: dict[str, Any],
        run_id: str | None = None,
    ) -> UsageRecord:
        """Record token usage from an LLM API response usage block.

        Args:
            provider: Provider key (``"openai"``, ``"anthropic"`` …).
            model: Model identifier.
            usage: Usage dict from the API (keys differ by provider).
            run_id: Optional grouping key (e.g. agent run UUID).

        Returns:
            The recorded :class:`UsageRecord`.
        """
        # OpenAI uses prompt_tokens/completion_tokens; Anthropic uses
        # input_tokens/output_tokens.  Accept both.
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        total = int(usage.get("total_tokens") or (prompt + completion))
        cost = estimate_cost(provider, model, prompt, completion)
        rec = UsageRecord(
            provider=provider,
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            cost_usd=cost,
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=run_id,
        )
        with self._lock:
            self._session.append(rec)
        self._append(rec)
        logger.debug(
            "cost_tracker: %s/%s p=%d c=%d $%.6f",
            provider,
            model,
            prompt,
            completion,
            cost,
        )
        return rec

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def session_summary(self) -> dict[str, Any]:
        """Aggregate usage stats for the current session."""
        with self._lock:
            records = list(self._session)
        if not records:
            return {
                "total_calls": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "by_model": {},
            }

        by_model: dict[str, dict[str, Any]] = {}
        for r in records:
            key = f"{r.provider}/{r.model}"
            if key not in by_model:
                by_model[key] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_usd": 0.0,
                }
            entry = by_model[key]
            entry["calls"] += 1
            entry["prompt_tokens"] += r.prompt_tokens
            entry["completion_tokens"] += r.completion_tokens
            entry["cost_usd"] = round(entry["cost_usd"] + r.cost_usd, 8)

        return {
            "total_calls": len(records),
            "total_prompt_tokens": sum(r.prompt_tokens for r in records),
            "total_completion_tokens": sum(r.completion_tokens for r in records),
            "total_tokens": sum(r.total_tokens for r in records),
            "total_cost_usd": round(sum(r.cost_usd for r in records), 6),
            "by_model": by_model,
        }

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return up to *limit* most recent records from persisted history."""
        if not self._history_path.exists():
            return []
        try:
            lines = self._history_path.read_text(encoding="utf-8").splitlines()
            out: list[dict[str, Any]] = []
            for line in lines[-limit:]:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            return out
        except OSError:
            return []

    def reset_session(self) -> None:
        """Clear in-memory session records (history file unchanged)."""
        with self._lock:
            self._session.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _append(self, rec: UsageRecord) -> None:
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with self._history_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.to_dict()) + "\n")
        except OSError as exc:
            logger.warning("cost_tracker: persist failed: %s", exc)


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_singleton: CostTracker | None = None
_singleton_lock = threading.Lock()


def get_cost_tracker() -> CostTracker:
    """Return the process-wide :class:`CostTracker` singleton."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = CostTracker()
    return _singleton
