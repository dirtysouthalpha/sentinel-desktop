"""
Tests for the v28.0.0 Swarm Orchestration module.
"""
from core.swarm import SwarmManager, Swarm, SwarmTask, SwarmAgent, get_manager


class TestSwarmManager:
    def test_create_swarm(self):
        mgr = SwarmManager()
        swarm = mgr.create_swarm("test-swarm", agent_count=3)
        assert swarm.name == "test-swarm"
        assert len(swarm.agents) == 3
        assert swarm.status == "active"

    def test_assign_task(self):
        mgr = SwarmManager()
        swarm = mgr.create_swarm("test", agent_count=2)
        result = mgr.assign_task(swarm.id, "open notepad")
        assert result["success"]
        assert result["task_id"] in swarm.tasks

    def test_complete_task(self):
        mgr = SwarmManager()
        swarm = mgr.create_swarm("test", agent_count=1)
        result = mgr.assign_task(swarm.id, "do something")
        task_id = result["task_id"]
        result = mgr.complete_task(swarm.id, task_id, {"steps": 5})
        assert result["success"]
        assert swarm.tasks[task_id].status == "completed"

    def test_stop_swarm(self):
        mgr = SwarmManager()
        swarm = mgr.create_swarm("test", agent_count=2)
        mgr.assign_task(swarm.id, "task1")
        result = mgr.stop_swarm(swarm.id)
        assert result["success"]
        assert swarm.status == "stopped"

    def test_list_swarms(self):
        mgr = SwarmManager()
        mgr.create_swarm("swarm1", agent_count=1)
        mgr.create_swarm("swarm2", agent_count=2)
        swarms = mgr.list_swarms()
        assert len(swarms) >= 2

    def test_assign_nonexistent_swarm(self):
        mgr = SwarmManager()
        result = mgr.assign_task("fake-id", "goal")
        assert not result["success"]


class TestSwarmTask:
    def test_dataclass(self):
        t = SwarmTask(id="t1", goal="test goal")
        assert t.id == "t1"
        assert t.status == "pending"
        assert t.is_ready
        assert t.elapsed == 0.0


class TestSwarmAgent:
    def test_dataclass(self):
        a = SwarmAgent(id="a1", name="Agent 1")
        assert a.id == "a1"
        assert a.status == "idle"
        assert a.tasks_completed == 0
