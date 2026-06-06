"""Sentinel Desktop v5.0 — Multi-Modal Perception Pipeline.

Provides a layered perception system that combines accessibility tree data,
OCR text extraction, and vision model analysis into a unified element map
with annotated screenshots for the LLM.

Pipeline:
    Screenshot → [Accessibility Tree] → [Screen Parser] → [OCR] → [Fusion] → Annotated Output

Usage::

    from core.perception import PerceptionPipeline

    pipeline = PerceptionPipeline()
    result = pipeline.analyze(screenshot)
    # result.annotated_image  — PIL Image with bounding boxes
    # result.elements          — list of PerceptionElement
    # result.text_description  — text summary for LLM context
"""

from __future__ import annotations

import logging

from core.perception.annotator import annotate_screenshot
from core.perception.fusion import FusionEngine
from core.perception.pipeline import PerceptionPipeline
from core.perception.types import PerceptionElement, PerceptionResult

logger = logging.getLogger(__name__)

__all__ = [
    "PerceptionPipeline",
    "PerceptionElement",
    "PerceptionResult",
    "FusionEngine",
    "annotate_screenshot",
]
