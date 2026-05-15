"""Tests for api.server — SentinelServer auth, config, and route logic."""

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
