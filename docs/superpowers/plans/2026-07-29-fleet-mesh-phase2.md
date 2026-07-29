# Fleet Mesh Phase 2 — Transport, Execution, Dashboard

**Date:** 2026-07-29
**Goal:** Make the mesh distributed (WebSocket transport), make it do useful work (task executor), make it visible (fleet dashboard).
**Depends on:** Phase 1 (core/mesh/ — 11 modules, 78 tests)

---

## Task 1: WebSocket Transport Layer

**Files:**
- Create: `core/mesh/transport.py`
- Modify: `core/mesh/event_bus.py` (add transport integration)
- Test: `tests/test_mesh_transport.py`

### Design

Each mesh node runs BOTH a WebSocket server (accepts peer connections) and WebSocket clients (connects to known peers). Events published locally are forwarded to all connected peers. Events received from peers are delivered to local subscribers with deduplication.

```
┌─────────────┐     WebSocket      ┌─────────────┐
│   Node A    │◄──────────────────►│   Node B    │
│  Server:4433│                    │  Server:4434 │
│  Client ─────────► B:4434        │  Client ─────────► A:4433
│  EventBus   │                    │  EventBus   │
└─────────────┘                    └─────────────┘
```

### `core/mesh/transport.py`

```python
"""WebSocket transport for cross-node mesh event delivery."""
from __future__ import annotations

import asyncio
import json
import logging
import hmac
import os
from typing import Any, Awaitable, Callable, Optional
from dataclasses import dataclass, field

import websockets
from websockets.server import WebSocketServerProtocol
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)

# Type alias for event handler
EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass
class PeerConnection:
    """Tracks a connection to/from a peer node."""
    node_id: str
    uri: str | None = None
    is_outgoing: bool = True
    ws: WebSocketClientProtocol | WebSocketServerProtocol | None = None
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
        self._server: websockets.server.WebSocketServer | None = None
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
        logger.info("Mesh transport listening on %s:%d", self.listen_host, self.listen_port)

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

    async def _handle_incoming(
        self, ws: WebSocketServerProtocol, path: str
    ) -> None:
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
                    await ws.send(json.dumps({
                        "type": "auth",
                        "token": self.auth_token,
                        "node_id": self.node_id,
                    }))
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
                            logger.warning("Invalid JSON from peer %s", peer.node_id)

            except websockets.InvalidStatusCode as e:
                if e.status_code == 1008:
                    logger.error("Auth rejected by peer %s — check token", peer.node_id)
                    return  # Don't retry on auth failure
                logger.warning("Peer %s rejected connection: %s", peer.node_id, e)
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
            logger.info("Reconnecting to %s in %.0fs (attempt %d)", peer.node_id, delay, peer.retry_count)
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
```

### Modify `core/mesh/event_bus.py`

Add a `set_transport` method and modify `publish` to forward to peers:

```python
# Add import at top
from core.mesh.transport import WebSocketTransport

# In EventBus.__init__, add:
self._transport: WebSocketTransport | None = None

# Add method:
def set_transport(self, transport: WebSocketTransport) -> None:
    """Set the remote transport for cross-node event delivery."""
    self._transport = transport
    transport.on_remote_event(self._handle_remote_event)

# Add handler:
async def _handle_remote_event(self, envelope: dict[str, Any]) -> None:
    """Deliver a remote event to local subscribers."""
    event_type = envelope.get("type")
    if event_type and event_type in self._handlers:
        results = await asyncio.gather(
            *[self._safe_call(h, envelope) for h in self._handlers[event_type]],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Handler error for %s: %s", event_type, result)

# Modify publish() to forward to peers:
# After local delivery, add:
if self._transport:
    await self._transport.send_to_peers(envelope)
```

### `tests/test_mesh_transport.py`

