"""QQuickImageProvider for live screenshot display in QML."""

from __future__ import annotations

import logging

from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

logger = logging.getLogger(__name__)


class ScreenshotProvider(QQuickImageProvider):
    """Serves the latest agent screenshot to QML Image elements."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._current: QImage | None = None

    def set_image(self, img: QImage) -> None:
        self._current = img

    def requestImage(
        self,
        id: str,
        requestedSize: object,
    ) -> tuple:
        if self._current and not self._current.isNull():
            w = self._current.width()
            h = self._current.height()
            if hasattr(requestedSize, "width") and requestedSize.width() > 0:
                w = requestedSize.width()
            if hasattr(requestedSize, "height") and requestedSize.height() > 0:
                h = requestedSize.height()
            return (self._current.scaled(w, h), id)
        fallback = QImage(320, 240, QImage.Format.Format_RGB32)
        fallback.fill(0x0A080F)
        return (fallback, id)
