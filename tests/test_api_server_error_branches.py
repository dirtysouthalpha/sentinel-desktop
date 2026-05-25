"""Tests for api.server error-handling branches and the WebSocket/broadcast
machinery — the except-clauses in REST handlers, the agent-run crash broadcast,
_async_broadcast dead-client pruning, _broadcast_event scheduling, and the
_handle_ws connection lifecycle."""

import asyncio
import threading
import time

import pytest
from fastapi import HTTPException, WebSocketDisconnect

import api.server as mod
from api.server import SentinelServer
from config import Config


def _run(coro):
    return asyncio.run(coro)


def _make_server():
    return SentinelServer(Config())


def _raise(exc):
    """Return a function that raises *exc* regardless of arguments."""

    def _fn(*_args, **_kwargs):
        raise exc

    return _fn


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Engine:
    """Bare engine stand-in; attach attributes per-test as needed."""

    running = False
    step = 0
    max_steps = 50
    notes: list = []
    forensic_log: list = []
    on_step_callback = None


class _FakeWS:
    """Async WebSocket double supporting accept/receive/send/close."""

    def __init__(self, incoming=None, raise_on_send=False):
        # incoming: list of items to yield from receive_text(). An item that is
        # an Exception instance is raised instead of returned.
        self._incoming = list(incoming or [])
        self.raise_on_send = raise_on_send
        self.sent: list = []
        self.accepted = False
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        if not self._incoming:
            raise WebSocketDisconnect(1000)
        item = self._incoming.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def send_json(self, data):
        if self.raise_on_send:
            raise OSError("send failed")
        self.sent.append(data)

    async def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# create_app lifespan — captures the running loop on startup (lines 206-207)
# ---------------------------------------------------------------------------


class TestLifespan:
    def test_lifespan_captures_running_loop(self):
        server = _make_server()
        app = server.create_app()

        async def _drive():
            async with app.router.lifespan_context(app):
                assert server._loop is asyncio.get_running_loop()

        _run(_drive())


# ---------------------------------------------------------------------------
# _handle_goal — agent run crash broadcasts an error event (lines 325-327)
# ---------------------------------------------------------------------------


class TestGoalRunCrash:
    def test_run_crash_broadcasts_error(self, monkeypatch):
        server = _make_server()
        events: list = []
        server._broadcast_event = lambda e: events.append(e)

        class CrashEngine:
            running = False
            on_step_callback = None

            def __init__(self, cfg=None):
                pass

            def run(self, goal):
                raise RuntimeError("boom")

        monkeypatch.setattr(mod, "AgentEngine", CrashEngine)
        server.config.load = lambda: {}
        req = mod.GoalRequest(goal="do thing")
        result = _run(server._handle_goal(req, authorization=None))
        assert result["status"] == "started"
        server._run_thread.join(timeout=2)
        assert any(e.get("type") == "error" and "boom" in e.get("message", "") for e in events)

    def test_run_success_broadcasts_done(self, monkeypatch):
        server = _make_server()
        events: list = []
        server._broadcast_event = lambda e: events.append(e)

        class OkEngine:
            running = False
            on_step_callback = None

            def __init__(self, cfg=None):
                pass

            def run(self, goal):
                return {"steps": 3, "finish_summary": "all done"}

        monkeypatch.setattr(mod, "AgentEngine", OkEngine)
        server.config.load = lambda: {}
        req = mod.GoalRequest(goal="x")
        _run(server._handle_goal(req, authorization=None))
        server._run_thread.join(timeout=2)
        done = [e for e in events if e.get("type") == "done"]
        assert done and done[0]["result"]["steps"] == 3


# ---------------------------------------------------------------------------
# _handle_scripts_list — error branch (lines 469-471)
# ---------------------------------------------------------------------------


class TestScriptsListError:
    def test_list_scripts_oserror_returns_error(self, monkeypatch):
        monkeypatch.setattr(
            "core.recorder.ActionRecorder.list_scripts",
            _raise(OSError("no dir")),
            raising=False,
        )
        server = _make_server()
        result = _run(server._handle_scripts_list(authorization=None))
        assert result["scripts"] == []
        assert "no dir" in result["error"]