```python
"""Tests for the WebSocket transport layer."""
import asyncio
import json
import pytest
import pytest_asyncio
from core.mesh.transport import WebSocketTransport


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
    async def test_auth_rejects_wrong_token(self):
        server = WebSocketTransport(
            node_id="server", listen_port=14435, auth_token="right-token"
        )
        await server.start()
        try:
            client = WebSocketTransport(
                node_id="client", listen_port=14436, auth_token="wrong-token"
            )
            await client.start()
            with pytest.raises(Exception):
                await asyncio.wait_for(
                    websockets.connect("ws://127.0.0.1:14435"),
                    timeout=2,
                )
                # Send wrong auth
                ws = await websockets.connect("ws://127.0.0.1:14435")
                await ws.send(json.dumps({"token": "wrong-token", "node_id": "client"}))
                await asyncio.wait_for(ws.recv(), timeout=2)
            await client.stop()
        finally:
            await server.stop()

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


# Need to import PeerConnection for the test
from core.mesh.transport import PeerConnection
```

### EventBus integration test

Add to `tests/test_mesh_event_bus.py`:

```python
@pytest.mark.asyncio
async def test_publish_forwards_to_transport():
    """EventBus forwards events to the transport."""
    from core.mesh.transport import WebSocketTransport

    bus = EventBus()
    mock_transport = AsyncMock()
    bus.set_transport(mock_transport)

    received = []
    bus.subscribe("test.event", lambda evt: received.append(evt))
    await bus.publish("test.event", {"key": "value"})

    await asyncio.sleep(0.01)
    assert len(received) == 1
    mock_transport.send_to_peers.assert_called_once()
    envelope = mock_transport.send_to_peers.call_args[0][0]
    assert envelope["type"] == "test.event"
    assert envelope["data"]["key"] == "value"
```

---

## Task 2: Task Executor

**Files:**
- Create: `core/mesh/executor.py`
- Test: `tests/test_mesh_executor.py`

### Design

The `TaskExecutor` subscribes to `TASK_ASSIGNED` events on the EventBus. When a task is assigned to this node, it executes based on task type and publishes `TASK_COMPLETED` or `TASK_FAILED`.

### `core/mesh/executor.py`

```python
"""Task executor for the fleet mesh."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from typing import Any, Awaitable, Callable

from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.node import NodeCapabilities
from core.mesh.task_graph import Task, TaskStatus

logger = logging.getLogger(__name__)

# Type alias
EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class TaskExecutor:
    """Executes tasks assigned to this node via the mesh event bus."""

    def __init__(
        self,
        node_id: str,
        bus: EventBus,
        capabilities: NodeCapabilities,
    ) -> None:
        self.node_id = node_id
        self.bus = bus
        self.capabilities = capabilities
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
            "shell": self._exec_shell,
            "python": self._exec_python,
            "action": self._exec_action,
            "llm": self._exec_llm,
        }
        self._running = False

    def start(self) -> None:
        """Start listening for task assignments."""
        self._running = True
        self.bus.subscribe(FleetEvent.TASK_ASSIGNED, self._on_task_assigned)
        logger.info("Task executor started for node %s", self.node_id)

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        self.bus.unsubscribe(FleetEvent.TASK_ASSIGNED, self._on_task_assigned)

    async def _on_task_assigned(self, envelope: dict[str, Any]) -> None:
        """Handle task assignment."""
        if not self._running:
            return
        data = envelope.get("data", {})
        assigned_node = data.get("node_id", "")
        if assigned_node != self.node_id:
            return  # Not for us

        task_id = data.get("task_id", "")
        plan_id = data.get("plan_id", "")
        task_type = data.get("task_type", "shell")
        task_goal = data.get("goal", "")
        task_params = data.get("params", {})

        logger.info("Executing task %s (type=%s): %s", task_id, task_type, task_goal)

        # Publish TASK_RUNNING
        await self.bus.publish(FleetEvent.TASK_RUNNING, {
            "task_id": task_id,
            "plan_id": plan_id,
            "node_id": self.node_id,
        })

        # Execute
        try:
            handler = self._handlers.get(task_type, self._exec_shell)
            result = await handler({
                "task_id": task_id,
                "goal": task_goal,
                "params": task_params,
            })
            # Success
            await self.bus.publish(FleetEvent.TASK_COMPLETED, {
                "task_id": task_id,
                "plan_id": plan_id,
                "node_id": self.node_id,
                "result": result,
            })
        except Exception as e:
            logger.exception("Task %s execution failed", task_id)
            await self.bus.publish(FleetEvent.TASK_FAILED, {
                "task_id": task_id,
                "plan_id": plan_id,
                "node_id": self.node_id,
                "error": str(e),
            })

    async def _exec_shell(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a shell command."""
        command = task.get("params", {}).get("command", task.get("goal", ""))
        if not command:
            raise ValueError("No command specified for shell task")

        timeout = task.get("params", {}).get("timeout", 60)
        cwd = task.get("params", {}).get("cwd", None)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed (exit {proc.returncode}): {stderr.decode().strip()}"
            )
        return {
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
            "exit_code": proc.returncode,
        }

    async def _exec_python(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a Python function."""
        module_path = task.get("params", {}).get("module", "")
        function_name = task.get("params", {}).get("function", "")
        args = task.get("params", {}).get("args", [])
        kwargs = task.get("params", {}).get("kwargs", {})

        if not module_path or not function_name:
            raise ValueError("Python task requires 'module' and 'function' params")

        import importlib
        mod = importlib.import_module(module_path)
        func = getattr(mod, function_name)
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return {"return_value": repr(result)}

    async def _exec_action(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a Sentinel Desktop action."""
        action_name = task.get("params", {}).get("action", "")
        action_params = task.get("params", {}).get("action_params", {})
        if not action_name:
            raise ValueError("Action task requires 'action' param")
        # Placeholder — would integrate with core.actions
        return {"action": action_name, "status": "executed", "params": action_params}

    async def _exec_llm(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute an LLM call."""
        prompt = task.get("goal", "")
        model = task.get("params", {}).get("model", "default")
        if not prompt:
            raise ValueError("LLM task requires a goal/prompt")
        # Placeholder — would integrate with core.engine
        return {"model": model, "prompt": prompt, "response": "LLM response placeholder"}
```

