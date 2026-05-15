"""Tests for api.server — SentinelServer auth, config, and route logic."""

import time

import pytest

import api.server as mod
from config import Config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeEngine:
    """Minimal fake AgentEngine for route handler tests."""

    running = False
    step = 0
    max_steps = 50
    notes: list = []

    class _recorder:
        @staticmethod
        def start_recording(_label):
            pass

        @staticmethod
        def stop_recording():
            class Script:
                name = ""
                description = ""
                steps: list = []

                def save(self, path):
                    pass

            return Script()

    class _scheduler:
        @staticmethod
        def list_tasks():
            return []

        @staticmethod
        def add_task(data):
            return "t1"

        @staticmethod
        def remove_task(tid):
            return True

        @staticmethod
        def run_task_now(tid):
            return {"ok": True}

    class _notifications:
        @staticmethod
        def notify(**kw):
            return True

    class _plugin_loader:
        @staticmethod
        def list_plugins():
            return []

        @staticmethod
        def reload_plugin(name):
            return True

    class _agent_pool:
        @staticmethod
        def list_sessions():
            return []

        @staticmethod
        def submit(**kw):
            return "s1"

        @staticmethod
        def cancel(sid):
            return True

        @staticmethod
        def get_status(sid):
            return None

    class _auth_manager:
        @staticmethod
        def authenticate(user, pw):
            return None

        @staticmethod
        def create_session(user):
            return "tok"

        @staticmethod
        def revoke_session(tok):
            pass

        @staticmethod
        def list_users():
            return []

    class _audit_exporter:
        @staticmethod
        def generate_report(log, metadata=None, format="html"):
            return "report.html"  # noqa: S108

    class _vault:
        @staticmethod
        def list_keys():
            return []

    forensic_log: list = []
    on_step_callback = None

    @property
    def recorder(self):
        return self._recorder

    @property
    def scheduler(self):
        return self._scheduler

    @property
    def notifications(self):
        return self._notifications

    @property
    def plugin_loader(self):
        return self._plugin_loader

    @property
    def agent_pool(self):
        return self._agent_pool

    @property
    def auth_manager(self):
        return self._auth_manager

    @property
    def audit_exporter(self):
        return self._audit_exporter

    @property
    def vault(self):
        return self._vault


def _make_server():
    return mod.SentinelServer(Config())


# ---------------------------------------------------------------------------
# _check_auth
# ---------------------------------------------------------------------------


class TestCheckAuth:
    def test_no_token_env_allows_all(self):
        server = _make_server()
        # No SENTINEL_API_TOKEN set → any request passes
        server._check_auth(None)
        server._check_auth("Bearer whatever")

    def test_valid_token_passes(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, "secret123")
        server = _make_server()
        server._check_auth("Bearer secret123")

    def test_invalid_token_raises(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setenv(mod.API_TOKEN_ENV, "secret123")
        server = _make_server()
        with pytest.raises(HTTPException) as exc_info:
            server._check_auth("Bearer wrong")
        assert exc_info.value.status_code == 401

    def test_missing_header_raises_when_token_set(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setenv(mod.API_TOKEN_ENV, "secret123")
        server = _make_server()
        with pytest.raises(HTTPException) as exc_info:
            server._check_auth(None)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# CORS origins
# ---------------------------------------------------------------------------


class TestCORS:
    def test_no_token_restricts_to_localhost(self, monkeypatch):
        monkeypatch.delenv(mod.API_TOKEN_ENV, raising=False)
        monkeypatch.delenv("SENTINEL_CORS_ORIGINS", raising=False)
        server = _make_server()
        app = server.create_app()
        # Find CORS middleware
        cors_mw = None
        for mw in app.user_middleware:
            if "CORSMiddleware" in str(mw):
                cors_mw = mw
                break
        assert cors_mw is not None

    def test_token_set_allows_star(self, monkeypatch):
        monkeypatch.setenv(mod.API_TOKEN_ENV, "tok")
        monkeypatch.delenv("SENTINEL_CORS_ORIGINS", raising=False)
        server = _make_server()
        app = server.create_app()
        assert app is not None

    def test_custom_origins(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_CORS_ORIGINS", "https://a.com, https://b.com")
        server = _make_server()
        app = server.create_app()
        assert app is not None


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------


class TestBroadcast:
    def test_broadcast_without_loop_is_noop(self):
        server = _make_server()
        server._loop = None
        # Should not raise
        server._broadcast_event({"type": "test"})

    def test_broadcast_step_strips_screenshot(self):
        server = _make_server()
        captured = {}
        server._broadcast_event = lambda e: captured.update(e)
        server._broadcast_step(step=1, screenshot="bigdata", action="click")
        assert "screenshot" not in captured
        assert captured["step"] == 1


# ---------------------------------------------------------------------------
# Route handlers (sync logic)
# ---------------------------------------------------------------------------


class TestHandleStop:
    def test_not_running(self):
        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.running = False
        # _handle_stop is async, but its logic is sync — just call it
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            server._handle_stop(authorization=None)
        )
        assert result["status"] == "not_running"


class TestHandleStatus:
    def test_no_engine(self):
        server = _make_server()
        server.engine = None
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            server._handle_status(authorization=None)
        )
        assert result["running"] is False

    def test_with_engine(self):
        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.running = True
        server.engine.step = 5
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            server._handle_status(authorization=None)
        )
        assert result["running"] is True
        assert result["step"] == 5


