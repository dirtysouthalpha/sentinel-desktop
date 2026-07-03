"""Plugin system for Sentinel Desktop."""
import importlib
import importlib.util
import logging
from pathlib import Path
from src.core.engine import CommandResult

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).parent.parent.parent / "plugins"


class PluginManager:
    """Load and manage external plugins."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.plugins = {}
            cls._instance._loaded = False
        return cls._instance

    def discover(self) -> list:
        """Discover available plugins."""
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        found = [f.stem for f in PLUGIN_DIR.glob("plugin_*.py")]
        logger.info(f"Discovered plugins: {found}")
        return found

    def load_all(self) -> CommandResult:
        """Load all discovered plugins."""
        if self._loaded:
            return CommandResult(True, "Plugins already loaded")
        names = self.discover()
        loaded = 0
        for name in names:
            result = self.load(name)
            if result.success:
                loaded += 1
        self._loaded = True
        return CommandResult(True, f"Loaded {loaded}/{len(names)} plugins")

    def load(self, name: str) -> CommandResult:
        """Load a single plugin."""
        filepath = PLUGIN_DIR / f"{name}.py"
        if not filepath.exists():
            return CommandResult(False, f"Plugin not found: {name}")
        try:
            spec = importlib.util.spec_from_file_location(name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.plugins[name] = module
            logger.info(f"Loaded plugin: {name}")
            return CommandResult(True, f"Plugin loaded: {name}")
        except Exception as e:
            logger.error(f"Failed to load plugin '{name}': {e}")
            return CommandResult(False, f"Plugin load error: {e}")

    def list_plugins(self) -> CommandResult:
        """List all available plugins."""
        names = self.discover()
        if not names:
            return CommandResult(True, "No plugins available")
        lines = "\n".join([f"  - {n}" for n in sorted(names)])
        return CommandResult(True, "Available plugins:\n" + lines)

    def execute(self, text: str) -> CommandResult:
        """Parse and execute plugin commands."""
        t = text.lower().strip()
        if t in ["list plugins", "plugins"]:
            return self.list_plugins()
        if t.startswith("load plugin"):
            parts = text.split(None, 2)
            name = parts[2] if len(parts) >= 3 else ""
            if name:
                return self.load(name)
            return CommandResult(False, "Usage: load plugin <name>")
        return CommandResult(False, f"Unknown plugin command: {text}")