### `tests/test_mesh_executor.py`

```python
"""Tests for the task executor."""
import asyncio
import pytest
import pytest_asyncio
from core.mesh.executor import TaskExecutor
from core.mesh.event_bus import EventBus, FleetEvent
from core.mesh.node import NodeCapabilities


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def capabilities():
    return NodeCapabilities(
        can_orchestrate=False,
        can_execute_desktop=True,
        can_reason=True,
        can_remember=True,
    )


@pytest.fixture
def executor(bus, capabilities):
    ex = TaskExecutor(node_id="test-node", bus=bus, capabilities=capabilities)
    ex.start()
    yield ex
    ex.stop()


class TestTaskExecutor:
    def test_construct(self, bus, capabilities):
        ex = TaskExecutor(node_id="n1", bus=bus, capabilities=capabilities)
        assert ex.node_id == "n1"
        assert not ex._running

    @pytest.mark.asyncio
    async def test_exec_shell_command(self, executor):
        """Shell task executes a command."""
        result = await executor._exec_shell({
            "task_id": "t1",
            "goal": "echo hello",
            "params": {"command": "echo hello world"},
        })
        assert result["stdout"] == "hello world"
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exec_shell_failure(self, executor):
        """Shell task raises on non-zero exit."""
        with pytest.raises(RuntimeError, match="exit"):
            await executor._exec_shell({
                "task_id": "t1",
                "goal": "",
                "params": {"command": "exit 1"},
            })

    @pytest.mark.asyncio
    async def test_exec_shell_timeout(self, executor):
        """Shell task times out."""
        with pytest.raises(asyncio.TimeoutError):
            await executor._exec_shell({
                "task_id": "t1",
                "goal": "",
                "params": {"command": "sleep 10", "timeout": 1},
            })

    @pytest.mark.asyncio
    async def test_task_assignment_triggers_execution(self, executor, bus):
        """TASK_ASSIGNED event triggers execution."""
        completed = []
        bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

        await bus.publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "t1",
            "plan_id": "p1",
            "node_id": "test-node",
            "task_type": "shell",
            "goal": "echo test",
            "params": {"command": "echo test output"},
        })

        # Wait for execution
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert completed[0]["data"]["task_id"] == "t1"
        assert completed[0]["data"]["result"]["stdout"] == "test output"

    @pytest.mark.asyncio
    async def test_task_for_other_node_ignored(self, executor, bus):
        """Tasks assigned to other nodes are ignored."""
        completed = []
        bus.subscribe(FleetEvent.TASK_COMPLETED, lambda env: completed.append(env))

        await bus.publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "t1",
            "plan_id": "p1",
            "node_id": "other-node",
            "task_type": "shell",
            "goal": "echo test",
            "params": {"command": "echo test"},
        })

        await asyncio.sleep(0.3)
        assert len(completed) == 0

    @pytest.mark.asyncio
    async def test_execution_failure_publishes_task_failed(self, executor, bus):
        """Failed execution publishes TASK_FAILED."""
        failed = []
        bus.subscribe(FleetEvent.TASK_FAILED, lambda env: failed.append(env))

        await bus.publish(FleetEvent.TASK_ASSIGNED, {
            "task_id": "t1",
            "plan_id": "p1",
            "node_id": "test-node",
            "task_type": "shell",
            "goal": "",
            "params": {"command": "exit 42"},
        })

        for _ in range(100):
            if failed:
                break
            await asyncio.sleep(0.05)

        assert len(failed) == 1
        assert failed[0]["data"]["task_id"] == "t1"
        assert "exit 42" in failed[0]["data"]["error"] or "42" in failed[0]["data"]["error"]

    @pytest.mark.asyncio
    async def test_exec_python(self, executor):
        """Python task executes a function."""
        result = await executor._exec_python({
            "task_id": "t1",
            "goal": "",
            "params": {
                "module": "os.path",
                "function": "join",
                "args": ["/tmp", "test.txt"],
            },
        })
        assert "/tmp" in result["return_value"]
        assert "test.txt" in result["return_value"]
```

