#!/usr/bin/env python3
"""
Sentinel Desktop — AI-powered Windows desktop automation agent.

Modes:
  GUI  (default)     : CustomTkinter dark-themed chat interface
  API  (--api)       : FastAPI server on port 8091
  CLI  (--command)   : Single goal, execute, exit

The package version is sourced from ``core.__version__``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from argparse import Namespace

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sentinel")

# ---------------------------------------------------------------------------
# Add project root to sys.path so `core`, `gui`, `api` packages resolve
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def parse_args() -> Namespace:
    from core import __version__

    parser = argparse.ArgumentParser(
        prog="sentinel-desktop",
        description=f"Sentinel Desktop v{__version__} — AI-powered Windows desktop automation",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--api",
        action="store_true",
        help="Launch in headless API mode (FastAPI on port 8091)",
    )
    parser.add_argument(
        "--command",
        "-c",
        type=str,
        default=None,
        help="Execute a single goal in CLI mode and exit",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8091,
        help="Port for API server (default: 8091)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for API server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log state-changing actions instead of executing them",
    )
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Skip every approval prompt and let the agent run uninterrupted",
    )
    return parser.parse_args()


def run_gui() -> None:
    """Launch the CustomTkinter GUI."""
    try:
        import customtkinter as ctk  # noqa: F401  (availability check)
    except ImportError:
        logger.error("customtkinter not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    from config import Config
    from gui.app import SentinelApp

    logger.info("Starting Sentinel Desktop in GUI mode")
    config = Config()
    app = SentinelApp(config)
    app.run()


def run_api(host: str = "0.0.0.0", port: int = 8091) -> None:
    """Launch the FastAPI server."""
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    from api.server import SentinelServer
    from config import Config

    config = Config()
    server = SentinelServer(config)
    app = server.create_app()

    logger.info(f"Starting Sentinel Desktop in API mode on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_cli(goal: str, dry_run: bool = False, autonomous: bool = False) -> None:
    """Execute a single goal and exit."""
    from config import Config
    from core.engine import AgentEngine

    logger.info(f"CLI mode — executing goal: {goal}")

    config = Config()
    cfg = config.load()
    if dry_run:
        cfg["dry_run"] = True
        logger.info("DRY-RUN mode: state-changing actions will be logged, not executed")
    if autonomous:
        cfg["autonomous"] = True
        logger.info("AUTONOMOUS mode: no approval prompts")
    engine = AgentEngine(cfg)

    result = engine.run(goal)

    print(f"\n{'=' * 60}")
    print(f"Goal: {goal}")
    print(f"Steps: {result.get('steps', 0)}")
    print(f"Notes: {len(result.get('notes', []))}")
    if result.get("finish_summary"):
        print(f"\nSummary:\n{result['finish_summary']}")
    print(f"{'=' * 60}")


def main() -> None:
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.api:
        run_api(host=args.host, port=args.port)
    elif args.command:
        run_cli(args.command, dry_run=args.dry_run, autonomous=args.autonomous)
    else:
        # Surface CLI flags to config so the GUI picks them up this session.
        if args.dry_run or args.autonomous:
            from config import Config

            cfg = Config()
            data = cfg.load()
            if args.dry_run:
                data["dry_run"] = True
                logger.info("DRY-RUN mode enabled for this session")
            if args.autonomous:
                data["autonomous"] = True
                logger.info("AUTONOMOUS mode enabled for this session")
            cfg.save(data)
        run_gui()


if __name__ == "__main__":
    main()
