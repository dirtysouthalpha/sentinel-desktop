"""Multi-step AI agent that plans and executes complex tasks."""
import json
import re
from src.core.engine import CommandResult


class AgentPlanner:
    """Breaks complex requests into steps and executes them."""

    def __init__(self, engine=None, brain=None):
        self.engine = engine
        self.brain = brain
        self.max_steps = 10

    def is_complex(self, text: str) -> bool:
        """Check if a request needs multi-step planning."""
        indicators = [
            "then", "after that", "and also", "and then", 
            "step by step", "plan", "first", "second", "finally",
            "also", "next", "once done", "when finished",
            "research", "compile", "gather", "organize",
            "analyze", "investigate",
        ]
        t = text.lower()
        word_count = len(t.split())
        has_indicator = any(ind in t for ind in indicators)
        has_many_commas = t.count(",") >= 2
        is_long = word_count > 10
        return has_indicator or has_many_commas or (is_long and "," in text)

    def create_plan(self, text: str) -> list:
        """Break a complex request into executable steps."""
        plan = []
        
        # Split on common multi-step indicators
        parts = re.split(
            r'(?:,\s*then\s+|,\s*after\s+|,\s*and\s+then\s+|,\s*and\s+also\s+|\bthen\b|\bafter that\b|\bonce done\b|\bwhen finished\b|\bfinally\b|\bnext\b)',
            text, 
            flags=re.IGNORECASE
        )
        parts = [p.strip().rstrip(".,;!") for p in parts if p.strip()]
        
        # If splitting worked, use those parts
        if len(parts) > 1:
            plan = parts
        else:
            # Try splitting on commas for compound requests
            comma_parts = [p.strip() for p in text.split(",") if p.strip()]
            if len(comma_parts) > 1:
                plan = comma_parts
            else:
                # Single step - not actually complex
                plan = [text.strip()]
        
        # Clean up steps - remove filler words
        cleaned = []
        for step in plan:
            step = re.sub(r'^(hey|hi|please|can you|could you|i want you to|sentinel)[,\s]*', '', step, flags=re.IGNORECASE).strip()
            if step:
                cleaned.append(step)
        
        return cleaned[:self.max_steps]

    def execute_plan(self, text: str) -> CommandResult:
        """Create a plan and execute each step."""
        steps = self.create_plan(text)
        
        if len(steps) <= 1:
            return CommandResult(False, "")  # Signal: not a multi-step task
        
        results = []
        results.append(f"📋 PLAN: {len(steps)} steps detected")
        results.append("")
        
        for i, step in enumerate(steps, 1):
            results.append(f"▶ Step {i}/{len(steps)}: {step}")
            
            if self.engine:
                result = self.engine.execute(step)
                if result.success:
                    # Truncate long results
                    msg = result.message
                    if len(msg) > 300:
                        msg = msg[:300] + "..."
                    results.append(f"  ✅ {msg}")
                else:
                    results.append(f"  ❌ {result.message}")
            else:
                results.append("  ⚠ No engine available")
            results.append("")
        
        results.append(f"✅ Plan complete: {len(steps)} steps executed.")
        return CommandResult(True, "\n".join(results), {"steps": steps, "count": len(steps)})

    def execute(self, text: str) -> CommandResult:
        """Entry point for agent commands."""
        return self.execute_plan(text)