---

## Task 3: Fleet Dashboard GUI Tab

**Files:**
- Create: `gui/tabs/fleet_tab.py`
- Modify: `gui/app.py` (register tab)
- Test: `tests/test_fleet_tab.py`

### Design

A new tab in the Sentinel Desktop GUI showing fleet status. Uses customtkinter (matching existing tabs). Polls local state and subscribes to EventBus events for real-time updates.

### `gui/tabs/fleet_tab.py`

```python
"""Fleet Mesh dashboard tab for Sentinel Desktop GUI."""
from __future__ import annotations

import logging
import threading
from typing import Any

import customtkinter as ctk

logger = logging.getLogger(__name__)


class FleetTab:
    """Displays fleet mesh status: nodes, tasks, events, leader."""

    def __init__(self, parent_frame: ctk.CTkFrame, app: Any) -> None:
        self.app = app
        self._t = app._t
        self.frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        self._build_ui()
        self._poll_interval = 2000  # ms
        self._scheduled_poll: str | None = None
        self._start_polling()

    def _build_ui(self) -> None:
        """Build the fleet dashboard UI."""
        # Title
        title = ctk.CTkLabel(
            self.frame,
            text="🛰️ Fleet Mesh",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=(10, 5), padx=10, anchor="w")

        # Status frame
        status_frame = ctk.CTkFrame(self.frame)
        status_frame.pack(fill="x", padx=10, pady=5)

        self._leader_label = ctk.CTkLabel(
            status_frame, text="Leader: —", font=ctk.CTkFont(size=12)
        )
        self._leader_label.pack(anchor="w", padx=10, pady=2)

        self._nodes_label = ctk.CTkLabel(
            status_frame, text="Nodes: 0", font=ctk.CTkFont(size=12)
        )
        self._nodes_label.pack(anchor="w", padx=10, pady=2)

        self._tasks_label = ctk.CTkLabel(
            status_frame, text="Tasks: 0 active", font=ctk.CTkFont(size=12)
        )
        self._tasks_label.pack(anchor="w", padx=10, pady=2)

        # Node list
        nodes_header = ctk.CTkLabel(
            self.frame, text="Nodes", font=ctk.CTkFont(size=14, weight="bold")
        )
        nodes_header.pack(pady=(10, 2), padx=10, anchor="w")

        self._nodes_text = ctk.CTkTextbox(self.frame, height=120, font=ctk.CTkFont(size=11))
        self._nodes_text.pack(fill="x", padx=10, pady=2)

        # Event log
        events_header = ctk.CTkLabel(
            self.frame, text="Recent Events", font=ctk.CTkFont(size=14, weight="bold")
        )
        events_header.pack(pady=(10, 2), padx=10, anchor="w")

        self._events_text = ctk.CTkTextbox(self.frame, height=200, font=ctk.CTkFont(size=11))
        self._events_text.pack(fill="both", expand=True, padx=10, pady=2)

        # Control buttons
        btn_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=5)

        self._refresh_btn = ctk.CTkButton(
            btn_frame, text="🔄 Refresh", command=self._refresh, width=100
        )
        self._refresh_btn.pack(side="left", padx=5)

        self._clear_btn = ctk.CTkButton(
            btn_frame, text="🗑️ Clear Events", command=self._clear_events, width=120
        )
        self._clear_btn.pack(side="left", padx=5)

    def _start_polling(self) -> None:
        """Start periodic refresh."""
        self._refresh()
        self._schedule_next_poll()

    def _schedule_next_poll(self) -> None:
        """Schedule the next poll."""
        if hasattr(self.app, 'root') and self.app.root is not None:
            try:
                self._scheduled_poll = self.app.root.after(
                    self._poll_interval, self._poll_callback
                )
            except RuntimeError:
                pass  # Root destroyed

    def _poll_callback(self) -> None:
        """Called by after() — reschedule and refresh."""
        self._refresh()
        self._schedule_next_poll()

    def _refresh(self) -> None:
        """Refresh the display with current fleet state."""
        try:
            # Get fleet data from the app's mesh components
            mesh_data = getattr(self.app, '_fleet_data', None)
            if mesh_data is None:
                self._leader_label.configure(text="Leader: — (mesh not started)")
                return

            leader = mesh_data.get("leader", "—")
            nodes = mesh_data.get("nodes", [])
            tasks = mesh_data.get("tasks", [])

            self._leader_label.configure(text=f"Leader: {leader}")
            self._nodes_label.configure(text=f"Nodes: {len(nodes)}")
            self._tasks_label.configure(text=f"Tasks: {len(tasks)} active")

            # Update nodes text
            self._nodes_text.configure(state="normal")
            self._nodes_text.delete("0.0", "end")
            for node in nodes:
                status_icon = "🟢" if node.get("alive") else "🔴"
                self._nodes_text.insert("end", f"{status_icon} {node.get('node_id', '?')} (pri={node.get('priority', '?')}) — {node.get('status', '?')}\n")
            self._nodes_text.configure(state="disabled")

        except Exception as e:
            logger.debug("Fleet refresh error: %s", e)

    def _clear_events(self) -> None:
        """Clear the event log."""
        self._events_text.configure(state="normal")
        self._events_text.delete("0.0", "end")
        self._events_text.configure(state="disabled")

    def add_event(self, event_text: str) -> None:
        """Add an event to the log (thread-safe)."""
        try:
            if hasattr(self.app, 'root') and self.app.root is not None:
                self.app.root.after(0, lambda: self._append_event(event_text))
        except RuntimeError:
            pass

    def _append_event(self, event_text: str) -> None:
        """Append event on main thread."""
        self._events_text.configure(state="normal")
        self._events_text.insert("0.0", event_text + "\n")
        # Cap at 500 lines
        lines = self._events_text.get("0.0", "end").split("\n")
        if len(lines) > 500:
            self._events_text.delete("500.0", "end")
        self._events_text.configure(state="disabled")

    def destroy(self) -> None:
        """Clean up polling."""
        if self._scheduled_poll and hasattr(self.app, 'root') and self.app.root is not None:
            try:
                self.app.root.after_cancel(self._scheduled_poll)
            except RuntimeError:
                pass
```

