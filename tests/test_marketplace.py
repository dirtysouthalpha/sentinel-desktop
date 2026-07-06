"""
Tests for the v26.0.0 Plugin Marketplace module.
"""
from core.marketplace import list_installed, uninstall_plugin, PluginInfo, get_marketplace_listing


class TestMarketplace:
    def test_list_installed_returns_list(self):
        result = list_installed()
        assert isinstance(result, list)

    def test_plugin_info_dataclass(self):
        pi = PluginInfo(name="test-plugin", description="A test", author="me", version="1.0.0")
        assert pi.name == "test-plugin"
        assert pi.installed is False
        assert pi.tags == []

    def test_get_marketplace_listing_returns_list(self):
        listing = get_marketplace_listing()
        assert isinstance(listing, list)
        # Each entry should have required keys
        for entry in listing:
            assert "name" in entry
            assert "installed" in entry

    def test_uninstall_nonexistent_plugin(self):
        result = uninstall_plugin("does_not_exist_xyz")
        assert result["success"] is False
        assert "not installed" in result["message"]

    def test_uninstall_protected_files(self):
        for name in ("__init__", "template"):
            result = uninstall_plugin(name)
            assert result["success"] is False
            assert "built-in" in result["message"]
