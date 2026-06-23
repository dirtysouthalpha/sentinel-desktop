"""Tests for untested api.server handlers — screenshot, windows, processes,
system, script_run, workflows, workflow builder, and _get_client_ip."""

import asyncio

import pytest

import api.server as mod
from api.server import SentinelServer
from config import Config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def _make_server():
    return SentinelServer(Config())


class _FakeRequest:
    """Minimal fake starlette.Request for _get_client_ip tests."""

    class _Client:
        host = "10.0.0.5"

    _client_obj = _Client()

    def __init__(self, headers=None):
        self._headers = headers or {}

    @property
    def headers(self):
        return self._headers

    @property
    def client(self):
        return self._client_obj


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
            return "report.html"

    class _vault:
        @staticmethod
        def list_keys():
            return []

    forensic_log: list = []
    on_step_callback = None

    class _executor:
        pass

    class _script_engine:
        pass

    executor = _executor()
    script_engine = _script_engine()

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


# ---------------------------------------------------------------------------
# _get_client_ip
# ---------------------------------------------------------------------------


class TestGetClientIP:
    """Tests for SentinelServer._get_client_ip static method.

    Forwarded headers (X-Forwarded-For / X-Real-IP) are SPOOFABLE by the
    caller, so by default they are ignored and ``request.client.host`` is
    returned directly. Set ``SENTINEL_TRUST_PROXY=1`` when Sentinel runs
    behind a trusted reverse proxy that overwrites those headers.
    """

    def test_forwarded_headers_ignored_by_default(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_TRUST_PROXY", raising=False)
        # XFF present but no opt-in → must fall back to the socket peer so a
        # single host can't rotate fake IPs to dodge the per-IP rate limiter.
        req = _FakeRequest(headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
        assert SentinelServer._get_client_ip(req) == "10.0.0.5"

    def test_real_ip_ignored_by_default(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_TRUST_PROXY", raising=False)
        req = _FakeRequest(headers={"x-real-ip": "192.168.1.1"})
        assert SentinelServer._get_client_ip(req) == "10.0.0.5"

    def test_trust_proxy_enables_xff_first_ip(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_TRUST_PROXY", "1")
        req = _FakeRequest(headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
        assert SentinelServer._get_client_ip(req) == "1.2.3.4"

    def test_trust_proxy_enables_single_xff(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_TRUST_PROXY", "1")
        req = _FakeRequest(headers={"x-forwarded-for": "9.8.7.6"})
        assert SentinelServer._get_client_ip(req) == "9.8.7.6"

    def test_trust_proxy_enables_x_real_ip(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_TRUST_PROXY", "1")
        req = _FakeRequest(headers={"x-real-ip": "192.168.1.1"})
        assert SentinelServer._get_client_ip(req) == "192.168.1.1"

    def test_trust_proxy_xff_takes_priority_over_real_ip(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_TRUST_PROXY", "1")
        req = _FakeRequest(headers={"x-forwarded-for": "1.1.1.1", "x-real-ip": "2.2.2.2"})
        assert SentinelServer._get_client_ip(req) == "1.1.1.1"

    def test_fallback_to_client_host(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_TRUST_PROXY", raising=False)
        req = _FakeRequest(headers={})
        assert SentinelServer._get_client_ip(req) == "10.0.0.5"

    def test_unknown_when_no_client(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_TRUST_PROXY", raising=False)

        class NoClientReq:
            @property
            def headers(self):
                return {}

            @property
            def client(self):
                return None

        assert SentinelServer._get_client_ip(NoClientReq()) == "unknown"


# ---------------------------------------------------------------------------
# _handle_screenshot
# ---------------------------------------------------------------------------


class TestHandleScreenshot:
    def test_screenshot_success(self, monkeypatch):
        monkeypatch.setattr(mod, "capture_to_base64", lambda: "base64data")
        server = _make_server()
        result = _run(server._handle_screenshot(authorization=None))
        assert result["screenshot"] == "base64data"
        assert result["format"] == "png"
        assert result["encoding"] == "base64"

    def test_screenshot_capture_failure(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(
            mod, "capture_to_base64", lambda: (_ for _ in ()).throw(OSError("no display"))
        )
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_screenshot(authorization=None))
        assert exc_info.value.status_code == 500

    def test_screenshot_value_error(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(
            mod, "capture_to_base64", lambda: (_ for _ in ()).throw(ValueError("bad"))
        )
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_screenshot(authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_windows
# ---------------------------------------------------------------------------


class TestHandleWindows:
    def test_windows_success(self, monkeypatch):
        fake_windows = [{"title": "Notepad", "hwnd": 1234}]
        monkeypatch.setattr(mod.wm, "list_windows", lambda: fake_windows)
        server = _make_server()
        result = _run(server._handle_windows(authorization=None))
        assert result["windows"] == fake_windows

    def test_windows_oserror(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(mod.wm, "list_windows", lambda: (_ for _ in ()).throw(OSError("fail")))
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_windows(authorization=None))
        assert exc_info.value.status_code == 500

    def test_windows_runtime_error(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(
            mod.wm, "list_windows", lambda: (_ for _ in ()).throw(RuntimeError("crash"))
        )
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_windows(authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_processes
# ---------------------------------------------------------------------------


class TestHandleProcesses:
    def test_processes_success(self, monkeypatch):
        fake_procs = [{"pid": 1, "name": "init"}]
        monkeypatch.setattr(mod.pm, "list_processes", lambda limit=100: fake_procs)
        server = _make_server()
        result = _run(server._handle_processes(authorization=None))
        assert result["processes"] == fake_procs

    def test_processes_passes_limit_100(self, monkeypatch):
        captured = {}

        def fake_list(limit=100):
            captured["limit"] = limit
            return []

        monkeypatch.setattr(mod.pm, "list_processes", fake_list)
        server = _make_server()
        _run(server._handle_processes(authorization=None))
        assert captured["limit"] == 100

    def test_processes_oserror(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(
            mod.pm, "list_processes", lambda limit=100: (_ for _ in ()).throw(OSError("fail"))
        )
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_processes(authorization=None))
        assert exc_info.value.status_code == 500

    def test_processes_runtime_error(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(
            mod.pm, "list_processes", lambda limit=100: (_ for _ in ()).throw(RuntimeError("crash"))
        )
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_processes(authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_system
# ---------------------------------------------------------------------------


class TestHandleSystem:
    def test_system_success(self, monkeypatch):
        fake_info = {"cpu": "Intel", "ram_gb": 16}
        monkeypatch.setattr(mod.sysinfo, "system_info", lambda: fake_info)
        server = _make_server()
        result = _run(server._handle_system(authorization=None))
        assert result["system"] == fake_info

    def test_system_oserror(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(
            mod.sysinfo, "system_info", lambda: (_ for _ in ()).throw(OSError("fail"))
        )
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_system(authorization=None))
        assert exc_info.value.status_code == 500

    def test_system_runtime_error(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(
            mod.sysinfo, "system_info", lambda: (_ for _ in ()).throw(RuntimeError("crash"))
        )
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_system(authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_script_run
# ---------------------------------------------------------------------------


class TestHandleScriptRun:
    def test_script_run_no_engine_500(self):
        from fastapi import HTTPException

        server = _make_server()
        server.engine = None
        req = mod.ScriptRunRequest(path="/scripts/test.json")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_script_run(req, authorization=None))
        assert exc_info.value.status_code == 500

    def test_script_run_success(self, monkeypatch):
        server = _make_server()
        server.engine = _FakeEngine()

        class FakeScriptEngine:
            def __init__(self, executor):
                pass

            class _Result:
                success = True
                steps_completed = 3
                steps_total = 5
                error = None

            def run_script(self, path, params):
                return self._Result()

        monkeypatch.setattr("core.script_engine.ScriptEngine", FakeScriptEngine, raising=False)
        req = mod.ScriptRunRequest(path="/scripts/test.json")
        result = _run(server._handle_script_run(req, authorization=None))
        assert result["success"] is True
        assert result["steps_completed"] == 3
        assert result["steps_total"] == 5

    def test_script_run_value_error(self, monkeypatch):
        from fastapi import HTTPException

        server = _make_server()
        server.engine = _FakeEngine()

        class FakeScriptEngine:
            def __init__(self, executor):
                pass

            def run_script(self, path, params):
                raise ValueError("bad script")

        monkeypatch.setattr("core.script_engine.ScriptEngine", FakeScriptEngine, raising=False)
        req = mod.ScriptRunRequest(path="/scripts/bad.json")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_script_run(req, authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_workflows_list
# ---------------------------------------------------------------------------


class TestHandleWorkflowsList:
    def test_workflows_list_success(self, monkeypatch):
        fake_workflows = [{"name": "wf1", "path": "/wf/test.json"}]
        monkeypatch.setattr(
            "core.workflow.WorkflowEngine.list_workflows",
            lambda wf_dir: fake_workflows,
            raising=False,
        )
        server = _make_server()
        result = _run(server._handle_workflows_list(authorization=None))
        assert result["workflows"] == fake_workflows

    def test_workflows_list_oserror(self, monkeypatch):
        monkeypatch.setattr(
            "core.workflow.WorkflowEngine.list_workflows",
            lambda wf_dir: (_ for _ in ()).throw(OSError("no dir")),
            raising=False,
        )
        server = _make_server()
        result = _run(server._handle_workflows_list(authorization=None))
        assert result["workflows"] == []
        assert "error" in result


# ---------------------------------------------------------------------------
# _handle_workflow_run
# ---------------------------------------------------------------------------


class TestHandleWorkflowRun:
    def test_workflow_run_no_engine_500(self):
        from fastapi import HTTPException

        server = _make_server()
        server.engine = None
        req = mod.WorkflowRunRequest(path="/wf/test.json")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_workflow_run(req, authorization=None))
        assert exc_info.value.status_code == 500

    def test_workflow_run_success(self, monkeypatch):
        server = _make_server()
        server.engine = _FakeEngine()

        class _Result:
            success = True
            steps_completed = 4
            steps_total = 4
            error = None
            elapsed_seconds = 1.5

        class FakeWorkflowEngine:
            def __init__(self, executor, script_engine=None):
                pass

            def run_workflow(self, path, variables=None):
                return _Result()

        monkeypatch.setattr("core.workflow.WorkflowEngine", FakeWorkflowEngine, raising=False)
        req = mod.WorkflowRunRequest(path="/wf/test.json", variables={"x": 1})
        result = _run(server._handle_workflow_run(req, authorization=None))
        assert result["success"] is True
        assert result["steps_completed"] == 4
        assert result["elapsed"] == 1.5

    def test_workflow_run_oserror(self, monkeypatch):
        from fastapi import HTTPException

        server = _make_server()
        server.engine = _FakeEngine()

        class FakeWorkflowEngine:
            def __init__(self, executor, script_engine=None):
                pass

            def run_workflow(self, path, variables=None):
                raise OSError("workflow file not found")

        monkeypatch.setattr("core.workflow.WorkflowEngine", FakeWorkflowEngine, raising=False)
        req = mod.WorkflowRunRequest(path="/wf/missing.json")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_workflow_run(req, authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_stop — additional edge case
# ---------------------------------------------------------------------------


class TestHandleStopEdgeCases:
    def test_stop_with_running_engine(self):
        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.running = True
        stopped = {}
        server.engine.stop = lambda: stopped.update({"stopped": True})
        result = _run(server._handle_stop(authorization=None))
        assert result["status"] == "stopping"
        assert stopped.get("stopped") is True

    def test_stop_no_engine(self):
        server = _make_server()
        server.engine = None
        result = _run(server._handle_stop(authorization=None))
        assert result["status"] == "not_running"


# ---------------------------------------------------------------------------
# Workflow Builder handlers
# ---------------------------------------------------------------------------


class TestWorkflowBuilderList:
    def test_list_empty(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        # Clear any existing workflows for this test
        for wf in server._workflow_store.list_all():
            server._workflow_store.delete(wf.id)
        result = _run(server._handle_workflow_builder_list(authorization=None))
        assert result["workflows"] == []

    def test_list_returns_dicts(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        # Clear any existing workflows for this test
        for wf in server._workflow_store.list_all():
            server._workflow_store.delete(wf.id)
        # Create a workflow first
        wf = server._workflow_store.create(name="Test WF")
        result = _run(server._handle_workflow_builder_list(authorization=None))
        assert len(result["workflows"]) >= 1
        assert result["workflows"][0]["name"] == "Test WF"
        # Clean up
        server._workflow_store.delete(wf.id)


class TestWorkflowBuilderCreate:
    def test_create_default_name(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        result = _run(server._handle_workflow_builder_create(authorization=None))
        assert result["name"] == "New Workflow"
        assert "id" in result
        # Clean up
        server._workflow_store.delete(result["id"])

    def test_create_custom_name(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        result = _run(
            server._handle_workflow_builder_create(
                name="Custom WF", description="desc", authorization=None
            )
        )
        assert result["name"] == "Custom WF"
        assert result["description"] == "desc"
        # Clean up
        server._workflow_store.delete(result["id"])


class TestWorkflowTemplates:
    def test_templates_returns_dict(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        result = _run(server._handle_workflow_templates(authorization=None))
        assert "templates" in result
        assert isinstance(result["templates"], dict)


class TestWorkflowAddStep:
    def test_add_step_success(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        wf = server._workflow_store.create(name="WF")
        result = _run(
            server._handle_workflow_add_step(
                wf.id, action="click", name="Click button", params={"x": 100}, authorization=None
            )
        )
        assert result["step"]["action"] == "click"
        assert result["workflow"]["id"] == wf.id
        server._workflow_store.delete(wf.id)

    def test_add_step_workflow_not_found(self):
        from fastapi import HTTPException

        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(
                server._handle_workflow_add_step(
                    "nonexistent", action="click", name="X", authorization=None
                )
            )
        assert exc_info.value.status_code == 404


class TestWorkflowRemoveStep:
    def test_remove_step_success(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        wf = server._workflow_store.create(name="WF")
        step = wf.add_step(action="type", name="Type text")
        result = _run(
            server._handle_workflow_remove_step(wf.id, step_id=step.id, authorization=None)
        )
        assert result["removed"] is True
        server._workflow_store.delete(wf.id)

    def test_remove_step_workflow_not_found(self):
        from fastapi import HTTPException

        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(
                server._handle_workflow_remove_step("nonexistent", step_id="s1", authorization=None)
            )
        assert exc_info.value.status_code == 404


class TestWorkflowBuilderDelete:
    def test_delete_existing(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        wf = server._workflow_store.create(name="WF")
        result = _run(server._handle_workflow_builder_delete(wf.id, authorization=None))
        assert result["deleted"] is True

    def test_delete_nonexistent(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        result = _run(server._handle_workflow_builder_delete("nonexistent", authorization=None))
        assert result["deleted"] is False


class TestWorkflowDuplicate:
    def test_duplicate_success(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        wf = server._workflow_store.create(name="Original")
        result = _run(server._handle_workflow_duplicate(wf.id, authorization=None))
        assert result["name"] == "Original (Copy)"
        # Clean up
        server._workflow_store.delete(wf.id)
        server._workflow_store.delete(result["id"])

    def test_duplicate_custom_name(self):
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        wf = server._workflow_store.create(name="Original")
        result = _run(
            server._handle_workflow_duplicate(wf.id, new_name="Custom Copy", authorization=None)
        )
        assert result["name"] == "Custom Copy"
        server._workflow_store.delete(wf.id)
        server._workflow_store.delete(result["id"])

    def test_duplicate_not_found(self):
        from fastapi import HTTPException

        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_workflow_duplicate("nonexistent", authorization=None))
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Recorder start/stop — no-engine error paths
# ---------------------------------------------------------------------------


class TestRecorderStartNoEngine:
    def test_recorder_start_no_engine_500(self):
        from fastapi import HTTPException

        server = _make_server()
        server.engine = None
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_recorder_start(authorization=None))
        assert exc_info.value.status_code == 500


class TestRecorderStopNoEngine:
    def test_recorder_stop_no_engine_500(self):
        from fastapi import HTTPException

        server = _make_server()
        server.engine = None
        req = mod.RecorderStopRequest(name="test")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_recorder_stop(req, authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_get_config — additional edge case
# ---------------------------------------------------------------------------


class TestHandleGetConfigEdgeCases:
    def test_no_api_key_returns_as_is(self):
        server = _make_server()
        server.config.load = lambda: {"model": "gpt-4o", "provider": "openai"}
        result = _run(server._handle_get_config(authorization=None))
        assert result["model"] == "gpt-4o"
        assert "api_key" not in result

    def test_api_key_masked(self):
        server = _make_server()
        server.config.load = lambda: {"api_key": "sk-super-secret-key-12345", "model": "gpt-4o"}
        result = _run(server._handle_get_config(authorization=None))
        assert result["api_key"] == "***"
        assert result["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# _handle_put_config — save failure
# ---------------------------------------------------------------------------


class TestHandlePutConfigErrors:
    def test_save_failure_500(self):
        from fastapi import HTTPException

        server = _make_server()
        server.config.load = lambda: {"model": "gpt-4o"}
        server.config.save = lambda cfg: (_ for _ in ()).throw(OSError("disk full"))
        req = mod.ConfigUpdate(model="claude-3.5-sonnet")
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_put_config(req, authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_command — additional error paths
# ---------------------------------------------------------------------------


class TestHandleCommandErrors:
    def test_value_error_from_executor(self, monkeypatch):
        from fastapi import HTTPException

        fake_executor = type(
            "E", (), {"execute_sync": lambda s, p: (_ for _ in ()).throw(ValueError("bad"))}
        )()

        class FakeAE:
            def __init__(self, cfg):
                self.executor = fake_executor

        monkeypatch.setattr(mod, "AgentEngine", FakeAE)
        server = _make_server()
        req = mod.CommandRequest(command='{"action": "bad_action"}')
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_command(req, authorization=None))
        assert exc_info.value.status_code == 400

    def test_os_error_from_executor(self, monkeypatch):
        from fastapi import HTTPException

        fake_executor = type(
            "E", (), {"execute_sync": lambda s, p: (_ for _ in ()).throw(OSError("fail"))}
        )()

        class FakeAE:
            def __init__(self, cfg):
                self.executor = fake_executor

        monkeypatch.setattr(mod, "AgentEngine", FakeAE)
        server = _make_server()
        req = mod.CommandRequest(command='{"action": "click", "x": 1}')
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_command(req, authorization=None))
        assert exc_info.value.status_code == 500

    def test_runtime_error_from_executor(self, monkeypatch):
        from fastapi import HTTPException

        fake_executor = type(
            "E", (), {"execute_sync": lambda s, p: (_ for _ in ()).throw(RuntimeError("crash"))}
        )()

        class FakeAE:
            def __init__(self, cfg):
                self.executor = fake_executor

        monkeypatch.setattr(mod, "AgentEngine", FakeAE)
        server = _make_server()
        req = mod.CommandRequest(command='{"action": "click", "x": 1}')
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_command(req, authorization=None))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# _handle_goal — max_steps and approval_mode passthrough
# ---------------------------------------------------------------------------


class TestHandleGoalConfigPassthrough:
    def test_goal_with_max_steps_and_approval(self, monkeypatch):
        server = _make_server()
        server.engine = _FakeEngine()
        server.engine.running = False
        captured_cfg = {}

        class FakeEngine:
            running = False
            step = 0
            max_steps = 50
            notes: list = []
            forensic_log: list = []
            on_step_callback = None

            def __init__(self, cfg=None):
                captured_cfg.update(cfg or {})

            def run(self, goal):
                return {"steps": 1, "finish_summary": "done"}

        monkeypatch.setattr(mod, "AgentEngine", FakeEngine)
        server.config.load = lambda: {"max_steps": 10}
        req = mod.GoalRequest(goal="test", max_steps=20, approval_mode=True)
        result = _run(server._handle_goal(req, authorization=None))
        assert result["status"] == "started"
        assert captured_cfg["max_steps"] == 20
        assert captured_cfg["approval_mode"] is True


# ---------------------------------------------------------------------------
# Timeout tests - 100% coverage
# ---------------------------------------------------------------------------


class TestHandleCommandTimeout:
    def test_command_timeout(self, monkeypatch):
        """Test command execution timeout raises 504."""
        from fastapi import HTTPException

        def fake_to_thread(func, *args):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        fake_executor = type("E", (), {"execute_sync": lambda s, p: {"status": "ok"}})()

        class FakeAE:
            def __init__(self, cfg):
                self.executor = fake_executor

        monkeypatch.setattr(mod, "AgentEngine", FakeAE)
        server = _make_server()
        req = mod.CommandRequest(command='{"action": "click", "x": 1}')
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_command(req, authorization=None))
        assert exc_info.value.status_code == 504
        assert "timed out after" in str(exc_info.value.detail)


class TestHandleScreenshotTimeout:
    def test_screenshot_timeout(self, monkeypatch):
        """Test screenshot capture timeout raises 504."""
        from fastapi import HTTPException

        def fake_to_thread(func, *args):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(mod, "capture_to_base64", lambda: "base64data")
        server = _make_server()
        _ = server.create_app()  # Initialize workflow store
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_screenshot(authorization=None))
        assert exc_info.value.status_code == 504
        assert "Screenshot capture timed out after" in str(exc_info.value.detail)


class TestHandleScriptRunTimeout:
    def test_script_run_timeout(self, monkeypatch):
        """Test script execution timeout raises 504."""
        from fastapi import HTTPException

        def fake_to_thread(func, *args):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        fake_engine = type(
            "E",
            (),
            {
                "run_script": lambda s, p, v: {"status": "ok"},
                "executor": type("Ex", (), {"execute_sync": lambda s, p: {}})(),
            },
        )()

        server = _make_server()
        server.engine = fake_engine
        req = mod.ScriptRunRequest(path="test.json", params={})
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_script_run(req, authorization=None))
        assert exc_info.value.status_code == 504
        assert "Script execution timed out after" in str(exc_info.value.detail)


class TestHandlePowerShellTimeout:
    def test_powershell_timeout(self, monkeypatch):
        """Test PowerShell execution timeout returns error dict."""

        def fake_to_thread(func, *args):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        fake_ps = type(
            "PS", (), {"run_command": lambda s, c: type("R", (), {"exit_code": 0, "objects": []})()}
        )()

        fake_engine = type("E", (), {"powershell": fake_ps})()

        server = _make_server()
        server.engine = fake_engine
        req = mod.PowerShellRequest(command="Get-Process")
        result = _run(server._handle_powershell(req, authorization=None))
        assert result["success"] is False
        assert "PowerShell execution timed out after" in result["error"]


class TestHandleWorkflowRunTimeout:
    def test_workflow_run_timeout(self, monkeypatch):
        """Test workflow execution timeout raises 504."""
        from fastapi import HTTPException

        def fake_to_thread(func, *args):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        fake_wf = type("WF", (), {"run_workflow": lambda s, p, v: {"status": "ok"}})()

        fake_engine = type(
            "E",
            (),
            {
                "executor": type("Ex", (), {"execute_sync": lambda s, p: {}})(),
                "script_engine": type("SE", (), {})(),
            },
        )()

        server = _make_server()
        server.engine = fake_engine
        server.workflow = fake_wf
        req = mod.WorkflowRunRequest(path="test.json", variables={})
        with pytest.raises(HTTPException) as exc_info:
            _run(server._handle_workflow_run(req, authorization=None))
        assert exc_info.value.status_code == 504
        assert "Workflow execution timed out after" in str(exc_info.value.detail)