class TestHandleLog:
    def test_no_engine(self):
        server = _make_server()
        server.engine = None
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(server._handle_log(authorization=None))
        assert result["log"] == []

    def test_with_engine(self):
        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.forensic_log = [{"step": 1}]
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(server._handle_log(authorization=None))
        assert len(result["log"]) == 1


class TestHandleGetConfig:
    def test_masks_api_key(self):
        server = _make_server()
        import asyncio

        # Monkeypatch config.load to return a dict with api_key
        server.config.load = lambda: {"api_key": "supersecret", "model": "gpt-4o"}
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_get_config(authorization=None)
        )
        assert result["api_key"] == "***"
        assert result["model"] == "gpt-4o"


class TestHandleCommand:
    def test_json_action_passthrough(self, monkeypatch):
        import asyncio

        server = _make_server()
        # Patch AgentEngine to avoid real init
        fake_executor = type("E", (), {"execute_sync": lambda s, p: {"success": True}})()

        class FakeAE:
            def __init__(self, cfg):
                self.executor = fake_executor

        monkeypatch.setattr(mod, "AgentEngine", FakeAE)
        req = mod.CommandRequest(command='{"action": "click", "x": 10, "y": 20}')
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_command(req, authorization=None)
        )
        assert result["success"] is True

    def test_text_command_becomes_note(self, monkeypatch):
        import asyncio

        captured = {}

        fake_executor = type(
            "E", (), {"execute_sync": lambda s, p: captured.update(p) or {"success": True}}
        )()

        class FakeAE:
            def __init__(self, cfg):
                self.executor = fake_executor

        monkeypatch.setattr(mod, "AgentEngine", FakeAE)
        server = _make_server()
        req = mod.CommandRequest(command="hello world")
        asyncio.get_event_loop().run_until_complete(server._handle_command(req, authorization=None))
        assert captured["action"] == "note"
        assert captured["text"] == "hello world"

    def test_invalid_json_raises(self, monkeypatch):
        import asyncio

        from fastapi import HTTPException

        server = _make_server()

        class FakeAE:
            def __init__(self, cfg):
                pass

        monkeypatch.setattr(mod, "AgentEngine", FakeAE)
        req = mod.CommandRequest(command='{"bad json')
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                server._handle_command(req, authorization=None)
            )
        assert exc_info.value.status_code == 400

    def test_json_without_action_key_raises(self, monkeypatch):
        import asyncio

        from fastapi import HTTPException

        server = _make_server()

        class FakeAE:
            def __init__(self, cfg):
                pass

        monkeypatch.setattr(mod, "AgentEngine", FakeAE)
        req = mod.CommandRequest(command='{"x": 1}')
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                server._handle_command(req, authorization=None)
            )
        assert exc_info.value.status_code == 400


class TestHandlePutConfig:
    def test_save_called(self, monkeypatch):
        import asyncio

        server = _make_server()
        server.config.load = lambda: {"model": "gpt-4o"}
        saved = {}
        server.config.save = lambda cfg: saved.update(cfg)
        req = mod.ConfigUpdate(model="claude-3.5-sonnet")
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_put_config(req, authorization=None)
        )
        assert result["status"] == "saved"
        assert saved["model"] == "claude-3.5-sonnet"


class TestScheduleHandlers:
    def test_schedule_list(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_schedule_list(authorization=None)
        )
        assert result["tasks"] == []

    def test_schedule_add(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        req = mod.ScheduleAddRequest(name="test", goal="do thing")
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_schedule_add(req, authorization=None)
        )
        assert result["task_id"] == "t1"

    def test_schedule_remove(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        req = mod.ScheduleRemoveRequest(task_id="t1")
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_schedule_remove(req, authorization=None)
        )
        assert result["status"] == "removed"


class TestHandleNotify:
    def test_notify(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        req = mod.NotifyRequest(message="test")
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_notify(req, authorization=None)
        )
        assert result["success"] is True


class TestHandleAgents:
    def test_agents_list(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_agents_list(authorization=None)
        )
        assert result["sessions"] == []

    def test_agents_submit(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        req = mod.AgentSubmitRequest(goal="test")
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_agents_submit(req, authorization=None)
        )
        assert result["session_id"] == "s1"


