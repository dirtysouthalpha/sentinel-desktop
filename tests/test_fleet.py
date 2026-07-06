"""
Tests for the v29.0.0 Fleet Bus module.
"""
from core.fleet.redis_bus import FleetManager, FleetNode, InMemoryBus


class TestInMemoryBus:
    def test_publish_and_get(self):
        bus = InMemoryBus()
        bus.publish("test", {"msg": "hello"})
        msgs = bus.get_messages("test")
        assert len(msgs) == 1
        assert msgs[0]["data"]["msg"] == "hello"

    def test_subscribe(self):
        bus = InMemoryBus()
        received = []
        bus.subscribe("test", lambda m: received.append(m))
        bus.publish("test", {"msg": "hi"})
        assert len(received) == 1
        assert received[0]["msg"] == "hi"


class TestFleetManager:
    def test_register_node(self):
        mgr = FleetManager()
        node = mgr.register_node("node-1", hostname="server1", ip="10.0.0.1")
        assert node.id == "node-1"
        assert node.hostname == "server1"

    def test_list_nodes(self):
        mgr = FleetManager()
        mgr.register_node("node-a", hostname="a")
        mgr.register_node("node-b", hostname="b")
        nodes = mgr.list_nodes()
        assert len(nodes) >= 2

    def test_deploy_to_nonexistent_node(self):
        mgr = FleetManager()
        result = mgr.deploy_agent("fake-node", "do something")
        assert not result["success"]

    def test_deploy_to_node(self):
        mgr = FleetManager()
        mgr.register_node("deploy-target", hostname="target", ip="10.0.0.5")
        result = mgr.deploy_agent("deploy-target", "open notepad")
        assert result["success"]

    def test_fleet_health(self):
        mgr = FleetManager()
        health = mgr.get_fleet_health()
        assert "total_nodes" in health
        assert "healthy_nodes" in health
        assert health["bus_type"] == "in-memory"

    def test_publish_and_get_events(self):
        mgr = FleetManager()
        mgr.publish_event("test", {"action": "test"})
        events = mgr.get_events("test")
        assert len(events) >= 1


class TestFleetNode:
    def test_dataclass(self):
        node = FleetNode(id="n1", hostname="host", ip="1.2.3.4")
        assert node.id == "n1"
        assert node.status == "online"
        assert node.is_healthy is False  # no heartbeat yet