# ---------------------------------------------------------------------------
# _handle_powershell — error branch (lines 514-516)
# ---------------------------------------------------------------------------


class TestPowerShellError:
    def test_powershell_runtime_error_returns_error(self, monkeypatch):
        monkeypatch.setattr(
            "core.powershell.get_default_runner",
            _raise(RuntimeError("ps missing")),
            raising=False,
        )
        server = _make_server()
        req = mod.PowerShellRequest(command="Get-Process")
        result = _run(server._handle_powershell(req, authorization=None))
        assert result["success"] is False
        assert "ps missing" in result["error"]


# ---------------------------------------------------------------------------
# _handle_recorder_start / _handle_recorder_stop — error branches
# (lines 527-528, 540-541, 552-554)
# ---------------------------------------------------------------------------


class TestRecorderErrors:
    def test_recorder_start_failure_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _Rec:
            def start_recording(self, _label):
                raise RuntimeError("device busy")

        server.engine.recorder = _Rec()
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_recorder_start(authorization=None))
        assert exc.value.status_code == 500

    def test_recorder_stop_failure_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _Rec:
            def stop_recording(self):
                raise RuntimeError("not recording")

        server.engine.recorder = _Rec()
        req = mod.RecorderStopRequest(name="x")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_recorder_stop(req, authorization=None))
        assert exc.value.status_code == 500

    def test_recorder_stop_save_failure_500(self, monkeypatch):
        server = _make_server()
        server.engine = _Engine()

        class _Script:
            name = ""
            description = ""
            steps: list = []

            def save(self, path):
                raise OSError("disk full")

        class _Rec:
            def stop_recording(self):
                return _Script()

        server.engine.recorder = _Rec()
        monkeypatch.setattr(mod.os, "makedirs", lambda *a, **k: None)
        req = mod.RecorderStopRequest(name="my script")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_recorder_stop(req, authorization=None))
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# Scheduler handlers — error branches (lines 613-614, 626-627, 639-640)
# ---------------------------------------------------------------------------


class TestSchedulerErrors:
    def _server_with_scheduler(self, sched):
        server = _make_server()
        server.engine = _Engine()
        server.engine.scheduler = sched
        return server

    def test_schedule_add_failure_400(self):
        class _S:
            def add_task(self, data):
                raise ValueError("bad cron")

        server = self._server_with_scheduler(_S())
        req = mod.ScheduleAddRequest(name="t", goal="g", cron="* * * * *")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_schedule_add(req, authorization=None))
        assert exc.value.status_code == 400

    def test_schedule_remove_failure_500(self):
        class _S:
            def remove_task(self, tid):
                raise RuntimeError("locked")

        server = self._server_with_scheduler(_S())
        req = mod.ScheduleRemoveRequest(task_id="t1")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_schedule_remove(req, authorization=None))
        assert exc.value.status_code == 500

    def test_schedule_run_failure_500(self):
        class _S:
            def run_task_now(self, tid):
                raise KeyError("t1")

        server = self._server_with_scheduler(_S())
        req = mod.ScheduleRunRequest(task_id="t1")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_schedule_run(req, authorization=None))
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_notify — error branch (lines 655-656)
# ---------------------------------------------------------------------------


class TestNotifyError:
    def test_notify_failure_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _N:
            def notify(self, **kw):
                raise OSError("dbus down")

        server.engine.notifications = _N()
        req = mod.NotifyRequest(title="t", message="m", level="info")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_notify(req, authorization=None))
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# Plugin handlers — error branches (lines 668-669, 682-683)
# ---------------------------------------------------------------------------


class TestPluginErrors:
    def test_plugins_list_failure_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _P:
            def list_plugins(self):
                raise RuntimeError("scan failed")

        server.engine.plugin_loader = _P()
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_plugins_list(authorization=None))
        assert exc.value.status_code == 500

    def test_plugins_reload_failure_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _P:
            def reload_plugin(self, name):
                raise ImportError("no module")

        server.engine.plugin_loader = _P()
        req = mod.PluginReloadRequest(name="foo")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_plugins_reload(req, authorization=None))
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# Agent pool handlers — error branches (lines 710-711, 723-724, 736-737)
# ---------------------------------------------------------------------------


