"""Tests for AgentEngine lazy property accessors — all 11 subsystems."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.engine import AgentEngine


def _make_engine(**overrides):
    config = {"provider": "openai", "api_key": "k", "model": "gpt-4o"}
    config.update(overrides)
    with patch("core.engine.capture_to_base64"), patch("core.engine.ActionExecutor"):
        return AgentEngine(config=config)


# -------------------------------------------------------------------
# recorder
# -------------------------------------------------------------------


class TestRecorder:
    @patch("core.recorder.ActionRecorder")
    def test_lazy_creation(self, mock_cls):
        eng = _make_engine()
        _ = eng.recorder
        mock_cls.assert_called_once()

    @patch("core.recorder.ActionRecorder")
    def test_cached_after_first_access(self, mock_cls):
        eng = _make_engine()
        r1 = eng.recorder
        r2 = eng.recorder
        assert r1 is r2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# script_engine
# -------------------------------------------------------------------


class TestScriptEngine:
    @patch("core.script_engine.ScriptEngine")
    def test_lazy_creation_with_executor(self, mock_cls):
        eng = _make_engine()
        _ = eng.script_engine
        mock_cls.assert_called_once_with(eng.executor)

    @patch("core.script_engine.ScriptEngine")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        s1 = eng.script_engine
        s2 = eng.script_engine
        assert s1 is s2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# powershell
# -------------------------------------------------------------------


class TestPowerShell:
    @patch("core.powershell.PowerShellRunner")
    def test_lazy_creation(self, mock_cls):
        eng = _make_engine()
        _ = eng.powershell
        mock_cls.assert_called_once()

    @patch("core.powershell.PowerShellRunner")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        p1 = eng.powershell
        p2 = eng.powershell
        assert p1 is p2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# workflow_engine
# -------------------------------------------------------------------


class TestWorkflowEngine:
    @patch("core.workflow.WorkflowEngine")
    def test_lazy_creation(self, mock_cls):
        eng = _make_engine()
        _ = eng.workflow_engine
        mock_cls.assert_called_once()

    @patch("core.workflow.WorkflowEngine")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        w1 = eng.workflow_engine
        w2 = eng.workflow_engine
        assert w1 is w2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# scheduler
# -------------------------------------------------------------------


class TestScheduler:
    @patch("core.scheduler.TaskScheduler")
    def test_lazy_creation(self, mock_cls):
        eng = _make_engine()
        _ = eng.scheduler
        mock_cls.assert_called_once_with(eng)

    @patch("core.scheduler.TaskScheduler")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        s1 = eng.scheduler
        s2 = eng.scheduler
        assert s1 is s2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# notifications
# -------------------------------------------------------------------


class TestNotifications:
    @patch("core.notifications.NotificationManager")
    def test_lazy_creation(self, mock_cls):
        eng = _make_engine()
        _ = eng.notifications
        mock_cls.assert_called_once()

    @patch("core.notifications.NotificationManager")
    def test_config_forwarded(self, mock_cls):
        eng = _make_engine(notify_channels=["toast"], notify_webhook_url="http://hook")
        _ = eng.notifications
        call_kwargs = mock_cls.call_args[0][0]
        assert call_kwargs["enabled_channels"] == ["toast"]
        assert call_kwargs["webhook_url"] == "http://hook"

    @patch("core.notifications.NotificationManager")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        n1 = eng.notifications
        n2 = eng.notifications
        assert n1 is n2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# plugin_loader
# -------------------------------------------------------------------


class TestPluginLoader:
    @patch("core.plugin_loader.PluginLoader")
    def test_lazy_creation(self, mock_cls):
        mock_inst = MagicMock()
        mock_inst.load_all.return_value = []
        mock_cls.return_value = mock_inst
        eng = _make_engine()
        _ = eng.plugin_loader
        mock_cls.assert_called_once()

    @patch("core.plugin_loader.PluginLoader")
    def test_load_all_called(self, mock_cls):
        mock_inst = MagicMock()
        mock_inst.load_all.return_value = []
        mock_cls.return_value = mock_inst
        eng = _make_engine()
        _ = eng.plugin_loader
        mock_inst.load_all.assert_called_once()

    @patch("core.plugin_loader.PluginLoader")
    def test_cached(self, mock_cls):
        mock_inst = MagicMock()
        mock_inst.load_all.return_value = []
        mock_cls.return_value = mock_inst
        eng = _make_engine()
        p1 = eng.plugin_loader
        p2 = eng.plugin_loader
        assert p1 is p2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# auth_manager
# -------------------------------------------------------------------


class TestAuthManager:
    @patch("core.auth.AuthManager")
    def test_lazy_creation(self, mock_cls):
        eng = _make_engine()
        _ = eng.auth_manager
        mock_cls.assert_called_once()

    @patch("core.auth.AuthManager")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        a1 = eng.auth_manager
        a2 = eng.auth_manager
        assert a1 is a2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# vault
# -------------------------------------------------------------------


class TestVault:
    @patch("core.encryption.CredentialVault")
    def test_lazy_creation(self, mock_cls):
        eng = _make_engine()
        _ = eng.vault
        mock_cls.assert_called_once()

    @patch("core.encryption.CredentialVault")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        v1 = eng.vault
        v2 = eng.vault
        assert v1 is v2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# audit_exporter
# -------------------------------------------------------------------


class TestAuditExporter:
    @patch("core.audit_export.AuditExporter")
    def test_lazy_creation(self, mock_cls):
        eng = _make_engine()
        _ = eng.audit_exporter
        mock_cls.assert_called_once()

    @patch("core.audit_export.AuditExporter")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        a1 = eng.audit_exporter
        a2 = eng.audit_exporter
        assert a1 is a2
        assert mock_cls.call_count == 1


# -------------------------------------------------------------------
# agent_pool
# -------------------------------------------------------------------


class TestAgentPool:
    @patch("core.agent_pool.AgentPool")
    def test_lazy_creation_default(self, mock_cls):
        eng = _make_engine()
        _ = eng.agent_pool
        mock_cls.assert_called_once_with(max_agents=3)

    @patch("core.agent_pool.AgentPool")
    def test_config_max_agents(self, mock_cls):
        eng = _make_engine(max_agents=5)
        _ = eng.agent_pool
        mock_cls.assert_called_once_with(max_agents=5)

    @patch("core.agent_pool.AgentPool")
    def test_cached(self, mock_cls):
        eng = _make_engine()
        a1 = eng.agent_pool
        a2 = eng.agent_pool
        assert a1 is a2
        assert mock_cls.call_count == 1
