"""
Command Engine - Routes user input to the correct handler.
Supports natural language parsing, direct commands, and AI routing.
"""
import logging
import re
from typing import Optional
from src.core.brain import BrainClient

logger = logging.getLogger(__name__)


class CommandResult:
    """Result of a command execution."""
    def __init__(self, success: bool, message: str, data: dict = None):
        self.success = success
        self.message = message
        self.data = data or {}

    def __str__(self):
        return self.message


class CommandEngine:
    """Routes commands to registered handlers."""

    def __init__(self, brain: BrainClient = None):
        self.brain = brain or BrainClient()
        self.handlers = {}
        self.aliases = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register built-in command handlers."""
        from src.commands.system import SystemCommands
        from src.commands.automation import AutomationCommands
        from src.commands.network import NetworkCommands
        from src.commands.process import ProcessCommands
        from src.commands.files import FileCommands

        self.sys = SystemCommands()
        self.auto = AutomationCommands()
        self.net = NetworkCommands()
        self.proc = ProcessCommands()
        self.files = FileCommands()

    def parse_command(self, text: str) -> Optional[tuple]:
        """Parse natural language into (handler, args)."""
        text_lower = text.lower().strip()

        # Help
        if text_lower in ["help", "commands", "?", "what can you do"]:
            return ("system", "help")

        # System commands
        if any(w in text_lower for w in ["cpu", "processor"]):
            return ("system", "cpu")
        if any(w in text_lower for w in ["memory", "ram", "mem"]):
            return ("system", "memory")
        if any(w in text_lower for w in ["disk", "storage", "drive"]):
            return ("system", "disk")
        if any(w in text_lower for w in ["processes", "tasks", "running"]):
            return ("system", "processes")
        if any(w in text_lower for w in ["system info", "sysinfo", "system status"]):
            return ("system", "info")
        if "battery" in text_lower:
            return ("system", "battery")
        if "temp" in text_lower or "temperature" in text_lower:
            return ("system", "temperature")
        if "uptime" in text_lower:
            return ("system", "uptime")

        # Power management
        if any(w in text_lower for w in ["shutdown", "restart", "reboot", "sleep", "suspend", "lock screen", "lock computer", "power off", "cancel shutdown"]):
            return ("power", text)

        # Notifications
        if any(w in text_lower for w in ["notify", "alert", "remind"]):
            return ("notify", text)

        # Scheduler
        if any(w in text_lower for w in ["timer", "set timer", "list timers", "cancel timer"]):
            return ("scheduler", text)

        # Media controls
        if any(w in text_lower for w in ["volume", "mute", "unmute"]):
            return ("media", text)
        if any(w in text_lower for w in ["play", "pause", "next track", "previous track", "prev track", "stop media"]):
            return ("media", text)

        # Automation commands
        if text_lower.startswith("click"):
            return ("automation", text)
        if text_lower.startswith("type "):
            return ("automation", text)
        if text_lower.startswith("press "):
            return ("automation", text)
        if text_lower.startswith("move"):
            return ("automation", text)
        if "screenshot" in text_lower or "capture" in text_lower:
            return ("automation", "screenshot")
        if "scroll" in text_lower:
            return ("automation", text)
        if text_lower.startswith("drag"):
            return ("automation", text)

        # Network commands
        if text_lower.startswith("ping"):
            return ("network", text)
        if "ip" in text_lower and "config" in text_lower:
            return ("network", "ipconfig")
        if "ipconfig" in text_lower or "ip config" in text_lower:
            return ("network", "ipconfig")
        if "network" in text_lower and ("diag" in text_lower or "check" in text_lower or "test" in text_lower):
            return ("network", "diagnostics")
        if "wifi" in text_lower or "internet" in text_lower:
            return ("network", "diagnostics")
        if text_lower.startswith("speedtest"):
            return ("network", "speedtest")

        # Process management
        if text_lower.startswith("kill") or text_lower.startswith("close "):
            return ("process", text)
        if text_lower.startswith("open ") or text_lower.startswith("launch"):
            return ("process", text)

        # Clipboard
        if text_lower.startswith("copy "):
            return ("clipboard", text)
        if text_lower in ["paste", "clipboard"]:
            return ("clipboard", "read")

        # Window management (before file ops to catch "list windows")
        if ("window" in text_lower and ("list" in text_lower or "show" in text_lower)) or text_lower == "windows":
            return ("windows", "list")

        # File operations
        if text_lower.startswith("list ") or text_lower.startswith("dir") or text_lower.startswith("ls"):
            return ("files", text)
        if text_lower.startswith("find") or text_lower.startswith("search file"):
            return ("files", text)
        if text_lower.startswith("read "):
            return ("files", text)

        # Brain/AI
        if any(w in text_lower for w in ["brain", "think", "remember", "recall"]):
            return ("ai", text)

        return None

    def execute(self, text: str) -> CommandResult:
        """Execute a user command and return the result."""
        parsed = self.parse_command(text)

        if parsed is None:
            return self._ai_route(text)

        category, args = parsed

        try:
            if category == "system":
                return self._run_system(args)
            elif category == "automation":
                return self._run_automation(args)
            elif category == "network":
                return self._run_network(args)
            elif category == "process":
                return self._run_process(args)
            elif category == "files":
                return self._run_files(args)
            elif category == "power":
                return self._run_power(args)
            elif category == "scheduler":
                return self._run_scheduler(args)
            elif category == "notify":
                return self._run_notify(args)
            elif category == "media":
                return self._run_media(args)
            elif category == "clipboard":
                return self._run_clipboard(args)
            elif category == "windows":
                return self._run_windows(args)
            elif category == "ai":
                return self._run_ai(args)
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return CommandResult(False, f"Error: {e}")

        return CommandResult(False, "Unknown command")

    def _run_system(self, args) -> CommandResult:
        cmd = args if isinstance(args, str) else args
        if cmd == "help":
            return self.sys.help()
        if cmd == "cpu":
            return self.sys.cpu_usage()
        if cmd == "memory":
            return self.sys.memory_usage()
        if cmd == "disk":
            return self.sys.disk_usage()
        if cmd == "processes":
            return self.sys.list_processes()
        if cmd == "info":
            return self.sys.system_info()
        if cmd == "battery":
            return self.sys.battery_info()
        if cmd == "temperature":
            return self.sys.temperature()
        if cmd == "uptime":
            return self.sys.uptime()
        return CommandResult(False, f"Unknown system command: {cmd}")

    def _run_automation(self, args) -> CommandResult:
        if isinstance(args, str) and args == "screenshot":
            return self.auto.screenshot()
        return self.auto.execute(args)

    def _run_network(self, args) -> CommandResult:
        if isinstance(args, str):
            if args == "ipconfig":
                return self.net.ipconfig()
            if args == "diagnostics":
                return self.net.diagnostics()
            if args == "speedtest":
                return self.net.speedtest()
            if args.startswith("ping"):
                host = args.split(None, 1)[1] if len(args.split()) > 1 else "google.com"
                return self.net.ping(host)
        return CommandResult(False, "Unknown network command")

    def _run_process(self, args) -> CommandResult:
        if isinstance(args, str):
            if args.startswith("kill") or args.startswith("close"):
                name = args.split(None, 1)[1] if len(args.split()) > 1 else ""
                return self.proc.kill_process(name)
            if args.startswith("open") or args.startswith("launch"):
                name = args.split(None, 1)[1] if len(args.split()) > 1 else ""
                return self.proc.open_application(name)
        return CommandResult(False, "Unknown process command")

    def _run_files(self, args) -> CommandResult:
        return self.files.execute(args)

    def _run_power(self, args) -> CommandResult:
        return self.power.execute(args)

    def _run_scheduler(self, args) -> CommandResult:
        return self.scheduler.execute(args)

    def _run_notify(self, args) -> CommandResult:
        return self.notify.execute(args)

    def _run_media(self, args) -> CommandResult:
        return self.media.execute(args)

    def _run_clipboard(self, args) -> CommandResult:
        if isinstance(args, str):
            if args == "read":
                return self.clip.read()
            if args.startswith("copy"):
                text = args[5:].strip() if len(args) > 5 else ""
                return self.clip.write(text)
        return self.clip.execute(args)

    def _run_windows(self, args) -> CommandResult:
        if isinstance(args, str) and args == "list":
            return self.win_mgr.list_windows()
        return self.win_mgr.execute(args)

    def _run_ai(self, args) -> CommandResult:
        if isinstance(args, str):
            if args.lower().startswith("recall"):
                query = args.split(None, 1)[1] if len(args.split()) > 1 else ""
                results = self.brain.recall(query)
                if results:
                    text = chr(10).join([f"- {r.get('topic', '')}: {r.get('content', '')[:100]}" for r in results[:5]])
                    return CommandResult(True, f"Brain recall:" + chr(10) + text)
                return CommandResult(True, "No results found in brain.")
            if args.lower().startswith("think"):
                parts = args.split(None, 2)
                if len(parts) >= 3:
                    self.brain.think(parts[1], parts[2])
                    return CommandResult(True, f"Stored in brain: {parts[1]}")
                return CommandResult(False, "Usage: think <topic> <content>")
            if args.lower().startswith("brain status"):
                health = self.brain.health()
                stats = self.brain.stats()
                return CommandResult(True, f"Brain Status: {health}" + chr(10) + f"Stats: {stats}")
        return CommandResult(False, "Unknown AI command")

    def _ai_route(self, text: str) -> CommandResult:
        """Fall back to brain for natural language."""
        result = self.brain.ask(text)
        if result and result != "No relevant knowledge found in brain.":
            return CommandResult(True, f"AI: {result}")
        return CommandResult(False, f"I couldn't understand '{text}'. Type 'help' for available commands.")