class TestAgentPoolErrors:
    def test_agents_submit_failure_400(self):
        server = _make_server()
        server.engine = _Engine()

        class _Pool:
            def submit(self, **kw):
                raise ValueError("queue full")

        server.engine.agent_pool = _Pool()
        req = mod.AgentSubmitRequest(goal="g")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_agents_submit(req, authorization=None))
        assert exc.value.status_code == 400

    def test_agents_cancel_failure_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _Pool:
            def cancel(self, sid):
                raise RuntimeError("cannot cancel")

        server.engine.agent_pool = _Pool()
        req = mod.AgentCancelRequest(session_id="s1")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_agents_cancel(req, authorization=None))
        assert exc.value.status_code == 500

    def test_agent_status_keyerror_404(self):
        server = _make_server()
        server.engine = _Engine()

        class _Pool:
            def get_status(self, sid):
                raise KeyError(sid)

        server.engine.agent_pool = _Pool()
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_agent_status("missing", authorization=None))
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Auth handlers — no-engine + error branches
# (lines 750, 763-764, 769-770, 779, 782-784, 796-798)
# ---------------------------------------------------------------------------


class _FakeRequest:
    class _Client:
        host = "10.0.0.9"

    def __init__(self, headers=None):
        self._headers = headers or {}

    @property
    def headers(self):
        return self._headers

    @property
    def client(self):
        return self._Client()


class TestAuthLogin:
    def test_login_no_engine_500(self):
        server = _make_server()
        server.engine = None
        req = mod.AuthLoginRequest(username="u", password="p")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_auth_login(req, _FakeRequest(), authorization=None))
        assert exc.value.status_code == 500

    def test_login_authenticate_error_500(self):
        server = _make_server()
        server.create_app()  # initialises rate-limit state
        server.engine = _Engine()

        class _Auth:
            def authenticate(self, u, p):
                raise ValueError("db error")

        server.engine.auth_manager = _Auth()
        req = mod.AuthLoginRequest(username="u", password="p")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_auth_login(req, _FakeRequest(), authorization=None))
        assert exc.value.status_code == 500

    def test_login_create_session_error_500(self):
        server = _make_server()
        server.create_app()
        server.engine = _Engine()

        class _Role:
            value = "admin"

        class _User:
            role = _Role()
            username = "u"

        class _Auth:
            def authenticate(self, u, p):
                return _User()

            def create_session(self, user):
                raise OSError("write failed")

        server.engine.auth_manager = _Auth()
        req = mod.AuthLoginRequest(username="u", password="p")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_auth_login(req, _FakeRequest(), authorization=None))
        assert exc.value.status_code == 500


class TestAuthLogout:
    def test_logout_no_engine_500(self):
        server = _make_server()
        server.engine = None
        req = mod.AuthLogoutRequest(token="t")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_auth_logout(req, authorization=None))
        assert exc.value.status_code == 500

    def test_logout_revoke_error_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _Auth:
            def revoke_session(self, tok):
                raise ValueError("bad token")

        server.engine.auth_manager = _Auth()
        req = mod.AuthLogoutRequest(token="t")
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_auth_logout(req, authorization=None))
        assert exc.value.status_code == 500


class TestAuthUsersError:
    def test_users_list_error_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _Auth:
            def list_users(self):
                raise OSError("db locked")

        server.engine.auth_manager = _Auth()
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_auth_users(authorization=None))
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_audit_export — error branch (lines 813-815)
# ---------------------------------------------------------------------------


class TestAuditExportError:
    def test_export_failure_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _Exporter:
            def generate_report(self, log, metadata=None, format="html"):
                raise RuntimeError("template missing")

        server.engine.audit_exporter = _Exporter()
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_audit_export(authorization=None, format="html"))
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_vault_keys — error branch (lines 826-828)
# ---------------------------------------------------------------------------


