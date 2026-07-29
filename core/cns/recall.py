"""CNS Recall Evaluator — measures brain recall quality against golden queries.

The recall metric answers: "When we ask a standard set of questions, does
the brain return the relevant neuron in the top-K results?"

Target: 85%+ hit rate (golden query's expected neuron found in top-8).

This module defines a suite of golden queries with their expected top hits,
runs them against a recall backend, and produces a RecallReport.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

# A recall backend is any callable that takes (query, k) and returns
# a list of dicts with at least an "id" or "neuron_id" key.
class RecallBackend(Protocol):
    def __call__(self, query: str, k: int = 8) -> list[dict[str, Any]]: ...


@dataclass
class GoldenQuery:
    """A query with its expected top hit neuron ID."""
    query: str
    expected_neuron_id: int
    label: str = ""  # human-readable description


@dataclass
class QueryResult:
    """Result of running one golden query."""
    query: str
    expected_id: int
    hit: bool  # was expected_id in top-k?
    rank: int = -1  # position in results (0-indexed), -1 if not found
    results_count: int = 0
    latency_seconds: float = 0.0


@dataclass
class RecallReport:
    """Full recall evaluation report."""
    timestamp: str
    results: list[QueryResult] = field(default_factory=list)
    backend_name: str = "unknown"

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def hits(self) -> int:
        return sum(1 for r in self.results if r.hit)

    @property
    def misses(self) -> int:
        return self.total - self.hits

    @property
    def hit_rate(self) -> float:
        return (self.hits / self.total * 100) if self.total else 0.0

    @property
    def meets_target(self) -> bool:
        """True if hit rate is at or above the 85% target."""
        return self.hit_rate >= 85.0

    @property
    def mean_latency(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.latency_seconds for r in self.results) / len(self.results)

    def misses_list(self) -> list[QueryResult]:
        return [r for r in self.results if not r.hit]

    def summary(self) -> str:
        lines = [
            f"Recall Eval Report — {self.timestamp}",
            f"Backend: {self.backend_name}",
            f"Queries: {self.total} | Hits: {self.hits} | Misses: {self.misses}",
            f"Hit rate: {self.hit_rate:.1f}% (target: 85%)",
            f"Mean latency: {self.mean_latency:.3f}s",
            f"Status: {'PASS ✓' if self.meets_target else 'FAIL ✗ (below 85%)'}",
        ]
        if self.misses_list():
            lines.append("")
            lines.append("Misses:")
            for r in self.misses_list():
                lines.append(f"  [{r.expected_id}] \"{r.query[:50]}\"")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Golden query suite
# ---------------------------------------------------------------------------

# These queries represent the kind of context an agent needs to recall
# across sessions. The expected neuron IDs are validated against the
# live brain by the quality-tracker cron.
GOLDEN_QUERIES: list[GoldenQuery] = [
    GoldenQuery("desktop lineage canonical v30", 120797, "desktop version"),
    GoldenQuery("Neuralis brain is SENTINEL PRIME", 27, "brain identity"),
    Neuralis := GoldenQuery("Neuralis v5 shipped all phases", 119252, "neuralis v5"),
    GoldenQuery("recall performance rerank latency regression", 120809, "recall perf"),
    GoldenQuery("Tailscale mesh connects NUKE to hackbox", 20, "tailscale"),
    GoldenQuery("fleet GPU role split vision reasoning", 119565, "gpu split"),
    GoldenQuery("empire upgrade switch on safely", 37711, "empire"),
    GoldenQuery("vNext 7 phase unified orchestration", 120797, "vnext"),
    GoldenQuery("CNS reasoning engine planner evaluator", 122419, "cns"),
    Neuralis2 := GoldenQuery("homeserver clock runs behind NUKE skew", 119214, "clock skew"),
    GoldenQuery("brain semantic search shipped hybrid", 119213, "semantic search"),
    Neuralis3 := GoldenQuery("embedding backfill self-healing orphan purge", 119213, "backfill"),
    GoldenQuery("fleet mega plan 2026 do it all", 122419, "mega plan"),
    Neuralis4 := GoldenQuery("recall quality tracker golden eval", 122322, "quality tracker"),
    GoldenQuery("PremierBot third mesh node deploy", 122419, "premierbot"),
    Neuralis5 := GoldenQuery("Neuralis dual brain NUKE homeserver separate", 3348, "dual brain"),
    GoldenQuery("grid loop time bomb git incident", 8391, "git incident"),
    Neuralis6 := GoldenQuery("hermes cron jobs faculty self-test registry", 119625, "hermes cron"),
    GoldenQuery("family safety kernel model pinning", 119625, "safety kernel"),
    Neuralis7 := GoldenQuery("empire evolution engine content roadmap", 12297, "empire evolution"),
    GoldenQuery("hebbian learning synapse optimization", 1168, "hebbian"),
    GoldenQuery("knowledge graph embedding techniques", 1179, "kge"),
    GoldenQuery("self-organizing map representation", 1188, "som"),
    Neuralis8 := GoldenQuery("Neuralis backend API port 8000 frontend 5173", 67, "neuralis ports"),
    GoldenQuery("trading system autoresearch 10 modules", 16, "trading"),
    GoldenQuery("brain inspired AI architecture causal reasoning", 78391, "agi arch"),
    GoldenQuery("Windows NSSM service manager sentinel", 122415, "nssm"),
    Neuralis9 := GoldenQuery("alien history incident recovery branch", 8178, "alien"),
]


class RecallEvaluator:
    """Runs the golden query suite against a recall backend."""

    def __init__(
        self,
        backend: RecallBackend | None = None,
        golden_queries: list[GoldenQuery] | None = None,
        k: int = 8,
    ) -> None:
        self.backend = backend
        self.golden_queries = golden_queries or GOLDEN_QUERIES
        self.k = k

    def run(self) -> RecallReport:
        """Run all golden queries and produce a report."""
        report = RecallReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            backend_name=getattr(self.backend, "__name__", str(self.backend)) if self.backend else "none",
        )

        if self.backend is None:
            logger.warning("No recall backend provided — all queries will miss")
            for gq in self.golden_queries:
                report.results.append(QueryResult(
                    query=gq.query, expected_id=gq.expected_neuron_id,
                    hit=False, rank=-1,
                ))
            return report

        for gq in self.golden_queries:
            start = time.time()
            try:
                results = self.backend(gq.query, k=self.k)
                latency = time.time() - start
                # Find the expected neuron in the results.
                rank = -1
                for i, r in enumerate(results):
                    rid = r.get("id", r.get("neuron_id"))
                    if rid == gq.expected_neuron_id:
                        rank = i
                        break
                report.results.append(QueryResult(
                    query=gq.query,
                    expected_id=gq.expected_neuron_id,
                    hit=rank >= 0,
                    rank=rank,
                    results_count=len(results),
                    latency_seconds=latency,
                ))
            except Exception as e:
                latency = time.time() - start
                logger.warning("Query %r failed: %s", gq.query[:40], e)
                report.results.append(QueryResult(
                    query=gq.query,
                    expected_id=gq.expected_neuron_id,
                    hit=False,
                    rank=-1,
                    latency_seconds=latency,
                ))

        logger.info(
            "Recall eval done: %d/%d hits (%.1f%%)",
            report.hits, report.total, report.hit_rate,
        )
        return report


def make_http_backend(
    base_url: str = "http://localhost:8001",
    endpoint: str = "/neurons/search",
    api_key: str | None = None,
) -> RecallBackend:
    """Create a recall backend that hits the Neuralis brain HTTP API."""
    def backend(query: str, k: int = 8) -> list[dict[str, Any]]:
        import urllib.request
        import urllib.parse
        import json

        url = f"{base_url}{endpoint}?q={urllib.parse.quote(query)}&limit={k}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        # The brain returns {"results": [...]} — normalize.
        if isinstance(data, dict):
            return data.get("results", data.get("neurons", []))
        return data if isinstance(data, list) else []

    backend.__name__ = f"http({base_url})"  # type: ignore[attr-defined]
    return backend