### Modify `gui/app.py`

In `_build_tabs()`, add after the existing tabs:

```python
# Fleet Mesh tab (optional — only if mesh is available)
try:
    from gui.tabs.fleet_tab import FleetTab
    tab_fleet = self.tabview.add("🛰️ Fleet")
    self.fleet_tab = FleetTab(tab_fleet, self)
except ImportError as e:
    logger.debug("Fleet tab not available: %s", e)
```

### `tests/test_fleet_tab.py`

```python
"""Tests for the fleet dashboard tab."""
import pytest
from unittest.mock import MagicMock, patch


class TestFleetTab:
    def test_construct(self):
        """FleetTab can be constructed with mock app."""
        from gui.tabs.fleet_tab import FleetTab

        mock_app = MagicMock()
        mock_app._t = MagicMock()
        mock_app.root = MagicMock()
        mock_app.root.after.return_value = "poll_id"

        parent = MagicMock()
        tab = FleetTab(parent, mock_app)
        assert tab.app is mock_app
        assert tab._poll_interval == 2000

    def test_refresh_no_data(self):
        """Refresh handles missing fleet data gracefully."""
        from gui.tabs.fleet_tab import FleetTab

        mock_app = MagicMock()
        mock_app._t = MagicMock()
        mock_app.root = MagicMock()
        mock_app.root.after.return_value = "poll_id"
        mock_app._fleet_data = None

        parent = MagicMock()
        tab = FleetTab(parent, mock_app)
        tab._refresh()  # Should not raise

    def test_add_event(self):
        """Add event calls root.after."""
        from gui.tabs.fleet_tab import FleetTab

        mock_app = MagicMock()
        mock_app._t = MagicMock()
        mock_app.root = MagicMock()
        mock_app.root.after.return_value = "poll_id"

        parent = MagicMock()
        tab = FleetTab(parent, mock_app)
        tab.add_event("test event")
        mock_app.root.after.assert_called()

    def test_destroy_cancels_poll(self):
        """Destroy cancels pending poll."""
        from gui.tabs.fleet_tab import FleetTab

        mock_app = MagicMock()
        mock_app._t = MagicMock()
        mock_app.root = MagicMock()
        mock_app.root.after.return_value = "poll_id"

        parent = MagicMock()
        tab = FleetTab(parent, mock_app)
        tab.destroy()
        mock_app.root.after_cancel.assert_called_once_with("poll_id")
```

