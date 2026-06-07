"""Sentinel Desktop v11.0 — Memory subpackage.

Persistent memory system with episodic, semantic, and working memory.
Enables the agent to recall past interactions and learn from experience.
"""

from core.memory.episodic import EpisodicMemory
from core.memory.semantic import SemanticMemory
from core.memory.working import WorkingMemory

__all__ = ["EpisodicMemory", "SemanticMemory", "WorkingMemory"]