class TestHandleAuthUsers:
    def test_auth_users(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_auth_users(authorization=None)
        )
        assert result["users"] == []


class TestHandlePluginsList:
    def test_plugins_list(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_plugins_list(authorization=None)
        )
        assert result["plugins"] == []


class TestHandleVaultKeys:
    def test_vault_keys(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_vault_keys(authorization=None)
        )
        assert result["keys"] == []


class TestHandleAuditExport:
    def test_audit_export(self):
        import asyncio

        server = _make_server()
        server.engine = _FakeEngine()
        result = asyncio.get_event_loop().run_until_complete(
            server._handle_audit_export(authorization=None)
        )
        assert "path" in result


# ---------------------------------------------------------------------------
# Additional route handler tests
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


class TestHandleGoal:
    def test_goal_starts_engine(self, monkeypatch):
        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.running = False
        server.config.load = lambda: {"max_steps": 10}

        started = {}

        class FakeEngine:
            running = False
            step = 0
            max_steps = 10
            notes: list = []
            forensic_log: list = []
            on_step_callback = None

            def __init__(self, cfg=None):
                pass

            def run(self, goal):
                started["goal"] = goal
                return {"steps": 1, "finish_summary": "done"}

        monkeypatch.setattr(mod, "AgentEngine", FakeEngine)
        req = mod.GoalRequest(goal="open notepad")
        result = _run(server._handle_goal(req, authorization=None))
        assert result["status"] == "started"
        assert result["goal"] == "open notepad"

    def test_goal_conflict_when_running(self):
        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.running = True
        from fastapi import HTTPException

        req = mod.GoalRequest(goal="open notepad")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_goal(req, authorization=None))
        assert exc_info.value.status_code == 409


class TestHandleScheduleRun:
    def test_schedule_run(self):
        server = _make_server()
        server.engine = _FakeEngine()
        req = mod.ScheduleRunRequest(task_id="t1")
        result = _run(server._handle_schedule_run(req, authorization=None))
        assert result["ok"] is True


class TestHandlePluginsReload:
    def test_plugins_reload(self):
        server = _make_server()
        server.engine = _FakeEngine()
        req = mod.PluginReloadRequest(name="test_plugin")
        result = _run(server._handle_plugins_reload(req, authorization=None))
        assert result["success"] is True
        assert result["name"] == "test_plugin"


class TestHandleAgentsCancel:
    def test_agents_cancel(self):
        server = _make_server()
        server.engine = _FakeEngine()
        req = mod.AgentCancelRequest(session_id="s1")
        result = _run(server._handle_agents_cancel(req, authorization=None))
        assert result["success"] is True


class TestHandleAgentStatus:
    def test_agent_status_found(self):
        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.agent_pool.get_status = lambda sid: {"id": sid, "status": "completed"}
        result = _run(server._handle_agent_status("s1", authorization=None))
        assert result["id"] == "s1"

    def test_agent_status_not_found(self):
        from fastapi import HTTPException

        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.agent_pool.get_status = lambda sid: None
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_agent_status("missing", authorization=None))
        assert exc_info.value.status_code == 404


class TestHandleAuthLogin:
    def _make_login_server(self):
        server = _make_server()
        # create_app() initializes _login_attempts
        server.create_app()
        server.engine = _FakeEngine()
        return server

    def test_login_success(self, monkeypatch):
        server = self._make_login_server()

        class FakeUser:
            role = type("R", (), {"value": "admin"})()
            username = "admin"

        server.engine.auth_manager.authenticate = lambda u, p: FakeUser()
        server.engine.auth_manager.create_session = lambda u: "tok123"
        req = mod.AuthLoginRequest(username="admin", password="pass")
        result = _run(server._handle_auth_login(req, authorization=None))
        assert result["token"] == "tok123"
        assert result["role"] == "admin"

    def test_login_invalid_credentials(self):
        from fastapi import HTTPException

        server = self._make_login_server()
        server.engine.auth_manager.authenticate = lambda u, p: None
        req = mod.AuthLoginRequest(username="admin", password="wrong")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_auth_login(req, authorization=None))
        assert exc_info.value.status_code == 401

    def test_login_rate_limited(self):
        from collections import defaultdict
        from fastapi import HTTPException

        server = self._make_login_server()
        server.engine.auth_manager.authenticate = lambda u, p: None
        # Pre-populate rate limiter for a known client_id
        fake_id = 42
        server._login_attempts[fake_id] = [time.monotonic()] * server._login_limit
        # Patch id in the module to return our controlled id
        import api.server as srv_mod

        orig_id = id
        srv_mod_id_ref = (
            srv_mod.__builtins__["id"] if isinstance(srv_mod.__builtins__, dict) else None
        )
        # Use monkeypatch approach: temporarily replace id in builtins
        import builtins as _bi

        _orig_id = _bi.id
        _bi.id = lambda x: fake_id
        try:
            req = mod.AuthLoginRequest(username="admin", password="wrong")
            with pytest.raises(HTTPException) as exc_info:
                _run(server._handle_auth_login(req, authorization=None))
            assert exc_info.value.status_code == 429
        finally:
            _bi.id = _orig_id


