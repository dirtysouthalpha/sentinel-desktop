"""WebSocket transport for cross-node mesh event delivery."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.server import ServerConnection
from websockets.exceptions import InvalidStatus

logger = logging.getLogger(__name__)

# Type alias for event handler
EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass
class PeerConnection:
    """Tracks a connection to/from a peer node."""

    node_id: str
    uri: str | None = None
    is_outgoing: bool = True
    ws: ClientConnection | ServerConnection | None = None
    retry_count: int = 0
    connected: bool = False


class WebSocketTransport:
    """Full-mesh WebSocket transport for fleet events.

    Each node runs a server (accepts incoming) and connects to known peers.
    Events published on the local EventBus are forwarded to all peers.
    Events received from peers are delivered to the local EventBus.
    """

    def __init__(
        self,
        node_id: str,
        listen_host: str = "0.0.0.0",
        listen_port: int = 4433,
        auth_token: str = "",
    ) -> None:
        self.node_id = node_id
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.auth_token = auth_token
        self._peers: dict[str, PeerConnection] = {}
        self._server: websockets.asyncio.server.Server | None = None
        self._remote_handler: EventHandler | None = None
        self._seen_events: set[str] = set()
        self._seen_lock = asyncio.Lock()
        self._max_seen = 10_000
        self._tasks: set[asyncio.Task] = set()
        self._running = False

    def on_remote_event(self, handler: EventHandler) -> None:
        """Register handler for events received from remote peers."""
        self._remote_handler = handler

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._running = True
        self._server = await websockets.serve(
            self._handle_incoming,
            self.listen_host,
            self.listen_port,
        )
        logger.info(
            "Mesh transport listening on %s:%d", self.listen_host, self.listen_port
        )

    async def connect_to_peer(self, node_id: str, uri: str) -> None:
        """Connect to a peer node with auto-reconnect."""
        if node_id == self.node_id:
            return  # Don't connect to self
        peer = PeerConnection(node_id=node_id, uri=uri, is_outgoing=True)
        self._peers[node_id] = peer
        task = asyncio.create_task(self._maintain_peer_connection(peer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def send_to_peers(self, envelope: dict[str, Any]) -> None:
        """Send an event envelope to all connected peers."""
        for peer in self._peers.values():
            if peer.connected and peer.ws is not None:
                try:
                    await peer.ws.send(json.dumps(envelope))
                except Exception:
                    logger.debug("Failed to send to peer %s", peer.node_id)
                    peer.connected = False

    async def _handle_incoming(self, ws: ServerConnection) -> None:
        """Handle an incoming WebSocket connection from a peer."""
        try:
            # Auth handshake (first message must be auth)
            auth_msg = await asyncio.wait_for(ws.recv(), timeout=10)
            auth_data = json.loads(auth_msg)
            if not self._check_auth(auth_data.get("token", "")):
                await ws.close(1008, "Auth failed")
                return
            peer_node_id = auth_data.get("node_id", "unknown")
            if peer_node_id == self.node_id:
                await ws.close(1008, "Self-connection")
                return

            # Register peer
            if peer_node_id in self._peers:
                peer = self._peers[peer_node_id]
                peer.ws = ws
                peer.connected = True
                peer.retry_count = 0
            else:
                peer = PeerConnection(
                    node_id=peer_node_id,
                    is_outgoing=False,
                    ws=ws,
                    connected=True,
                )
                self._peers[peer_node_id] = peer

            logger.info("Peer connected: %s", peer_node_id)

            # Receive loop
            async for message in ws:
                try:
                    envelope = json.loads(message)
                    await self._handle_remote_event(envelope)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from peer %s", peer_node_id)

        except asyncio.TimeoutError:
            logger.warning("Auth timeout on incoming connection")
        except websockets.ConnectionClosed:
            pass
        except Exception:
            logger.exception("Error handling incoming connection")
        finally:
            # Mark peer as disconnected
            for p in self._peers.values():
                if p.ws is ws:
                    p.connected = False
                    p.ws = None
                    logger.info("Peer disconnected: %s", p.node_id)
                    break

    async def _maintain_peer_connection(self, peer: PeerConnection) -> None:
        """Maintain an outgoing connection with exponential backoff reconnect."""
        while self._running:
            try:
                async with websockets.connect(peer.uri) as ws:
                    # Auth handshake
                    await ws.send(
                        json.dumps(
                            {
                                "type": "auth",
                                "token": self.auth_token,
                                "node_id": self.node_id,
                            }
                        )
                    )
                    peer.ws = ws
                    peer.connected = True
                    peer.retry_count = 0
                    logger.info("Connected to peer %s", peer.node_id)

                    # Receive loop
                    async for message in ws:
                        try:
                            envelope = json.loads(message)
                            await self._handle_remote_event(envelope)
                        except json.JSONDecodeError:
                            logger.warning(
                                "Invalid JSON from peer %s", peer.node_id
                            )

            except InvalidStatus as e:
                if e.response.status_code == 1008:
                    logger.error(
                        "Auth rejected by peer %s — check token", peer.node_id
                    )
                    return  # Don't retry on auth failure
                logger.warning(
                    "Peer %s rejected connection: %s", peer.node_id, e
                )
            except Exception:
                logger.debug("Connection to peer %s failed", peer.node_id)
            finally:
                peer.connected = False
                peer.ws = None

            # Exponential backoff
            if not self._running:
                break
            delay = min(1.0 * (2 ** peer.retry_count), 60.0)
            peer.retry_count += 1
            logger.info(
                "Reconnecting to %s in %.0fs (attempt %d)",
                peer.node_id,
                delay,
                peer.retry_count,
            )
            await asyncio.sleep(delay)

    async def _handle_remote_event(self, envelope: dict[str, Any]) -> None:
        """Deduplicate and dispatch a remote event."""
        event_id = envelope.get("event_id")
        if not event_id:
            return

        async with self._seen_lock:
            if event_id in self._seen_events:
                return  # Already seen — dedup
            self._seen_events.add(event_id)
            # Cap memory usage
            if len(self._seen_events) > self._max_seen:
                # Remove oldest half
                excess = len(self._seen_events) - self._max_seen // 2
                for _ in range(excess):
                    try:
                        self._seen_events.pop()
                    except KeyError:
                        break

        if self._remote_handler:
            await self._remote_handler(envelope)

    def _check_auth(self, token: str) -> bool:
        """Constant-time token comparison."""
        if not self.auth_token:
            return True  # Auth disabled
        return hmac.compare_digest(token, self.auth_token)

    async def stop(self) -> None:
        """Stop the transport and close all connections."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("Mesh transport stopped")
