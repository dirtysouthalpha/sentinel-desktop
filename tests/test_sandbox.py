"""
Tests for the v27.0.0 Plugin Sandbox module.
"""
from core.sandbox import (
    SandboxResult,
    SandboxedPlugin,
    validate_permissions,
    execute_plugin,
    list_active,
    kill_plugin,
    VALID_PERMISSIONS,
)


class TestValidatePermissions:
    def test_valid_permissions(self):
        result = validate_permissions(["clipboard", "network"])
        assert "clipboard" in result
        assert "network" in result

    def test_invalid_permissions_filtered(self):
        result = validate_permissions(["clipboard", "hack_everything"])
        assert "clipboard" in result
        assert "hack_everything" not in result

    def test_empty_list(self):
        assert validate_permissions([]) == []

    def test_all_valid_permissions(self):
        result = validate_permissions(list(VALID_PERMISSIONS))
        assert len(result) == len(VALID_PERMISSIONS)


class TestExecutePlugin:
    def test_simple_plugin(self, tmp_path):
        plugin = tmp_path / "test_plugin.py"
        plugin.write_text("def run(args):\n    return 'hello from plugin'")
        result = execute_plugin(plugin, timeout=10)
        assert result.success
        assert "hello" in result.output

    def test_nonexistent_plugin(self, tmp_path):
        result = execute_plugin(tmp_path / "nonexistent.py")
        assert not result.success
        assert "not found" in result.error

    def test_plugin_timeout(self, tmp_path):
        plugin = tmp_path / "slow_plugin.py"
        plugin.write_text("import time\ndef run(args):\n    time.sleep(10)\n    return 'done'")
        result = execute_plugin(plugin, timeout=2)
        assert not result.success
        assert result.timed_out

    def test_plugin_exception(self, tmp_path):
        plugin = tmp_path / "crash_plugin.py"
        plugin.write_text("def run(args):\n    raise ValueError('crash!')")
        result = execute_plugin(plugin, timeout=10)
        assert not result.success
        assert "crash" in result.error


class TestListActive:
    def test_empty_list(self):
        result = list_active()
        assert isinstance(result, list)


class TestKillPlugin:
    def test_kill_nonexistent(self):
        result = kill_plugin("does_not_exist")
        assert result["success"] is False


class TestSandboxResult:
    def test_dataclass(self):
        r = SandboxResult(success=True, output="ok")
        assert r.success
        assert r.output == "ok"
        assert r.timed_out is False

    def test_sandboxed_plugin_dataclass(self):
        sp = SandboxedPlugin(name="test")
        assert sp.name == "test"
        assert sp.pid == 0
        assert sp.is_running is False