class TestVaultKeysError:
    def test_vault_keys_failure_500(self):
        server = _make_server()
        server.engine = _Engine()

        class _Vault:
            def list_keys(self):
                raise OSError("vault locked")

        server.engine.vault = _Vault()
        with pytest.raises(HTTPException) as exc:
            _run(server._handle_vault_keys(authorization=None))
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# _async_broadcast — sends to live clients, prunes dead ones (lines 846-859)
# ---------------------------------------------------------------------------


class TestAsyncBroadcast:
    def test_sends_to_all_live_clients(self):
        server = _make_server()
        a, b = _FakeWS(), _FakeWS()
        server._ws_clients = [a, b]
        _run(server._async_broadcast({"type": "step", "n": 1}))
        assert a.sent == [{"type": "step", "n": 1}]
        assert b.sent == [{"type": "step", "n": 1}]

    def test_prunes_dead_clients(self):
        server = _make_server()
        good = _FakeWS()
        bad = _FakeWS(raise_on_send=True)
        server._ws_clients = [good, bad]
        _run(server._async_broadcast({"type": "x"}))
        assert good in server._ws_clients
        assert bad not in server._ws_clients


# ---------------------------------------------------------------------------
# _broadcast_event / _broadcast_step — scheduling onto the loop (line 843)
# ---------------------------------------------------------------------------


class TestBroadcastScheduling:
    def test_broadcast_event_no_loop_is_noop(self):
        server = _make_server()
        server._loop = None
        # Should return without error and without touching clients.
        server._broadcast_event({"type": "x"})

    def test_broadcast_step_schedules_and_drops_screenshot(self):
        server = _make_server()
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        try:
            server._loop = loop
            ws = _FakeWS()
            server._ws_clients = [ws]
            server._broadcast_step(type="step", note="hi", screenshot="BIGDATA")
            deadline = time.monotonic() + 2
            while not ws.sent and time.monotonic() < deadline:
                time.sleep(0.01)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=2)
            loop.close()
        assert ws.sent, "broadcast was not delivered to the client"
        event = ws.sent[0]
        assert event["type"] == "step"
        assert event["note"] == "hi"
        assert "screenshot" not in event


# ---------------------------------------------------------------------------
# _handle_ws — connection lifecycle (lines 862-903)
# ---------------------------------------------------------------------------


class TestHandleWebSocket:
    def test_auth_then_ping_pong_then_disconnect(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        ws = _FakeWS(incoming=['{"type": "auth"}', '{"type": "ping"}'])
        _run(server._handle_ws(ws))
        assert ws.accepted
        assert {"type": "pong"} in ws.sent
        # Client was registered and then cleaned up on disconnect.
        assert ws not in server._ws_clients

    def test_invalid_token_rejected(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, "secret")
        server = _make_server()
        ws = _FakeWS(incoming=['{"type": "auth", "token": "wrong"}'])
        _run(server._handle_ws(ws))
        assert any(m.get("type") == "auth_error" for m in ws.sent)
        assert ws.closed
        assert ws not in server._ws_clients

    def test_valid_token_accepted(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, "secret")
        server = _make_server()
        ws = _FakeWS(incoming=['{"type": "auth", "token": "secret"}'])
        _run(server._handle_ws(ws))
        assert not ws.closed
        assert ws not in server._ws_clients

    def test_auth_timeout_closes(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        ws = _FakeWS(incoming=[asyncio.TimeoutError()])
        _run(server._handle_ws(ws))
        assert ws.closed

    def test_auth_invalid_json_closes(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        ws = _FakeWS(incoming=["not json"])
        _run(server._handle_ws(ws))
        assert ws.closed

    def test_auth_connection_error_closes(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        ws = _FakeWS(incoming=[RuntimeError("socket broke")])
        _run(server._handle_ws(ws))
        assert ws.closed

    def test_main_loop_ignores_invalid_json(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        server = _make_server()
        # auth ok, then garbage (ignored), then ping -> pong, then disconnect
        ws = _FakeWS(incoming=['{"type": "auth"}', "garbage", '{"type": "ping"}'])
        _run(server._handle_ws(ws))
        assert {"type": "pong"} in ws.sent
