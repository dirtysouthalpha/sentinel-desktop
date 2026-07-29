"""Tests for conflict resolution and vector clocks."""
from core.mesh.partition import VectorClock, ConflictResolver


class TestVectorClock:
    def test_new_clock_is_zero(self):
        assert VectorClock().clocks == {}

    def test_increment(self):
        vc = VectorClock()
        vc.increment("n1")
        vc.increment("n1")
        assert vc.clocks["n1"] == 2

    def test_compare_concurrent(self):
        va = VectorClock({"n1": 2, "n2": 1})
        vb = VectorClock({"n1": 1, "n2": 2})
        assert va.compare(vb) == 0

    def test_compare_before(self):
        va = VectorClock({"n1": 1, "n2": 1})
        vb = VectorClock({"n1": 2, "n2": 2})
        assert va.compare(vb) == -1

    def test_compare_after(self):
        va = VectorClock({"n1": 3, "n2": 2})
        vb = VectorClock({"n1": 1, "n2": 1})
        assert va.compare(vb) == 1

    def test_merge(self):
        va = VectorClock({"n1": 3, "n2": 1})
        vb = VectorClock({"n1": 2, "n2": 4})
        merged = va.merge(vb)
        assert merged.clocks == {"n1": 3, "n2": 4}


class TestConflictResolver:
    def test_no_conflict_when_one_is_newer(self):
        resolver = ConflictResolver()
        old = {"clock": {"n1": 1}, "data": "old"}
        new = {"clock": {"n1": 2}, "data": "new"}
        result = resolver.resolve(old, new)
        assert result["data"] == "new"

    def test_conflict_when_concurrent(self):
        resolver = ConflictResolver()
        a = {"clock": {"n1": 2, "n2": 1}, "data": "a"}
        b = {"clock": {"n1": 1, "n2": 2}, "data": "b"}
        result = resolver.resolve(a, b)
        assert "data" in result
