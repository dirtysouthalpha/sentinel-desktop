"""
Tests for the v28.0.0 Vector Memory Store module.
"""
from core.memory.vector_store import VectorMemoryStore


class TestVectorMemoryStore:
    def test_add_and_search(self, tmp_path):
        store = VectorMemoryStore(db_path=tmp_path / "vm.json")
        store.add("open notepad and type hello", actions=["click", "type"], outcome="success", success=True)
        store.add("open browser and navigate to google.com", actions=["click", "type"], outcome="success", success=True)
        results = store.search("open notepad")
        assert len(results) > 0
        assert "notepad" in results[0]["goal"]

    def test_search_empty_store(self, tmp_path):
        store = VectorMemoryStore(db_path=tmp_path / "vm.json")
        results = store.search("anything")
        assert results == []

    def test_stats(self, tmp_path):
        store = VectorMemoryStore(db_path=tmp_path / "vm.json")
        store.add("goal 1", success=True)
        store.add("goal 2", success=False)
        stats = store.get_stats()
        assert stats["total_entries"] == 2
        assert stats["successful"] == 1
        assert stats["failed"] == 1

    def test_clear(self, tmp_path):
        store = VectorMemoryStore(db_path=tmp_path / "vm.json")
        store.add("goal 1")
        store.clear()
        assert store.get_stats()["total_entries"] == 0

    def test_persistence(self, tmp_path):
        db = tmp_path / "vm.json"
        store1 = VectorMemoryStore(db_path=db)
        store1.add("persistent goal", success=True)
        store2 = VectorMemoryStore(db_path=db)
        stats = store2.get_stats()
        assert stats["total_entries"] == 1