---

## Task 4: Integration & Full Test Suite

**Files:**
- No new files — wire everything together and verify

### Steps

1. **Update `core/mesh/__init__.py`** to export `WebSocketTransport`, `TaskExecutor`

2. **Update `main.py`** mesh mode to optionally start transport and executor:
```python
# In mesh mode, after creating orch:
from core.mesh.transport import WebSocketTransport
from core.mesh.executor import TaskExecutor

transport = WebSocketTransport(
    node_id=node_id,
    listen_port=args.mesh_port or 4433,
    auth_token=os.environ.get("MESH_AUTH_TOKEN", ""),
)
await transport.start()

executor = TaskExecutor(node_id=node_id, bus=bus, capabilities=capabilities)
executor.start()

# Connect to peers from config
for peer_uri in args.mesh_peers or []:
    peer_id = peer_uri.split("/")[-1]  # Simple extraction
    await transport.connect_to_peer(peer_id, peer_uri)
```

3. **Run full test suite**: `pytest tests/ -q --tb=short`

4. **Run lint**: `ruff check core/mesh/`

5. **Fix any failures**

6. **Commit**

---

## Self-Review Checklist

1. Transport: auth handshake, dedup, reconnect, self-connection rejection
2. Executor: shell/python/action/llm types, event-driven, error handling
3. Dashboard: thread-safe updates, polling, event log
4. Integration: transport wired into EventBus, executor subscribes to events
5. Tests: all new code covered, existing tests still pass
