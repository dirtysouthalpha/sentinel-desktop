"""Tests for the WebSocket transport layer."""
import asyncio

import pytest
import pytest_asyncio

from core.mesh.transport import PeerConnection, WebSocketTransport


@pytest_asyncio.fixture
async def transport_a():
    """Create transport A on port 14433."""
    t = WebSocketTransport(
        node_id="node-a",
        listen_port=14433,
        auth_token="test-token",
    )
    await t.start()
    yield t
    await t.stop()


@pytest_asyncio.fixture
async def transport_b():
    """Create transport B on port 14434."""
    t = WebSocketTransport(
        node_id="node-b",
        listen_port=14434,
        auth_token="test-token",
    )
    await t.start()
    yield t
    await t.stop()


class TestWebSocketTransport:
    def test_construct(self):
        t = WebSocketTransport(node_id="test", listen_port=4433)
        assert t.node_id == "test"
        assert t._remote_handler is None

    @pytest.mark.asyncio
    async def test_connect_and_send(self, transport_a, transport_b):
        """Two transports can connect and exchange messages."""
        received = []
        transport_b.on_remote_event(lambda env: received.append(env))

        await transport_a.connect_to_peer("node-b", "ws://127.0.0.1:14434")
        # Wait for connection
        for _ in range(50):
            if transport_a._peers.get("node-b", PeerConnection("")).connected:
                break
            await asyncio.sleep(0.1)

        envelope = {"type": "test.event", "event_id": "evt-1", "data": {"key": "value"}}
        await transport_a.send_to_peers(envelope)

        # Wait for delivery
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0]["event_id"] == "evt-1"
        assert received[0]["data"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_dedup(self, transport_a, transport_b):
        """Duplicate events are filtered."""
        received = []
        transport_b.on_remote_event(lambda env: received.append(env))

        await transport_a.connect_to_peer("node-b", "ws://127.0.0.1:14434")
        for _ in range(50):
            if transport_a._peers.get("node-b", PeerConnection("")).connected:
                break
            await asyncio.sleep(0.1)

        envelope = {"type": "test.event", "event_id": "evt-dup", "data": {}}
        await transport_a.send_to_peers(envelope)
        await transport_a.send_to_peers(envelope)  # Duplicate

        await asyncio.sleep(0.5)
        assert len(received) == 1  # Only one delivered

    @pytest.mark.asyncio
    async def test_self_connection_rejected(self, transport_a):
        """Connecting to self is a no-op."""
        await transport_a.connect_to_peer("node-a", "ws://127.0.0.1:14433")
        await asyncio.sleep(0.2)
        assert "node-a" not in transport_a._peers
