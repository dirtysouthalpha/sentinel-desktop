"""Tests for the fleet dashboard tab."""
from unittest.mock import MagicMock


class TestFleetTab:
    def test_construct(self):
        """FleetTab can be constructed with mock app."""
        from gui.tabs.fleet_tab import FleetTab

        mock_app = MagicMock()
        mock_app._t = MagicMock()
        mock_app.root = MagicMock()
        mock_app.root.after.return_value = "poll_id"

        parent = MagicMock()
        tab = FleetTab(parent, mock_app)
        assert tab.app is mock_app
        assert tab._poll_interval == 2000

    def test_refresh_no_data(self):
        """Refresh handles missing fleet data gracefully."""
        from gui.tabs.fleet_tab import FleetTab

        mock_app = MagicMock()
        mock_app._t = MagicMock()
        mock_app.root = MagicMock()
        mock_app.root.after.return_value = "poll_id"
        mock_app._fleet_data = None

        parent = MagicMock()
        tab = FleetTab(parent, mock_app)
        tab._refresh()  # Should not raise

    def test_add_event(self):
        """Add event calls root.after."""
        from gui.tabs.fleet_tab import FleetTab

        mock_app = MagicMock()
        mock_app._t = MagicMock()
        mock_app.root = MagicMock()
        mock_app.root.after.return_value = "poll_id"

        parent = MagicMock()
        tab = FleetTab(parent, mock_app)
        tab.add_event("test event")
        mock_app.root.after.assert_called()

    def test_destroy_cancels_poll(self):
        """Destroy cancels pending poll."""
        from gui.tabs.fleet_tab import FleetTab

        mock_app = MagicMock()
        mock_app._t = MagicMock()
        mock_app.root = MagicMock()
        mock_app.root.after.return_value = "poll_id"

        parent = MagicMock()
        tab = FleetTab(parent, mock_app)
        tab.destroy()
        mock_app.root.after_cancel.assert_called_once_with("poll_id")
