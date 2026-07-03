import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import src.commands.automation as auto_mod
from src.commands.automation import AutomationCommands


class TestAutomationCommands:
    def setup_method(self):
        self.cmds = AutomationCommands()
        # Create a mock pyautogui
        self.mock_pag = MagicMock()
        self.mock_pag.position.return_value = MagicMock(x=100, y=200)

    def test_screenshot_without_pyautogui(self):
        with patch.object(self.cmds, "available", False):
            result = self.cmds.screenshot()
            assert result.success is False
            assert "pyautogui" in result.message

    def test_execute_unavailable(self):
        with patch.object(self.cmds, "available", False):
            result = self.cmds.execute("click 100,200")
            assert result.success is False

    def test_click_with_coords(self):
        self.cmds.available = True
        with patch.object(auto_mod, "pyautogui", self.mock_pag):
            result = self.cmds.execute("click 500,300")
            assert result.success is True
            self.mock_pag.click.assert_called_once_with(500, 300)

    def test_right_click(self):
        self.cmds.available = True
        with patch.object(auto_mod, "pyautogui", self.mock_pag):
            result = self.cmds.execute("click right 500,300")
            assert result.success is True
            self.mock_pag.rightClick.assert_called_once_with(500, 300)

    def test_type_text(self):
        self.cmds.available = True
        with patch.object(auto_mod, "pyautogui", self.mock_pag):
            result = self.cmds.execute("type hello world")
            assert result.success is True
            self.mock_pag.typewrite.assert_called_once_with("hello world", interval=0.02)

    def test_press_key_combo(self):
        self.cmds.available = True
        with patch.object(auto_mod, "pyautogui", self.mock_pag):
            result = self.cmds.execute("press ctrl+c")
            assert result.success is True
            self.mock_pag.hotkey.assert_called_once_with("ctrl", "c")

    def test_move_mouse(self):
        self.cmds.available = True
        with patch.object(auto_mod, "pyautogui", self.mock_pag):
            result = self.cmds.execute("move 100,200")
            assert result.success is True
            self.mock_pag.moveTo.assert_called_once()

    def test_scroll(self):
        self.cmds.available = True
        with patch.object(auto_mod, "pyautogui", self.mock_pag):
            result = self.cmds.execute("scroll 5")
            assert result.success is True
            self.mock_pag.scroll.assert_called_once_with(5)
