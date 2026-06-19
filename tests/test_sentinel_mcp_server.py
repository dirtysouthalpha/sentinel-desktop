"""Tests for sentinel_mcp_server.py — HTTP helpers, _err, and all MCP tool functions."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Stub fastmcp before loading the module (not installed in test venv)
# ---------------------------------------------------------------------------


def _make_fastmcp_stub() -> MagicMock:
    """Create a minimal fastmcp stub that makes @mcp.tool() a passthrough."""
    stub = MagicMock()
    instance = MagicMock()
    stub.FastMCP.return_value = instance

    def _passthrough(*args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    instance.tool = _passthrough
    return stub


if "fastmcp" not in sys.modules:
    sys.modules["fastmcp"] = _make_fastmcp_stub()


# ---------------------------------------------------------------------------
# Module loading (load by path so tests can run without installing the package)
# ---------------------------------------------------------------------------


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "sentinel_mcp_server",
        os.path.join(os.path.dirname(__file__), "..", "sentinel_mcp_server.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------


def _ok(data: Any = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data if data is not None else {"ok": True}
    resp.text = json.dumps(data if data is not None else {"ok": True})
    resp.raise_for_status.return_value = None
    return resp


def _err_resp(status_code: int, body: str = "bad") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body
    resp.json.side_effect = Exception("not json")
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"HTTP {status_code}", request=MagicMock(), response=resp
    )
    return resp


def _client_ctx(resp: MagicMock):
    """Return a mock httpx.Client context-manager yielding resp on all methods."""
    client = MagicMock()
    client.get.return_value = resp
    client.post.return_value = resp
    client.put.return_value = resp
    client.delete.return_value = resp
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    return cm, client


# ---------------------------------------------------------------------------
# _headers
# ---------------------------------------------------------------------------


class TestHeaders:
    def test_no_token_excludes_authorization(self):
        with patch.object(_mod, "API_TOKEN", ""):
            h = _mod._headers()
        assert "Content-Type" in h
        assert "Authorization" not in h

    def test_with_token_includes_bearer(self):
        with patch.object(_mod, "API_TOKEN", "s3cr3t"):
            h = _mod._headers()
        assert h["Authorization"] == "Bearer s3cr3t"


# ---------------------------------------------------------------------------
# _err
# ---------------------------------------------------------------------------


class TestErr:
    def test_generic_exception(self):
        assert _mod._err(ValueError("boom")) == "boom"

    def test_http_error_with_json_detail(self):
        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {"detail": "not found"}
        resp.text = '{"detail": "not found"}'
        e = httpx.HTTPStatusError("HTTP 404", request=MagicMock(), response=resp)
        assert _mod._err(e) == "HTTP 404: not found"

    def test_http_error_falls_back_to_text(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.json.side_effect = Exception("no json")
        resp.text = "Internal error"
        e = httpx.HTTPStatusError("HTTP 500", request=MagicMock(), response=resp)
        assert _mod._err(e) == "HTTP 500: Internal error"

    def test_http_error_text_truncated_at_200(self):
        resp = MagicMock()
        resp.status_code = 503
        resp.json.side_effect = Exception("no json")
        resp.text = "x" * 300
        e = httpx.HTTPStatusError("HTTP 503", request=MagicMock(), response=resp)
        result = _mod._err(e)
        assert "HTTP 503" in result
        assert len(result) < 300


# ---------------------------------------------------------------------------
# _api_get / _api_post / _api_put / _api_delete
# ---------------------------------------------------------------------------


class TestApiHelpers:
    def test_get_success_returns_json(self):
        cm, client = _client_ctx(_ok({"running": False}))
        with patch("httpx.Client", return_value=cm):
            assert _mod._api_get("/status") == {"running": False}
        client.get.assert_called_once()

    def test_get_passes_params(self):
        cm, client = _client_ctx(_ok([]))
        with patch("httpx.Client", return_value=cm):
            _mod._api_get("/jobs", params={"status": "pending"})
        _, kw = client.get.call_args
        assert kw["params"] == {"status": "pending"}

    def test_get_raises_on_http_error(self):
        cm, _ = _client_ctx(_err_resp(404))
        with patch("httpx.Client", return_value=cm), pytest.raises(httpx.HTTPStatusError):
            _mod._api_get("/missing")

    def test_post_success(self):
        cm, client = _client_ctx(_ok({"id": "abc"}))
        with patch("httpx.Client", return_value=cm):
            assert _mod._api_post("/goal", {"goal": "x"}) == {"id": "abc"}
        client.post.assert_called_once()

    def test_post_empty_body_defaults_to_empty_dict(self):
        cm, client = _client_ctx(_ok())
        with patch("httpx.Client", return_value=cm):
            _mod._api_post("/stop")
        _, kw = client.post.call_args
        assert kw["json"] == {}

    def test_put_success(self):
        cm, client = _client_ctx(_ok({"updated": True}))
        with patch("httpx.Client", return_value=cm):
            assert _mod._api_put("/config", {"model": "gpt-4"}) == {"updated": True}
        client.put.assert_called_once()

    def test_delete_success(self):
        cm, client = _client_ctx(_ok({"deleted": True}))
        with patch("httpx.Client", return_value=cm):
            assert _mod._api_delete("/fleet/nodes/n1") == {"deleted": True}
        client.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


class TestGoal:
    def test_happy(self):
        with patch.object(_mod, "_api_post", return_value={"started": True}):
            assert json.loads(_mod.goal("click")) == {"started": True}

    def test_optional_params_included_when_given(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.goal("x", max_steps=5, approval_mode=True)
        body = m.call_args[0][1]
        assert body["max_steps"] == 5 and body["approval_mode"] is True

    def test_optional_params_omitted_when_none(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.goal("x")
        body = m.call_args[0][1]
        assert "max_steps" not in body and "approval_mode" not in body

    def test_error_returns_error_string(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("timeout")):
            assert _mod.goal("x").startswith("Error:")


class TestCommand:
    def test_happy(self):
        with patch.object(_mod, "_api_post", return_value={"done": True}):
            assert json.loads(_mod.command('{"action":"click"}')) == {"done": True}

    def test_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.command("{}").startswith("Error:")


class TestStop:
    def test_happy(self):
        with patch.object(_mod, "_api_post", return_value={"stopped": True}):
            assert json.loads(_mod.stop())["stopped"] is True

    def test_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.stop().startswith("Error:")


class TestStatus:
    def test_happy(self):
        with patch.object(_mod, "_api_get", return_value={"running": False}):
            assert json.loads(_mod.status()) == {"running": False}

    def test_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.status().startswith("Error:")


class TestScreenshot:
    def test_happy(self):
        with patch.object(_mod, "_api_get", return_value={"image": "b64"}):
            assert json.loads(_mod.screenshot())["image"] == "b64"

    def test_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.screenshot().startswith("Error:")


class TestWindows:
    def test_happy(self):
        with patch.object(_mod, "_api_get", return_value=[{"title": "Notepad"}]):
            assert json.loads(_mod.windows()) == [{"title": "Notepad"}]

    def test_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.windows().startswith("Error:")


class TestProcesses:
    def test_happy(self):
        with patch.object(_mod, "_api_get", return_value=[]):
            assert json.loads(_mod.processes()) == []

    def test_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.processes().startswith("Error:")


class TestSystemInfo:
    def test_happy(self):
        with patch.object(_mod, "_api_get", return_value={"os": "Windows"}):
            assert json.loads(_mod.system_info())["os"] == "Windows"

    def test_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.system_info().startswith("Error:")


class TestConfig:
    def test_get_happy(self):
        with patch.object(_mod, "_api_get", return_value={"provider": "openai"}):
            assert json.loads(_mod.get_config())["provider"] == "openai"

    def test_get_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.get_config().startswith("Error:")

    def test_set_all_fields(self):
        with patch.object(_mod, "_api_put") as m:
            m.return_value = {"ok": True}
            _mod.set_config(
                provider="anthropic",
                model="claude-3",
                max_steps=10,
                approval_mode=True,
                theme="dark",
            )
        body = m.call_args[0][1]
        assert body == {
            "provider": "anthropic",
            "model": "claude-3",
            "max_steps": 10,
            "approval_mode": True,
            "theme": "dark",
        }

    def test_set_no_fields_sends_empty_body(self):
        with patch.object(_mod, "_api_put") as m:
            m.return_value = {}
            _mod.set_config()
        assert m.call_args[0][1] == {}

    def test_set_error(self):
        with patch.object(_mod, "_api_put", side_effect=Exception("x")):
            assert _mod.set_config(provider="x").startswith("Error:")


class TestLog:
    def test_happy(self):
        with patch.object(_mod, "_api_get", return_value=[{"action": "click"}]):
            assert json.loads(_mod.log()) == [{"action": "click"}]

    def test_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.log().startswith("Error:")


class TestScripts:
    def test_list_happy(self):
        with patch.object(_mod, "_api_get", return_value=[{"name": "cleanup"}]):
            assert json.loads(_mod.list_scripts()) == [{"name": "cleanup"}]

    def test_list_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.list_scripts().startswith("Error:")

    def test_run_happy(self):
        with patch.object(_mod, "_api_post", return_value={"ran": True}):
            assert json.loads(_mod.run_script("cleanup.json"))["ran"] is True

    def test_run_passes_params(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.run_script("s.json", params={"key": "val"})
        assert m.call_args[0][1]["params"] == {"key": "val"}

    def test_run_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.run_script("x.json").startswith("Error:")


class TestPowershell:
    def test_happy(self):
        with patch.object(_mod, "_api_post", return_value={"stdout": "ok"}):
            assert json.loads(_mod.powershell("Get-Process"))["stdout"] == "ok"

    def test_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.powershell("x").startswith("Error:")


class TestWorkflows:
    def test_list_happy(self):
        with patch.object(_mod, "_api_get", return_value=[]):
            assert json.loads(_mod.list_workflows()) == []

    def test_list_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.list_workflows().startswith("Error:")

    def test_run_happy(self):
        with patch.object(_mod, "_api_post", return_value={"ran": True}):
            assert json.loads(_mod.run_workflow("wf.json"))["ran"] is True

    def test_run_passes_variables(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.run_workflow("wf.json", variables={"x": 1})
        assert m.call_args[0][1]["variables"] == {"x": 1}

    def test_run_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.run_workflow("x").startswith("Error:")

    def test_templates_happy(self):
        with patch.object(_mod, "_api_get", return_value={"templates": []}):
            assert "templates" in json.loads(_mod.list_workflow_templates())

    def test_templates_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.list_workflow_templates().startswith("Error:")


class TestScheduler:
    def test_list_happy(self):
        with patch.object(_mod, "_api_get", return_value=[]):
            assert json.loads(_mod.list_scheduled_tasks()) == []

    def test_list_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.list_scheduled_tasks().startswith("Error:")

    def test_add_with_cron_no_delay(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {"id": "t1"}
            _mod.add_scheduled_task("daily", "do thing", cron="0 9 * * *")
        body = m.call_args[0][1]
        assert body["cron"] == "0 9 * * *"
        assert "delay_seconds" not in body

    def test_add_with_delay_no_cron(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.add_scheduled_task("once", "do thing", delay_seconds=60.0)
        body = m.call_args[0][1]
        assert body["delay_seconds"] == 60.0
        assert "cron" not in body

    def test_add_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.add_scheduled_task("x", "y").startswith("Error:")

    def test_remove_happy(self):
        with patch.object(_mod, "_api_post", return_value={"removed": True}):
            assert json.loads(_mod.remove_scheduled_task("t1"))["removed"] is True

    def test_remove_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.remove_scheduled_task("t").startswith("Error:")

    def test_run_task_happy(self):
        with patch.object(_mod, "_api_post", return_value={"started": True}):
            assert json.loads(_mod.run_scheduled_task("t1"))["started"] is True

    def test_run_task_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.run_scheduled_task("t").startswith("Error:")


class TestAgentPool:
    def test_list_happy(self):
        with patch.object(_mod, "_api_get", return_value=[]):
            assert json.loads(_mod.list_agents()) == []

    def test_list_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.list_agents().startswith("Error:")

    def test_submit_happy(self):
        with patch.object(_mod, "_api_post", return_value={"session_id": "s1"}):
            assert json.loads(_mod.submit_agent("task"))["session_id"] == "s1"

    def test_submit_with_config(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.submit_agent("x", config={"provider": "openai"}, priority="high")
        body = m.call_args[0][1]
        assert body["config"] == {"provider": "openai"} and body["priority"] == "high"

    def test_submit_no_config_omitted(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.submit_agent("x")
        assert "config" not in m.call_args[0][1]

    def test_submit_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.submit_agent("x").startswith("Error:")

    def test_cancel_happy(self):
        with patch.object(_mod, "_api_post", return_value={"cancelled": True}):
            assert json.loads(_mod.cancel_agent("s1"))["cancelled"] is True

    def test_cancel_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.cancel_agent("s").startswith("Error:")

    def test_agent_status_happy(self):
        with patch.object(_mod, "_api_get", return_value={"state": "running"}):
            assert json.loads(_mod.agent_status("s1"))["state"] == "running"

    def test_agent_status_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.agent_status("s").startswith("Error:")


class TestDaemon:
    def test_status_happy(self):
        with patch.object(_mod, "_api_get", return_value={"running": True}):
            assert json.loads(_mod.daemon_status())["running"] is True

    def test_status_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.daemon_status().startswith("Error:")

    def test_start_happy(self):
        with patch.object(_mod, "_api_post", return_value={"started": True}):
            assert json.loads(_mod.daemon_start())["started"] is True

    def test_start_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.daemon_start().startswith("Error:")

    def test_stop_happy(self):
        with patch.object(_mod, "_api_post", return_value={"stopped": True}):
            assert json.loads(_mod.daemon_stop())["stopped"] is True

    def test_stop_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.daemon_stop().startswith("Error:")


class TestFleet:
    def test_nodes_happy(self):
        with patch.object(_mod, "_api_get", return_value=[{"node_id": "n1"}]):
            assert json.loads(_mod.fleet_nodes()) == [{"node_id": "n1"}]

    def test_nodes_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.fleet_nodes().startswith("Error:")

    def test_register_minimal_no_tags(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.fleet_register("n1", "host1", "1.2.3.4")
        body = m.call_args[0][1]
        assert body["node_id"] == "n1" and "tags" not in body

    def test_register_with_tags(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.fleet_register("n1", "host1", "1.2.3.4", tags=["win", "gpu"])
        assert m.call_args[0][1]["tags"] == ["win", "gpu"]

    def test_register_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.fleet_register("n", "h", "1.1.1.1").startswith("Error:")

    def test_unregister_happy(self):
        with patch.object(_mod, "_api_post", return_value={"removed": True}):
            assert json.loads(_mod.fleet_unregister("n1"))["removed"] is True

    def test_unregister_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.fleet_unregister("n").startswith("Error:")


class TestJobs:
    def test_list_happy(self):
        with patch.object(_mod, "_api_get", return_value=[]):
            assert json.loads(_mod.list_jobs()) == []

    def test_list_status_param_passed(self):
        with patch.object(_mod, "_api_get") as m:
            m.return_value = []
            _mod.list_jobs(status="pending")
        assert m.call_args[1]["params"]["status"] == "pending"

    def test_list_no_status_no_params_key(self):
        with patch.object(_mod, "_api_get") as m:
            m.return_value = []
            _mod.list_jobs()
        assert m.call_args[1]["params"] == {}

    def test_list_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.list_jobs().startswith("Error:")

    def test_submit_happy(self):
        with patch.object(_mod, "_api_post", return_value={"job_id": "j1"}):
            assert json.loads(_mod.submit_job("task"))["job_id"] == "j1"

    def test_submit_with_node(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.submit_job("x", node_id="n1")
        assert m.call_args[0][1]["node_id"] == "n1"

    def test_submit_no_node_omitted(self):
        with patch.object(_mod, "_api_post") as m:
            m.return_value = {}
            _mod.submit_job("x")
        assert "node_id" not in m.call_args[0][1]

    def test_submit_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.submit_job("x").startswith("Error:")

    def test_job_status_happy(self):
        with patch.object(_mod, "_api_get", return_value={"state": "done"}):
            assert json.loads(_mod.job_status("j1"))["state"] == "done"

    def test_job_status_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.job_status("j").startswith("Error:")

    def test_cancel_happy(self):
        with patch.object(_mod, "_api_post", return_value={"cancelled": True}):
            assert json.loads(_mod.cancel_job("j1"))["cancelled"] is True

    def test_cancel_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.cancel_job("j").startswith("Error:")


class TestRecorder:
    def test_start_happy(self):
        with patch.object(_mod, "_api_post", return_value={"recording": True}):
            assert json.loads(_mod.recorder_start())["recording"] is True

    def test_start_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.recorder_start().startswith("Error:")

    def test_stop_happy(self):
        with patch.object(_mod, "_api_post", return_value={"saved": True}):
            assert json.loads(_mod.recorder_stop("my script", "desc"))["saved"] is True

    def test_stop_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.recorder_stop().startswith("Error:")


class TestNotify:
    def test_happy(self):
        with patch.object(_mod, "_api_post", return_value={"sent": True}):
            assert json.loads(_mod.notify("T", "M", "info"))["sent"] is True

    def test_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.notify().startswith("Error:")


class TestPlugins:
    def test_list_happy(self):
        with patch.object(_mod, "_api_get", return_value=[{"name": "p1"}]):
            assert json.loads(_mod.list_plugins()) == [{"name": "p1"}]

    def test_list_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("x")):
            assert _mod.list_plugins().startswith("Error:")

    def test_reload_happy(self):
        with patch.object(_mod, "_api_post", return_value={"reloaded": True}):
            assert json.loads(_mod.reload_plugin("p1"))["reloaded"] is True

    def test_reload_error(self):
        with patch.object(_mod, "_api_post", side_effect=Exception("x")):
            assert _mod.reload_plugin("p").startswith("Error:")


class TestHealth:
    def test_healthy_agent_running(self):
        with patch.object(_mod, "_api_get", return_value={"running": True}):
            data = json.loads(_mod.health())
        assert data["healthy"] is True and data["agent_running"] is True

    def test_healthy_agent_not_running(self):
        with patch.object(_mod, "_api_get", return_value={"running": False}):
            data = json.loads(_mod.health())
        assert data["healthy"] is True and data["agent_running"] is False

    def test_unhealthy_returns_error(self):
        with patch.object(_mod, "_api_get", side_effect=Exception("refused")):
            data = json.loads(_mod.health())
        assert data["healthy"] is False and "error" in data


class TestAgentZero:
    def _patch_client(self, resp: MagicMock):
        cm, client = _client_ctx(resp)
        return patch("httpx.Client", return_value=cm), client

    def test_run_happy_returns_text(self):
        resp = _ok()
        resp.text = "Task done"
        p, _ = self._patch_client(resp)
        with p:
            assert _mod.agent_zero_run("list files") == "Task done"

    def test_run_error_returns_error_string(self):
        cm = MagicMock()
        inner = MagicMock()
        inner.post.side_effect = Exception("unreachable")
        cm.__enter__.return_value = inner
        cm.__exit__.return_value = False
        with patch("httpx.Client", return_value=cm):
            assert _mod.agent_zero_run("x").startswith("Error:")

    def test_health_reachable_200(self):
        resp = MagicMock()
        resp.status_code = 200
        p, _ = self._patch_client(resp)
        with p:
            data = json.loads(_mod.agent_zero_health())
        assert data["reachable"] is True

    def test_health_reachable_404_still_reachable(self):
        resp = MagicMock()
        resp.status_code = 404
        p, _ = self._patch_client(resp)
        with p:
            data = json.loads(_mod.agent_zero_health())
        assert data["reachable"] is True

    def test_health_reachable_500_not_reachable(self):
        resp = MagicMock()
        resp.status_code = 500
        p, _ = self._patch_client(resp)
        with p:
            data = json.loads(_mod.agent_zero_health())
        assert data["reachable"] is False

    def test_health_exception_not_reachable(self):
        cm = MagicMock()
        cm.__enter__.side_effect = Exception("refused")
        with patch("httpx.Client", return_value=cm):
            data = json.loads(_mod.agent_zero_health())
        assert data["reachable"] is False and "error" in data


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


class TestMain:
    def test_stdio_transport_is_default(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("SENTINEL_MCP_TRANSPORT", None)
            with patch.object(_mod.mcp, "run") as mock_run:
                _mod.main()
        mock_run.assert_called_once_with(transport="stdio")

    def test_explicit_stdio_transport(self):
        with patch.dict("os.environ", {"SENTINEL_MCP_TRANSPORT": "stdio"}):
            with patch.object(_mod.mcp, "run") as mock_run:
                _mod.main()
        mock_run.assert_called_once_with(transport="stdio")

    def test_http_transport_uses_host_and_port(self):
        env = {
            "SENTINEL_MCP_TRANSPORT": "http",
            "SENTINEL_MCP_HOST": "10.0.0.1",
            "SENTINEL_MCP_PORT": "9999",
        }
        with patch.dict("os.environ", env):
            with patch.object(_mod.mcp, "run") as mock_run:
                _mod.main()
        mock_run.assert_called_once_with(transport="http", host="10.0.0.1", port=9999)

    def test_sse_transport_accepted(self):
        with patch.dict("os.environ", {"SENTINEL_MCP_TRANSPORT": "sse"}):
            with patch.object(_mod.mcp, "run") as mock_run:
                _mod.main()
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs.get("transport") == "http"

    def test_http_transport_with_auth_token(self):
        env = {
            "SENTINEL_MCP_TRANSPORT": "http",
            "SENTINEL_MCP_HOST": "127.0.0.1",
            "SENTINEL_MCP_PORT": "9192",
            "MCP_AUTH_TOKEN": "secret-tok",
        }
        fake_verifier_cls = MagicMock()
        fake_verifier = MagicMock()
        fake_verifier_cls.return_value = fake_verifier

        with patch.dict("os.environ", env):
            with patch.dict(
                "sys.modules",
                {
                    "fastmcp.server.auth.providers.jwt": MagicMock(
                        StaticTokenVerifier=fake_verifier_cls
                    )
                },
            ):
                with patch.object(_mod.mcp, "run"):
                    _mod.main()

        fake_verifier_cls.assert_called_once()
        call_kwargs = fake_verifier_cls.call_args
        tokens_arg = call_kwargs.kwargs.get("tokens") or call_kwargs.args[0]
        assert "secret-tok" in tokens_arg

    def test_http_transport_no_auth_token_skips_verifier(self):
        env = {
            "SENTINEL_MCP_TRANSPORT": "http",
            "SENTINEL_MCP_HOST": "127.0.0.1",
            "SENTINEL_MCP_PORT": "9192",
        }
        with patch.dict("os.environ", env):
            os.environ.pop("MCP_AUTH_TOKEN", None)
            with patch.object(_mod.mcp, "run") as mock_run:
                _mod.main()
        mock_run.assert_called_once_with(transport="http", host="127.0.0.1", port=9192)
