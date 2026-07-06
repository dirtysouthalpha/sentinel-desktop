"""
Sentinel Desktop v30.0.0 - Advanced Vision Pipeline.

Combines OCR, template matching, and confidence scoring
for enhanced UI element detection.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """A single detection from the vision pipeline."""
    label: str
    text: str = ""
    confidence: float = 0.0
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, w, h
    method: str = ""  # ocr, template, fusion


@dataclass
class VisionReport:
    """Full vision analysis report for a screenshot."""
    detections: list[DetectionResult] = field(default_factory=list)
    text_blocks: list[str] = field(default_factory=list)
    width: int = 0
    height: int = 0
    confidence_avg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API response."""
        return {
            "detections": [
                {"label": d.label, "text": d.text, "confidence": d.confidence, "bbox": list(d.bbox), "method": d.method}
                for d in self.detections
            ],
            "text_blocks": self.text_blocks,
            "width": self.width,
            "height": self.height,
            "confidence_avg": round(self.confidence_avg, 3),
        }


def analyze_screenshot(image_b64: str | None = None, image_path: str | None = None) -> VisionReport:
    """Analyze a screenshot using OCR and return a vision report.

    Args:
        image_b64: Base64-encoded PNG image.
        image_path: Path to image file.

    Returns:
        VisionReport with detections and text blocks.
    """
    report = VisionReport()

    # Try to load PIL image
    pil_image = None
    try:
        from PIL import Image
        if image_path:
            pil_image = Image.open(image_path)
        elif image_b64:
            img_data = base64.b64decode(image_b64)
            pil_image = Image.open(io.BytesIO(img_data))
    except Exception as e:
        logger.debug("Failed to load image: %s", e)
        return report

    if pil_image is None:
        return report

    report.width = pil_image.width
    report.height = pil_image.height

    # OCR pass
    try:
        import pytesseract
        ocr_data = pytesseract.image_to_data(pil_image, output_type=pytesseract.Output.DICT)
        for i in range(len(ocr_data["text"])):
            text = ocr_data["text"][i].strip()
            if text and int(ocr_data["conf"][i]) > 30:
                conf = int(ocr_data["conf"][i]) / 100.0
                report.detections.append(DetectionResult(
                    label="text",
                    text=text,
                    confidence=conf,
                    bbox=(ocr_data["left"][i], ocr_data["top"][i], ocr_data["width"][i], ocr_data["height"][i]),
                    method="ocr",
                ))
                report.text_blocks.append(text)
    except Exception as e:
        logger.debug("OCR failed: %s", e)

    # Template matching pass (if OpenCV available)
    try:
        import numpy as np
        import cv2
        img_array = np.array(pil_image)
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        # Edge detection for UI elements
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 20 and h > 20 and w < report.width * 0.8 and h < report.height * 0.8:
                area_ratio = (w * h) / (report.width * report.height)
                report.detections.append(DetectionResult(
                    label="ui_element",
                    text="",
                    confidence=round(min(area_ratio * 10, 0.9), 3),
                    bbox=(x, y, w, h),
                    method="template",
                ))
    except Exception as e:
        logger.debug("Template matching failed: %s", e)

    # Calculate average confidence
    if report.detections:
        report.confidence_avg = sum(d.confidence for d in report.detections) / len(report.detections)

    return report
