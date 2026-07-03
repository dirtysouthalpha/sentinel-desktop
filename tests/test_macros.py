import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.commands.macros import MacroCommands, MACRO_DIR


class TestMacroCommands:
    def setup_method(self):
        self.cmds = MacroCommands()

    def test_start_recording(self):
        result = self.cmds.start_recording()
        assert result.success is True
        assert "Recording started" in result.message

    def test_double_start(self):
        self.cmds.start_recording()
        result = self.cmds.start_recording()
        assert result.success is False

    def test_stop_not_recording(self):
        result = self.cmds.stop_recording()
        assert result.success is False

    def test_record_and_stop(self):
        self.cmds.start_recording()
        self.cmds.record_action("click 100 100")
        self.cmds.record_action("type hello")
        result = self.cmds.stop_recording()
        assert result.success is True
        assert "2 actions" in result.message

    def test_save_macro(self):
        self.cmds.start_recording()
        self.cmds.record_action("click")
        self.cmds.stop_recording()
        result = self.cmds.save_macro("test_macro")
        assert result.success is True
        (MACRO_DIR / "test_macro.json").unlink(missing_ok=True)

    def test_save_empty(self):
        result = self.cmds.save_macro("empty")
        assert result.success is False

    def test_list_empty(self):
        for f in MACRO_DIR.glob("*.json"):
            f.unlink()
        result = self.cmds.list_macros()
        assert result.success is True
        assert "No saved" in result.message

    def test_list_with_data(self):
        self.cmds.start_recording()
        self.cmds.record_action("click")
        self.cmds.stop_recording()
        self.cmds.save_macro("list_test")
        result = self.cmds.list_macros()
        assert result.success is True
        assert "list_test" in result.message
        (MACRO_DIR / "list_test.json").unlink(missing_ok=True)

    def test_load_macro(self):
        self.cmds.start_recording()
        self.cmds.record_action("click")
        self.cmds.stop_recording()
        self.cmds.save_macro("load_test")
        result = self.cmds.load_macro("load_test")
        assert result.success is True
        (MACRO_DIR / "load_test.json").unlink(missing_ok=True)

    def test_load_not_found(self):
        result = self.cmds.load_macro("nonexistent")
        assert result.success is False

    def test_delete_macro(self):
        self.cmds.start_recording()
        self.cmds.record_action("click")
        self.cmds.stop_recording()
        self.cmds.save_macro("del_test")
        result = self.cmds.delete_macro("del_test")
        assert result.success is True

    def test_delete_not_found(self):
        result = self.cmds.delete_macro("nonexistent")
        assert result.success is False

    def test_execute_start(self):
        result = self.cmds.execute("start recording")
        assert result.success is True

    def test_execute_stop(self):
        self.cmds.start_recording()
        result = self.cmds.execute("stop recording")
        assert result.success is True

    def test_execute_save(self):
        self.cmds.start_recording()
        self.cmds.record_action("test")
        self.cmds.stop_recording()
        result = self.cmds.execute("save macro quick")
        assert result.success is True
        (MACRO_DIR / "quick.json").unlink(missing_ok=True)

    def test_execute_list(self):
        result = self.cmds.execute("list macros")
        assert result.success is True

    def test_execute_unknown(self):
        result = self.cmds.execute("fly to mars")
        assert result.success is False