class TestHandleAuthLogout:
    def test_logout(self):
        server = _make_server()
        server.engine = _FakeEngine()
        revoked = {}
        server.engine.auth_manager.revoke_session = lambda t: revoked.update({"token": t})
        req = mod.AuthLogoutRequest(token="tok123")
        result = _run(server._handle_auth_logout(req, authorization=None))
        assert result["status"] == "logged_out"
        assert revoked["token"] == "tok123"


class TestHandleScriptsList:
    def test_scripts_list_no_engine(self, monkeypatch):
        server = _make_server()
        server.engine = _FakeEngine()
        # Patch ActionRecorder.list_scripts to return empty
        monkeypatch.setattr(
            "core.recorder.ActionRecorder.list_scripts", staticmethod(lambda d: []), raising=False
        )
        result = _run(server._handle_scripts_list(authorization=None))
        assert "scripts" in result


class TestHandleRecorderStart:
    def test_recorder_start(self):
        server = _make_server()
        server.engine = _FakeEngine()
        result = _run(server._handle_recorder_start(authorization=None))
        assert result["status"] == "recording"


class TestHandleRecorderStop:
    def test_recorder_stop(self, tmp_path, monkeypatch):
        server = _make_server()
        server.engine = _FakeEngine()
        # Patch ActionRecorder to avoid real file I/O
        monkeypatch.setattr(
            "core.recorder.ActionRecorder.stop_recording",
            lambda self=None: type(
                "Script",
                (),
                {
                    "name": "test",
                    "description": "",
                    "steps": [],
                    "save": lambda self, p: None,
                },
            )(),
            raising=False,
        )
        req = mod.RecorderStopRequest(name="test_script")
        result = _run(server._handle_recorder_stop(req, authorization=None))
        assert result["status"] == "saved"


class TestHandlePowershell:
    def test_powershell_endpoint(self, monkeypatch):
        server = _make_server()
        server.engine = _FakeEngine()

        class FakeResult:
            success = True
            stdout = "process output"
            stderr = ""
            exit_code = 0
            objects: list = []

        monkeypatch.setattr(
            "core.powershell.get_default_runner",
            lambda: type("R", (), {"run_command": lambda self, cmd: FakeResult()})(),
            raising=False,
        )
        req = mod.PowerShellRequest(command="Get-Process")
        result = _run(server._handle_powershell(req, authorization=None))
        assert result["success"] is True
        assert result["stdout"] == "process output"


class TestEngineNotInitialized:
    """Handlers that require engine should return 500 when engine is None."""

    @pytest.mark.parametrize(
        "handler_method",
        [
            "schedule_list",
            "schedule_add",
            "schedule_remove",
            "schedule_run",
            "notify",
            "plugins_list",
            "plugins_reload",
            "agents_list",
            "agents_submit",
            "agents_cancel",
            "agent_status",
            "auth_users",
            "audit_export",
            "vault_keys",
        ],
    )
    def test_returns_500_without_engine(self, handler_method):
        from fastapi import HTTPException

        server = _make_server()
        server.engine = None
        method = getattr(server, f"_handle_{handler_method}")
        with pytest.raises(HTTPException) as exc_info:
            if handler_method in ("agent_status",):
                _run(method("s1", authorization=None))
            elif handler_method in (
                "schedule_list",
                "plugins_list",
                "agents_list",
                "auth_users",
                "audit_export",
                "vault_keys",
            ):
                _run(method(authorization=None))
            elif handler_method == "schedule_run":
                _run(method(mod.ScheduleRunRequest(task_id="t1"), authorization=None))
            elif handler_method == "schedule_add":
                _run(method(mod.ScheduleAddRequest(name="t", goal="g"), authorization=None))
            elif handler_method == "schedule_remove":
                _run(method(mod.ScheduleRemoveRequest(task_id="t1"), authorization=None))
            elif handler_method == "notify":
                _run(method(mod.NotifyRequest(message="m"), authorization=None))
            elif handler_method == "plugins_reload":
                _run(method(mod.PluginReloadRequest(name="p"), authorization=None))
            elif handler_method == "agents_submit":
                _run(method(mod.AgentSubmitRequest(goal="g"), authorization=None))
            elif handler_method == "agents_cancel":
                _run(method(mod.AgentCancelRequest(session_id="s1"), authorization=None))
        assert exc_info.value.status_code == 500
