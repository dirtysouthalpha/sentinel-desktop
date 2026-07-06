"""
Tests for the v30.0.0 Self-Learning Playbook module.
"""
from core.learning.playbook import PlaybookManager, Playbook


class TestPlaybookManager:
    def test_learn_from_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.learning.playbook.PLAYBOOK_DIR", tmp_path)
        mgr = PlaybookManager()
        runs = [
            {"goal": "open notepad", "status": "completed", "steps": 5},
            {"goal": "open notepad", "status": "completed", "steps": 4},
            {"goal": "open notepad", "status": "failed", "steps": 10},
        ]
        created = mgr.learn_from_telemetry({}, runs)
        assert created >= 1
        playbooks = mgr.list_playbooks()
        assert len(playbooks) >= 1
        assert playbooks[0]["times_used"] == 3

    def test_find_playbook(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.learning.playbook.PLAYBOOK_DIR", tmp_path)
        mgr = PlaybookManager()
        runs = [
            {"goal": "open calculator", "status": "completed", "steps": 3},
            {"goal": "open calculator", "status": "completed", "steps": 2},
        ]
        mgr.learn_from_telemetry({}, runs)
        pb = mgr.find_playbook("open calculator")
        assert pb is not None
        assert pb.success_rate > 0.5

    def test_no_playbook_for_single_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.learning.playbook.PLAYBOOK_DIR", tmp_path)
        mgr = PlaybookManager()
        runs = [{"goal": "unique task", "status": "completed", "steps": 5}]
        created = mgr.learn_from_telemetry({}, runs)
        assert created == 0

    def test_stats(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.learning.playbook.PLAYBOOK_DIR", tmp_path)
        mgr = PlaybookManager()
        stats = mgr.get_stats()
        assert "total_playbooks" in stats
        assert "total_uses" in stats


class TestPlaybookDataclass:
    def test_to_dict(self):
        pb = Playbook(id="pb-test", name="Test", goal_pattern="test pattern")
        d = pb.to_dict()
        assert d["id"] == "pb-test"
        assert d["success_rate"] == 0.0
