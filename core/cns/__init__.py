"""Sentinel Desktop vNext — Cognitive Navigation System (CNS) 1.0.

The CNS is the fleet's reasoning engine. It decomposes complex goals
into task graphs, evaluates execution results, and closes the loop
between planning and observation.

Modules:
  planner     — Goal decomposition into dependency-linked subtasks
  evaluator   — Result scoring and pass/fail determination
  conductor   — Orchestrates plan→execute→evaluate cycles
  reasoner    — Rule-based reasoning over task outputs

The CNS sits on top of the mesh layer (core/mesh/). The mesh handles
node-to-node communication; the CNS handles *what* to do and *whether
it worked*.
"""
from core.cns.planner import TaskPlanner, Subtask, TaskType
from core.cns.evaluator import Evaluator, EvalResult, EvalStatus, compute_score
from core.cns.conductor import Conductor, PlanResult, SubtaskHandler
from core.cns.reasoner import (
    Reasoner,
    ReasoningResult,
    Conclusion,
    Rule,
    default_reasoner,
)
from core.cns.recall import (
    RecallEvaluator,
    RecallReport,
    GoldenQuery,
    QueryResult,
    GOLDEN_QUERIES,
    make_http_backend,
)

__all__ = [
    "TaskPlanner",
    "Subtask",
    "TaskType",
    "Evaluator",
    "EvalResult",
    "EvalStatus",
    "compute_score",
    "Conductor",
    "PlanResult",
    "SubtaskHandler",
    "Reasoner",
    "ReasoningResult",
    "Conclusion",
    "Rule",
    "default_reasoner",
    "RecallEvaluator",
    "RecallReport",
    "GoldenQuery",
    "QueryResult",
    "GOLDEN_QUERIES",
    "make_http_backend",
]
