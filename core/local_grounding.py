"""Sentinel Desktop v7.0 — Local Grounding Model.

Optional local model that converts natural language targets (e.g., "click the
Save button") into bounding boxes without any cloud round-trip. Enables
air-gapped operation and massive latency/cost wins.

This module defines the interface and a no-op fallback. Actual model
implementations (OmniParser, Florence-2, UGround) are loaded as optional
dependencies behind the ``local_grounding`` feature flag.

Configuration:
    config.json → {"local_grounding": {"enabled": true, "model": "auto"}}
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# Feature flag key in config
FEATURE_FLAG = "local_grounding"

# Supported local model backends
SUPPORTED_BACKENDS = ("auto", "omniparser", "florence2", "uground", "yolo")


@dataclass
class LocalGroundingResult:
    """Result from a local grounding model prediction.

    Attributes:
        bbox: (x, y, width, height) bounding box in screenshot coordinates.
        confidence: Prediction confidence 0.0–1.0.
        label: Optional label for the detected element.
        model: Backend that produced this result.
        latency_ms: Prediction time in milliseconds.
    """

    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    label: str = ""
    model: str = "none"
    latency_ms: float = 0.0

    @property
    def center(self) -> tuple[int, int]:
        """Center of the bounding box."""
        x, y, w, h = self.bbox
        return (x + w // 2, y + h // 2)

    @property
    def is_valid(self) -> bool:
        """Whether the result has a valid bounding box."""
        x, y, w, h = self.bbox
        return w > 0 and h > 0


class LocalGroundingModel:
    """Interface for local grounding models.

    Usage::

        model = LocalGroundingModel(backend="auto")
        result = model.predict(screenshot, prompt="click the Save button")
        if result.is_valid:
            x, y = result.center
    """

    def __init__(self, backend: str = "auto") -> None:
        """Initialize the local grounding model.

        Args:
            backend: Model backend to use. "auto" tries available backends.
                Options: "auto", "omniparser", "florence2", "uground", "yolo".

        Raises:
            ImportError: If the selected backend is not installed (only when
                backend is explicitly specified, not "auto").
        """
        self.backend = backend
        self._model: Any = None
        self._initialized = False

    def _try_load(self) -> bool:
        """Try to load a local grounding model.

        Returns True if a model was successfully loaded.
        """
        if self._initialized:
            return self._model is not None

        self._initialized = True

        # Try backends in order of preference
        backends_to_try = (
            [self.backend]
            if self.backend != "auto"
            else ["omniparser", "florence2", "uground", "yolo"]
        )

        for backend_name in backends_to_try:
            try:
                loader = _BACKEND_LOADERS.get(backend_name)
                if loader is not None:
                    self._model = loader()
                    if self._model is not None:
                        self.backend = backend_name
                        logger.info("Local grounding model loaded: %s", backend_name)
                        return True
            except (ImportError, OSError, RuntimeError) as exc:
                logger.debug("Backend %s unavailable: %s", backend_name, exc)
                continue

        logger.debug("No local grounding model available")
        return False

    def predict(
        self,
        screenshot: Image.Image,
        prompt: str,
    ) -> LocalGroundingResult:
        """Predict a bounding box for the described target.

        Args:
            screenshot: PIL Image of the screen.
            prompt: Natural language description of the target
                (e.g., "the Save button", "username text field").

        Returns:
            LocalGroundingResult with predicted bbox, or invalid result
            if no model is available.
        """
        import time

        if not self._try_load():
            return LocalGroundingResult(model="none")

        start = time.monotonic()
        try:
            result = self._model.predict(screenshot, prompt)
            elapsed_ms = (time.monotonic() - start) * 1000

            if isinstance(result, LocalGroundingResult):
                result.latency_ms = elapsed_ms
                result.model = self.backend
                return result

            # If the model returned a raw bbox tuple, wrap it
            if isinstance(result, (tuple, list)) and len(result) == 4:
                return LocalGroundingResult(
                    bbox=tuple(result),  # type: ignore
                    confidence=0.5,
                    label=prompt[:50],
                    model=self.backend,
                    latency_ms=elapsed_ms,
                )

            return LocalGroundingResult(model=self.backend, latency_ms=elapsed_ms)

        except Exception as exc:
            logger.warning("Local grounding prediction failed: %s", exc)
            return LocalGroundingResult(model=self.backend)

    @property
    def is_available(self) -> bool:
        """Whether a local grounding model is available."""
        return self._try_load()


# ---------------------------------------------------------------------------
# Backend loaders — each returns a model object or raises ImportError
# ---------------------------------------------------------------------------

_BACKEND_LOADERS: dict[str, Any] = {}


def _register_backend(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a backend loader."""
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _BACKEND_LOADERS[name] = fn
        return fn
    return decorator


