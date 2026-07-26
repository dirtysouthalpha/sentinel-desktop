"""Sentinel Desktop Steel — PySide6 + QML launcher.

Replaces the customtkinter GUI with the Steel design system.
Imports the existing core engine unchanged.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

QML_DIR = Path(__file__).resolve().parent / "qml"


def run_steel(config: dict | None = None) -> None:
    """Launch the Steel QML interface."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from gui.bridge.controller import AgentController
    from gui.qml.image_provider import ScreenshotProvider

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Sentinel Desktop")
    app.setOrganizationName("DirtySouthAlpha")

    engine = QQmlApplicationEngine()

    img_provider = ScreenshotProvider()
    engine.addImageProvider("imageProvider", img_provider)

    from config import Config
    try:
        cfg_obj = Config()
        cfg = cfg_obj.load()
    except (OSError, ValueError) as exc:
        logger.warning("Config load failed (%s) — using defaults", exc)
        cfg = {}

    if config:
        cfg.update(config)

    controller = AgentController(cfg)
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("config", cfg)

    qml_file = QML_DIR / "main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        logger.error("Failed to load QML: %s", qml_file)
        sys.exit(1)

    logger.info("Sentinel Desktop Steel launched")
    app.exec()
