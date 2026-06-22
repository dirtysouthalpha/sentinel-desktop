"""Regression: POST /workflows/run must confine paths to the workflows/ dir.

``_handle_workflow_run`` passed ``req.path`` straight to ``run_workflow`` →
``_load_workflow_file`` → ``Path(path).open()`` with no sanitization (unlike
``/scripts/run``, which has ``ScriptRunRequest.validate_path``). An
authenticated caller could supply ``../../etc/passwd`` to read arbitrary
JSON from disk as a workflow.

Fix: ``WorkflowRunRequest.validate_path`` (mirrors ``ScriptRunRequest``)
strips traversal and prefixes ``workflows/``, and the handler calls it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import api.server as mod
from config import Config


def _run(coro):
    return asyncio.run(coro)


class _FakeEngine:
    executor = None
    script_engine = None


def _make_server():
    server = mod.SentinelServer(Config())
    server.engine = _FakeEngine()
    return server


class _WorkflowResult:
    success = True
    steps_completed = 0
    steps_total = 0
    error = None
    elapsed_seconds = 0.0


class TestWorkflowRunPathSanitization:
    def test_validate_path_strips_traversal(self):
        req = mod.WorkflowRunRequest(path="../../etc/passwd")
        safe = req.validate_path()
        assert ".." not in safe
        assert "~" not in safe
        assert safe.startswith("workflows/")

    def test_validate_path_prefixes_bare_name(self):
        req = mod.WorkflowRunRequest(path="patch.yml")
        assert req.validate_path() == "workflows/patch.yml"

    def test_handler_passes_sanitized_path(self, monkeypatch):
        captured = {}

        class _Capture:
            def __init__(self, executor, script_engine=None):
                pass

            def run_workflow(self, path, variables=None):
                captured["path"] = path
                return _WorkflowResult()

        monkeypatch.setattr("core.workflow.WorkflowEngine", _Capture, raising=False)
        server = _make_server()
        req = mod.WorkflowRunRequest(path="../../secret/file.json", variables={})
        result = _run(server._handle_workflow_run(req, authorization=None))
        assert result["success"] is True
        # Traversal is neutralized and the resolved path stays under workflows/.
        captured_path = captured["path"]
        assert captured_path.startswith("workflows/")
        assert ".." not in captured_path
        wf_root = Path.cwd().joinpath("workflows").resolve()
        resolved = Path.cwd().joinpath(captured_path).resolve()
        assert str(resolved) == str(wf_root) or str(resolved).startswith(
            str(wf_root) + "/"
        )
