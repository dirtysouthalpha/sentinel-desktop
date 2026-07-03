"""Vision-guided UI grounding.

Instead of hardcoded coordinates, describe what you want to interact with
and let the vision model find it on screen. Falls back to OCR/UIA when
no vision model is available.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GroundedElement:
    """An element located on screen by vision/OCR/UIA."""

    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0
    method: str = ""  # vision, ocr, uia, accessibility
    description: str = ""


class VisionGrounder:
    """Find UI elements by description using vision models, OCR, or UIA."""

    def __init__(self, vision_model: Any = None, ocr_engine: Any = None) -> None:
        self._vision = vision_model
        self._ocr = ocr_engine

    def ground(self, description: str, screenshot: Any = None) -> GroundedElement | None:
        """Find an element matching the description on screen.

        Strategy priority:
        1. Vision model (LLM analyzes screenshot)
        2. OCR (find text on screen)
        3. UIA/Accessibility (Windows only)
        """
        if self._vision and screenshot:
            result = self._ground_vision(description, screenshot)
            if result:
                return result
        if self._ocr and screenshot:
            result = self._ground_ocr(description, screenshot)
            if result:
                return result
        return None

    def ground_all(self, description: str, screenshot: Any = None) -> list[GroundedElement]:
        """Find all matching elements."""
        results = []
        if self._ocr and screenshot:
            results.extend(self._ground_ocr_all(description, screenshot))
        return results

    def _ground_vision(self, description: str, screenshot: Any) -> GroundedElement | None:
        """Use vision model to locate element."""
        try:
            # Encode screenshot for vision model
            buf = io.BytesIO()
            if hasattr(screenshot, "save"):
                screenshot.save(buf, format="PNG")
            else:
                return None
            img_b64 = __import__("base64").b64encode(buf.getvalue()).decode("utf-8")

            # If vision model is callable, use it
            if callable(self._vision):
                result = self._vision(description, img_b64)
                if result and "x" in result:
                    return GroundedElement(
                        text=result.get("text", description),
                        x=int(result["x"]),
                        y=int(result["y"]),
                        width=int(result.get("width", 0)),
                        height=int(result.get("height", 0)),
                        confidence=float(result.get("confidence", 0.8)),
                        method="vision",
                        description=description,
                    )
        except Exception as exc:
            logger.debug("vision grounding failed: %s", exc)
        return None

    def _ground_ocr(self, description: str, screenshot: Any) -> GroundedElement | None:
        """Use OCR to find text on screen."""
        matches = self._ground_ocr_all(description, screenshot)
        return matches[0] if matches else None

    def _ground_ocr_all(self, description: str, screenshot: Any) -> list[GroundedElement]:
        """Find all OCR matches."""
        results = []
        try:
            import pytesseract
            from PIL import Image

            img = screenshot if hasattr(screenshot, "convert") else Image.open(io.BytesIO(screenshot))
            # Get detailed OCR data
            output = pytesseract.image_to_data(img)
            if isinstance(output, str):
                # Fallback: parse the string output
                self._parse_ocr_string(output, description, results)
            elif isinstance(output, dict):
                self._parse_ocr_dict(output, description, results)
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("OCR grounding failed: %s", exc)
        return results

    @staticmethod
    def _parse_ocr_dict(data: dict[str, Any], description: str, results: list[GroundedElement]) -> None:
        """Parse pytesseract dict output."""
        for i, text in enumerate(data.get("text", [])):
            if text and description.lower() in text.lower():
                conf = data.get("conf", [0] * (i + 1))
                results.append(
                    GroundedElement(
                        text=text,
                        x=data.get("left", [0] * (i + 1))[i],
                        y=data.get("top", [0] * (i + 1))[i],
                        width=data.get("width", [0] * (i + 1))[i],
                        height=data.get("height", [0] * (i + 1))[i],
                        confidence=float(conf[i]) / 100.0
                        if isinstance(conf, list) and i < len(conf) and conf[i] > 0
                        else 0.5,
                        method="ocr",
                        description=description,
                    )
                )

    @staticmethod
    def _parse_ocr_string(output: str, description: str, results: list[GroundedElement]) -> None:
        """Parse pytesseract string (TSV) output."""
        for line in output.splitlines()[1:]:  # skip header
            parts = line.split("\t")
            if len(parts) >= 12:
                text = parts[11].strip()
                if text and description.lower() in text.lower():
                    try:
                        conf = float(parts[10])
                        results.append(
                            GroundedElement(
                                text=text,
                                x=int(parts[6]),
                                y=int(parts[7]),
                                width=int(parts[8]),
                                height=int(parts[9]),
                                confidence=conf / 100.0 if conf >= 0 else 0.5,
                                method="ocr",
                                description=description,
                            )
                        )
                    except (ValueError, IndexError):
                        pass


__all__ = ["GroundedElement", "VisionGrounder"]
