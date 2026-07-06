"""Multi-step AI agent that plans and executes complex tasks."""
import json
import re
from core.legacy_engine import CommandResult


AVAILABLE_COMMANDS = [
    "cpu", "memory", "disk", "processes", "battery", "temp", "uptime", "system info",
    "screenshot", "click X,Y", "type text", "press key", "move X,Y", "scroll direction",
    "ping host", "ipconfig", "network diagnostics", "speedtest",
    "open appname", "kill processname", "list path", "find filename", "read filepath",
    "copy text", "paste", "list windows",
    "volume up", "volume down", "mute", "play", "pause", "next track", "previous track",
    "shutdown", "restart", "sleep", "lock screen",
    "notify message", "alert message", "remind message",
    "timer seconds", "list timers", "cancel timer id",
    "brief url", "fetch url", "go to url", "search for query",
    "start recording", "stop recording", "save macro name", "list macros",
    "list plugins", "speak text",
]


class AgentPlanner:
    """Breaks complex requests into steps and executes them using LLM planning."""

    def __init__(self, engine=None, brain=None):
        self.engine = engine
        self.brain = brain
        self.llm = None
        self.max_steps = 10

    def _get_llm(self):
        if self.llm is None:
            try:
                from core.legacy_llm import LLMClient
                self.llm = LLMClient()
            except Exception:
                pass
        return self.llm

    def is_complex(self, text: str) -> bool:
        """Check if a request needs multi-step planning."""
        t = text.lower()
        word_count = len(t.split())
        has_indicator = any(ind in t for ind in [
            " then ", " after that ", " and then ", " and also ",
            " step by step ", "first ", "second ", "finally ",
            " also ", " next ", " once done ", " when finished ",
        ])
        has_many_commas = t.count(",") >= 2
        is_long = word_count > 15
        return has_indicator or has_many_commas or is_long

    def create_plan(self, text: str) -> list:
        """Break a complex request into executable steps using LLM."""
        llm = self._get_llm()
        if llm:
            try:
                plan = llm.plan(text, AVAILABLE_COMMANDS)
                if plan and len(plan) > 1:
                    return plan[:self.max_steps]
            except Exception:
                pass
        return self._keyword_fallback_plan(text)

    def _keyword_fallback_plan(self, text: str) -> list:
        """Fallback: split on keywords when LLM is unavailable."""
        parts = re.split(
            r'(?:,\s*then\s+|,\s*after\s+|,\s*and\s+then\s+|,\s*and\s+also\s+|\bthen\b|\bafter that\b|\bonce done\b|\bwhen finished\b|\bfinally\b|\bnext\b)',
            text,
            flags=re.IGNORECASE
        )
        parts = [p.strip().rstrip(".,;!") for p in parts if p.strip()]
        if len(parts) <= 1:
            comma_parts = [p.strip() for p in text.split(",") if p.strip()]
            parts = comma_parts if len(comma_parts) > 1 else [text.strip()]
        cleaned = []
        for step in parts:
            step = re.sub(r'^(hey|hi|please|can you|could you|i want you to|sentinel)[,\s]*', '', step, flags=re.IGNORECASE).strip()
            if step:
                cleaned.append(step)
        return cleaned[:self.max_steps]

    def execute_plan(self, text: str) -> CommandResult:
        """Create a plan and execute each step."""
        steps = self.create_plan(text)
        if len(steps) <= 1:
            return CommandResult(False, "")
        results = []
        llm_used = self._get_llm() is not None
        source = "AI-planned" if llm_used else "keyword-split"
        results.append(f"PLAN ({source}): {len(steps)} steps")
        results.append("")
        for i, step in enumerate(steps, 1):
            results.append(f"Step {i}/{len(steps)}: {step}")
            if self.engine:
                result = self.engine.execute(step)
                if result.success:
                    msg = result.message
                    if len(msg) > 300:
                        msg = msg[:300] + "..."
                    results.append(f"  OK: {msg}")
                else:
                    results.append(f"  SKIP: {result.message}")
            else:
                results.append("  No engine available")
            results.append("")
        results.append(f"Plan complete: {len(steps)} steps executed.")
        return CommandResult(True, "\n".join(results), {"steps": steps, "count": len(steps)})

    def execute(self, text: str) -> CommandResult:
        """Entry point for agent commands."""
        return self.execute_plan(text)
