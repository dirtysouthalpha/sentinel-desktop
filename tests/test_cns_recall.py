"""Tests for the CNS Recall Evaluator."""
import time
import pytest
from core.cns.recall import (
    GoldenQuery,
    QueryResult,
    RecallReport,
    RecallEvaluator,
    GOLDEN_QUERIES,
    make_http_backend,
)


class TestGoldenQuery:
    def test_golden_query_creation(self):
        gq = GoldenQuery("test query", 12345, "test label")
        assert gq.query == "test query"
        assert gq.expected_neuron_id == 12345
        assert gq.label == "test label"


class TestQueryResult:
    def test_query_result_creation(self):
        qr = QueryResult(query="test", expected_id=1, hit=True, rank=0)
        assert qr.hit is True
        assert qr.rank == 0


class TestRecallReport:
    def test_empty_report(self):
        report = RecallReport(timestamp="2026-01-01T00:00:00Z")
        assert report.total == 0
        assert report.hits == 0
        assert report.hit_rate == 0.0
        assert report.meets_target is False

    def test_all_pass(self):
        report = RecallReport(timestamp="now")
        report.results = [
            QueryResult("q1", 1, True, 0),
            QueryResult("q2", 2, True, 1),
            QueryResult("q3", 3, True, 0),
        ]
        assert report.hits == 3
        assert report.hit_rate == 100.0
        assert report.meets_target is True

    def test_mixed_results(self):
        report = RecallReport(timestamp="now")
        report.results = [
            QueryResult("q1", 1, True, 0),
            QueryResult("q2", 2, False, -1),
            QueryResult("q3", 3, True, 0),
            QueryResult("q4", 4, False, -1),
        ]
        assert report.hits == 2
        assert report.misses == 2
        assert report.hit_rate == 50.0
        assert report.meets_target is False

    def test_exactly_85_percent(self):
        """85% hit rate meets the target."""
        report = RecallReport(timestamp="now")
        # 20 queries, 17 pass = 85%
        for i in range(17):
            report.results.append(QueryResult(f"q{i}", i, True, 0))
        for i in range(3):
            report.results.append(QueryResult(f"q{i+17}", i+17, False, -1))
        assert report.hit_rate == 85.0
        assert report.meets_target is True

    def test_just_below_85_percent(self):
        """84.9% fails the target."""
        report = RecallReport(timestamp="now")
        for i in range(16):
            report.results.append(QueryResult(f"q{i}", i, True, 0))
        for i in range(3):
            report.results.append(QueryResult(f"q{i+16}", i+16, False, -1))
        # 16/19 = 84.2%
        assert report.meets_target is False

    def test_summary_includes_hit_rate(self):
        report = RecallReport(timestamp="2026-07-29T00:00:00Z")
        report.results = [QueryResult("q1", 1, True, 0)]
        summary = report.summary()
        assert "100.0%" in summary
        assert "PASS" in summary

    def test_summary_lists_misses(self):
        report = RecallReport(timestamp="now")
        report.results = [
            QueryResult("good query", 1, True, 0),
            QueryResult("bad query", 2, False, -1),
        ]
        summary = report.summary()
        assert "bad query" in summary

    def test_mean_latency(self):
        report = RecallReport(timestamp="now")
        report.results = [
            QueryResult("q1", 1, True, 0, latency_seconds=0.1),
            QueryResult("q2", 2, True, 0, latency_seconds=0.3),
        ]
        assert report.mean_latency == pytest.approx(0.2)

    def test_misses_list(self):
        report = RecallReport(timestamp="now")
        report.results = [
            QueryResult("q1", 1, True, 0),
            QueryResult("q2", 2, False, -1),
            QueryResult("q3", 3, False, -1),
        ]
        misses = report.misses_list()
        assert len(misses) == 2


class TestRecallEvaluator:
    def test_no_backend_all_miss(self):
        """Without a backend, all queries miss."""
        ev = RecallEvaluator(backend=None, golden_queries=[
            GoldenQuery("test", 1, "t"),
            GoldenQuery("other", 2, "o"),
        ])
        report = ev.run()
        assert report.total == 2
        assert report.hits == 0

    def test_perfect_backend(self):
        """A backend that always returns the expected ID scores 100%."""
        def perfect_backend(query, k=8):
            # Return a result with id matching what's expected.
            # We need to extract the expected id from the query.
            # The test uses queries with a known suffix.
            return [{"id": int(query.split("_")[1])}]

        queries = [
            GoldenQuery("q_1", 1),
            GoldenQuery("q_2", 2),
            GoldenQuery("q_3", 3),
        ]
        ev = RecallEvaluator(backend=perfect_backend, golden_queries=queries)
        report = ev.run()
        assert report.hits == 3
        assert report.hit_rate == 100.0

    def test_partial_backend(self):
        """A backend that returns some expected IDs."""
        def partial_backend(query, k=8):
            results = []
            if "a" in query:
                results.append({"id": 1})
            if "b" in query:
                results.append({"id": 2})
            return results

        queries = [
            GoldenQuery("a query", 1),  # hit
            GoldenQuery("b query", 2),  # hit
            GoldenQuery("c query", 3),  # miss
        ]
        ev = RecallEvaluator(backend=partial_backend, golden_queries=queries)
        report = ev.run()
        assert report.hits == 2
        assert report.misses == 1

    def test_backend_returns_neuron_id_key(self):
        """Backend uses 'neuron_id' instead of 'id' key."""
        def backend(query, k=8):
            return [{"neuron_id": 42, "content": "test"}]

        queries = [GoldenQuery("test", 42)]
        ev = RecallEvaluator(backend=backend, golden_queries=queries)
        report = ev.run()
        assert report.hits == 1

    def test_backend_exception_handled(self):
        """Backend raising an exception doesn't crash the eval."""
        def bad_backend(query, k=8):
            raise RuntimeError("connection refused")

        queries = [GoldenQuery("test", 1)]
        ev = RecallEvaluator(backend=bad_backend, golden_queries=queries)
        report = ev.run()  # should not raise
        assert report.hits == 0
        assert report.total == 1

    def test_default_golden_queries_exist(self):
        """Default golden query suite is non-empty."""
        assert len(GOLDEN_QUERIES) >= 10

    def test_rank_tracking(self):
        """Rank is correctly recorded when expected ID is not first."""
        def backend(query, k=8):
            return [
                {"id": 99, "content": "wrong"},
                {"id": 1, "content": "expected"},
                {"id": 88, "content": "wrong"},
            ]

        queries = [GoldenQuery("test", 1)]
        ev = RecallEvaluator(backend=backend, golden_queries=queries)
        report = ev.run()
        assert report.hits == 1
        assert report.results[0].rank == 1


class TestMakeHttpBackend:
    def test_returns_callable(self):
        backend = make_http_backend("http://localhost:8001")
        assert callable(backend)
        assert "http" in backend.__name__
