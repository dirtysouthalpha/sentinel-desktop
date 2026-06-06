"""Sentinel Desktop v6.0 — Deep Control Layer.

Implements the Plan → Ground → Execute → Verify loop that separates
high-level task planning from precise coordinate grounding and
post-action verification.

Architecture:
    Planner  (heavy LLM)  — decomposes goal into high-level steps
    Grounder (fast model)  — converts semantic targets to screen coordinates
    Verifier (screenshot)  — confirms action success via before/after comparison
"""

from core.control.grounder import ActionGrounder
from core.control.loop import ControlLoop
from core.control.planner import PlanStep, TaskPlanner
from core.control.verifier import ActionVerifier

__all__ = [
    "TaskPlanner",
    "PlanStep",
    "ActionGrounder",
    "ActionVerifier",
    "ControlLoop",
]
