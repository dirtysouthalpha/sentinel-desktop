import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.legacy_plugins import PLUGIN_DIR, PluginManager


class TestPluginManager:
    def setup_method(self):
        PluginManager._instance = None
        self.pm = PluginManager()

    def test_discover(self):
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        result = self.pm.discover()
        assert isinstance(result, list)

    def test_list_empty(self):
        result = self.pm.list_plugins()
        assert result.success is True

    def test_load_nonexistent(self):
        result = self.pm.load("plugin_nonexistent")
        assert result.success is False

    def test_execute_list(self):
        result = self.pm.execute("list plugins")
        assert result.success is True

    def test_execute_load(self):
        result = self.pm.execute("load plugin test")
        assert result.success is False

    def test_execute_unknown(self):
        result = self.pm.execute("dance")
        assert result.success is False
