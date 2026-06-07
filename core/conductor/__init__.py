"""Sentinel Desktop v12.0 — Conductor subpackage.

Multi-agent orchestration with LLM-powered task decomposition,
parallel execution, and result synthesis.
"""

from core.conductor.coordinator import Conductor
from core.conductor.parallel import ParallelExecutor
from core.conductor.planner import TaskPlanner
from core.conductor.synthesizer import ResultSynthesizer

__all__ = ["TaskPlanner", "ParallelExecutor", "ResultSynthesizer", "Conductor"]