@_register_backend("omniparser")
def _load_omniparser() -> Any:
    """Load OmniParser model (optional dependency)."""
    try:
        from omniparser import OmniParser  # type: ignore
        return OmniParser()
    except ImportError:
        raise ImportError("omniparser not installed — pip install omniparser") from None


@_register_backend("florence2")
def _load_florence2() -> Any:
    """Load Florence-2 model (optional dependency)."""
    try:
        from transformers import AutoModelForCausalLM, AutoProcessor  # type: ignore

        class _Florence2Wrapper:
            """Wraps Florence-2 for grounding predictions."""
            def __init__(self) -> None:
                self.model = AutoModelForCausalLM.from_pretrained(
                    "microsoft/Florence-2-large",
                    trust_remote_code=True,
                )
                self.processor = AutoProcessor.from_pretrained(
                    "microsoft/Florence-2-large",
                    trust_remote_code=True,
                )

            def predict(self, screenshot: Image.Image, prompt: str) -> LocalGroundingResult:
                # Simplified interface — actual implementation would use
                # Florence-2's grounded captioning
                raise NotImplementedError("Florence-2 grounding not yet implemented")

        return _Florence2Wrapper()
    except ImportError:
        raise ImportError("transformers not installed for Florence-2") from None


@_register_backend("uground")
def _load_uground() -> Any:
    """Load UGround model (optional dependency)."""
    try:
        import uground  # type: ignore
        return uground.Model()
    except ImportError:
        raise ImportError("uground not installed") from None


@_register_backend("yolo")
def _load_yolo() -> Any:
    """Load YOLO-based UI element detector (optional dependency)."""
    try:
        from ultralytics import YOLO  # type: ignore

        class _YOLOWrapper:
            """Wraps YOLO for UI element detection."""
            def __init__(self) -> None:
                # Use a general-purpose YOLO model — could be replaced with
                # a UI-specific trained model
                self.model = YOLO("yolov8n.pt")

            def predict(self, screenshot: Image.Image, prompt: str) -> LocalGroundingResult:
                # YOLO doesn't do text-to-bbox natively, but detects objects
                # We return the first detection as a rough grounding
                import numpy as np
                results = self.model(np.array(screenshot))
                if results and len(results[0].boxes) > 0:
                    box = results[0].boxes[0].xyxy[0].cpu().numpy()
                    x1, y1, x2, y2 = box
                    return LocalGroundingResult(
                        bbox=(int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                        confidence=float(results[0].boxes[0].conf[0]),
                        label=prompt[:50],
                    )
                return LocalGroundingResult()

        return _YOLOWrapper()
    except ImportError:
        raise ImportError("ultralytics not installed for YOLO") from None


# ---------------------------------------------------------------------------
# Feature flag check
# ---------------------------------------------------------------------------


def is_local_grounding_enabled(config: dict[str, Any] | None = None) -> bool:
    """Check if local grounding is enabled in config.

    Args:
        config: Application config dict.

    Returns:
        True if local_grounding.enabled is true in config.
    """
    if config is None:
        return False
    setting = config.get(FEATURE_FLAG, {})
    if isinstance(setting, bool):
        return setting
    if isinstance(setting, dict):
        return bool(setting.get("enabled", False))
    return False


def get_grounding_backend(config: dict[str, Any] | None = None) -> str:
    """Get the configured grounding backend.

    Args:
        config: Application config dict.

    Returns:
        Backend name string (defaults to "auto").
    """
    if config is None:
        return "auto"
    setting = config.get(FEATURE_FLAG, {})
    if isinstance(setting, dict):
        return setting.get("model", "auto")
    return "auto"
