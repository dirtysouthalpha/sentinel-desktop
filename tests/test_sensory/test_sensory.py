"""Tests for the sensory network agents."""

from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestScreenAgent:
    """Tests for the screen monitoring agent."""

    def test_default_config(self):
        from core.sensory.screen_agent import ScreenConfig
        config = ScreenConfig()
        assert config.capture_interval_seconds == 5.0
        assert config.change_threshold == 0.05
        assert config.enabled is True

    def test_agent_lifecycle(self):
        from core.sensory.screen_agent import ScreenAgent, ScreenConfig
        agent = ScreenAgent(ScreenConfig(capture_interval_seconds=0.1, enabled=True))
        assert agent.is_running is False
        agent.start()
        assert agent.is_running is True
        agent.stop()
        assert agent.is_running is False

    def test_callback_registration(self):
        from core.sensory.screen_agent import ScreenAgent
        agent = ScreenAgent()
        events = []
        agent.on_change(lambda e: events.append(e))
        assert len(agent._callbacks) == 1

    def test_emit_screen_event(self):
        from core.sensory.screen_agent import ScreenAgent, ScreenEvent
        agent = ScreenAgent()
        received = []
        agent.on_change(lambda e: received.append(e))
        event = ScreenEvent(timestamp=time.time(), change_percent=0.15, changed=True, description="test")
        agent._emit(event)
        assert len(received) == 1
        assert received[0].changed is True
        assert received[0].change_percent == 0.15

    def test_get_last_image_initially_none(self):
        from core.sensory.screen_agent import ScreenAgent
        agent = ScreenAgent()
        assert agent.get_last_image() is None


class TestProcessAgent:
    """Tests for the process monitoring agent."""

    def test_default_config(self):
        from core.sensory.process_agent import ProcessConfig
        config = ProcessConfig()
        assert config.check_interval_seconds == 10.0
        assert config.cpu_alert_threshold == 80.0
        assert config.enabled is True

    def test_agent_lifecycle(self):
        from core.sensory.process_agent import ProcessAgent, ProcessConfig
        agent = ProcessAgent(ProcessConfig(check_interval_seconds=0.1, enabled=True))
        assert agent.is_running is False
        agent.start()
        assert agent.is_running is True
        agent.stop()
        assert agent.is_running is False

    def test_process_event_types(self):
        from core.sensory.process_agent import ProcessAgent, ProcessEvent
        agent = ProcessAgent()
        received = []
        agent.on_change(lambda e: received.append(e))

        # Test new process event
        event = ProcessEvent(timestamp=time.time(), event_type="new", pid=1234, name="python")
        agent._emit(event)
        assert received[-1].event_type == "new"

        # Test high cpu event
        event = ProcessEvent(timestamp=time.time(), event_type="high_cpu", pid=1234, name="python", details="CPU: 95%")
        agent._emit(event)
        assert received[-1].event_type == "high_cpu"

    def test_known_processes_empty_initially(self):
        from core.sensory.process_agent import ProcessAgent
        agent = ProcessAgent()
        assert agent.get_known_processes() == {}


class TestNetworkAgent:
    """Tests for the network monitoring agent."""

    def test_default_config(self):
        from core.sensory.network_agent import NetworkConfig
        config = NetworkConfig()
        assert config.check_interval_seconds == 30.0
        assert config.ping_timeout == 5
        assert config.enabled is True

    def test_agent_lifecycle(self):
        from core.sensory.network_agent import NetworkAgent, NetworkConfig
        agent = NetworkAgent(NetworkConfig(check_interval_seconds=0.1, enabled=True))
        assert agent.is_running is False
        agent.start()
        assert agent.is_running is True
        agent.stop()
        assert agent.is_running is False

    def test_peer_info_dataclass(self):
        from core.sensory.network_agent import PeerInfo
        peer = PeerInfo(hostname="test-machine", ip="100.86.200.42", online=True)
        assert peer.hostname == "test-machine"
        assert peer.ip == "100.86.200.42"
        assert peer.online is True

    def test_network_event_creation(self):
        from core.sensory.network_agent import NetworkEvent
        event = NetworkEvent(timestamp=time.time(), event_type="peer_online", hostname="NUKE")
        assert event.event_type == "peer_online"

    def test_get_peers_empty_initially(self):
        from core.sensory.network_agent import NetworkAgent
        agent = NetworkAgent()
        assert agent.get_peers() == {}
        assert agent.get_online_peers() == []


