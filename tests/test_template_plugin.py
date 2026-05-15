"""Tests for plugins/template.py register function."""

from unittest.mock import MagicMock

from plugins.template import PLUGIN_DESCRIPTION, PLUGIN_NAME, PLUGIN_VERSION, register


class TestTemplatePluginMetadata:
    def test_name(self):
        assert PLUGIN_NAME == "Template Plugin"

    def test_version(self):
        assert PLUGIN_VERSION == "1.0.0"

    def test_description(self):
        assert isinstance(PLUGIN_DESCRIPTION, str)
        assert len(PLUGIN_DESCRIPTION) > 0


class TestRegister:
    def test_registers_action(self):
        api = MagicMock()
        register(api)
        api.register_action.assert_called_once()
        call_kwargs = api.register_action.call_args
        assert call_kwargs.kwargs["name"] == "template_test"

    def test_registers_setting(self):
        api = MagicMock()
        register(api)
        api.register_setting.assert_called_once()
        call_kwargs = api.register_setting.call_args
        assert call_kwargs.kwargs["key"] == "example_flag"

    def test_logs_messages(self):
        api = MagicMock()
        register(api)
        assert api.log.call_count >= 2

    def test_action_handler_succeeds(self):
        api = MagicMock()
        register(api)
        handler = api.register_action.call_args.kwargs["handler"]
        result = handler(foo="bar")
        assert result["success"] is True