class TestSensoryFusion:
    """Tests for the sensory fusion engine."""

    def test_default_state(self):
        from core.sensory.fusion import SensoryFusion
        fusion = SensoryFusion()
        state = fusion.get_world_state()
        assert state.summary == "no recent events"
        assert state.screen_changed is False
        assert state.process_count == 0

    def test_ingest_screen_event(self):
        from core.sensory.fusion import SensoryFusion
        from core.sensory.screen_agent import ScreenEvent
        fusion = SensoryFusion()
        event = ScreenEvent(timestamp=time.time(), changed=True, change_percent=0.15)
        fusion.ingest_screen(event)
        state = fusion.get_world_state()
        assert state.screen_changed is True
        assert state.screen_change_percent == 0.15

    def test_ingest_process_event(self):
        from core.sensory.fusion import SensoryFusion
        from core.sensory.process_agent import ProcessEvent
        fusion = SensoryFusion()
        event = ProcessEvent(timestamp=time.time(), event_type="new", pid=1234, name="nginx")
        fusion.ingest_process(event)
        state = fusion.get_world_state()
        assert len(state.new_processes) == 1
        assert "nginx" in state.new_processes[0]

    def test_ingest_network_event(self):
        from core.sensory.fusion import SensoryFusion
        from core.sensory.network_agent import NetworkEvent
        fusion = SensoryFusion()
        event = NetworkEvent(timestamp=time.time(), event_type="peer_online", hostname="homeserver")
        fusion.ingest_network(event)
        state = fusion.get_world_state()
        assert "homeserver" in state.online_peers

    def test_summary_generation(self):
        from core.sensory.fusion import SensoryFusion
        from core.sensory.process_agent import ProcessEvent
        from core.sensory.screen_agent import ScreenEvent
        fusion = SensoryFusion()
        fusion.ingest_screen(ScreenEvent(timestamp=time.time(), changed=True, change_percent=0.20))
        fusion.ingest_process(ProcessEvent(timestamp=time.time(), event_type="new", pid=1, name="test"))
        state = fusion.get_world_state()
        assert "20" in state.summary  # may format as "20.0%" or "0.20"
        assert "new processes" in state.summary

    def test_clear(self):
        from core.sensory.fusion import SensoryFusion
        from core.sensory.screen_agent import ScreenEvent
        fusion = SensoryFusion()
        fusion.ingest_screen(ScreenEvent(timestamp=time.time(), changed=True, change_percent=0.10))
        fusion.clear()
        state = fusion.get_world_state()
        assert state.screen_changed is False
        assert state.summary == "no recent events"


class TestWorldModel:
    """Tests for the world model (persistent memory bridge)."""

    def test_without_memory(self):
        from core.sensory.world_model import WorldModel
        wm = WorldModel(memory=None)
        # Should not raise
        wm.record_observation("test", "something happened")
        wm.record_episode("service_restart", "Jellyfin restarted")
        assert wm.query_memory("test") == []
        # Pass a state to get non-empty context
        from core.sensory.fusion import WorldState
        state = WorldState(timestamp=time.time(), summary="test summary")
        assert "Current State" in wm.get_full_context(state)

    def test_with_mock_memory(self):
        from core.sensory.world_model import WorldModel
        mock_mem = MagicMock()
        mock_mem.search.return_value = []
        wm = WorldModel(memory=mock_mem)
        wm.record_observation("test", "observed something")
        wm.record_episode("crash", "service crashed")
        assert mock_mem.store.call_count == 2

    def test_full_context_includes_state(self):
        from core.sensory.fusion import WorldState
        from core.sensory.world_model import WorldModel
        wm = WorldModel(memory=None)
        state = WorldState(timestamp=time.time(), summary="screen changed 15%")
        context = wm.get_full_context(state)
        assert "screen changed" in context


class TestSensoryIntegration:
    """Integration-style tests showing how agents work together."""

    def test_agents_register_callbacks_on_fusion(self):
        from core.sensory.fusion import SensoryFusion
        from core.sensory.process_agent import ProcessAgent
        from core.sensory.screen_agent import ScreenAgent

        fusion = SensoryFusion()
        screen = ScreenAgent()
        process = ProcessAgent()

        # Wire agents to fusion
        screen.on_change(fusion.ingest_screen)
        process.on_change(fusion.ingest_process)

        # Emit events
        from core.sensory.process_agent import ProcessEvent
        from core.sensory.screen_agent import ScreenEvent
        fusion.ingest_screen(ScreenEvent(timestamp=time.time(), changed=True, change_percent=0.10))
        fusion.ingest_process(ProcessEvent(timestamp=time.time(), event_type="new", pid=1, name="test"))

        state = fusion.get_world_state()
        assert state.screen_changed is True
        assert len(state.new_processes) == 1

    def test_world_model_tracks_episodes(self):
        import tempfile

        from core.memory.long_term import LongTermMemory
        from core.sensory.world_model import WorldModel
        tmp = tempfile.mktemp(suffix=".db")
        memory = LongTermMemory(db_path=tmp)
        wm = WorldModel(memory=memory)
        wm.record_episode("backup_complete", "Jellyfin backup completed")
        episodes = memory.search(category="episodes")
        assert len(episodes) >= 1
        # Note: file cleanup skipped on Windows — SQLite keeps handle
