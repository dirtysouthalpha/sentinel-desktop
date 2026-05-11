#!/usr/bin/env python3
"""
Sentinel Desktop v2 — AI-powered Windows desktop automation agent.

Modes:
  GUI  (default)     : CustomTkinter dark-themed chat interface
  API  (--api)       : FastAPI server on port 8091
  CLI  (--command)   : Single goal, execute, exit
"""

import argparse
import sys
import os
import logging

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


def parse_args():
    parser = argparse.ArgumentParser(
        prog="sentinel-desktop",
        description="Sentinel Desktop v2 — AI-powered Windows desktop automation",
    )
    parser.add_argument(
        "--api", action="store_true",
        help="Launch in headless API mode (FastAPI on port 8091)",
    )
    parser.add_argument(
        "--command", "-c", type=str, default=None,
        help="Execute a single goal in CLI mode and exit",
    )
    parser.add_argument(
        "--port", type=int, default=8091,
        help="Port for API server (default: 8091)",
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0",
        help="Host for API server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def run_gui():
    """Launch the CustomTkinter GUI."""
    try:
        import customtkinter as ctk
    except ImportError:
        logger.error("customtkinter not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    from config import Config
    from gui.app import SentinelApp

    logger.info("Starting Sentinel Desktop in GUI mode")
    config = Config()
    app = SentinelApp(config)
    app.run()


def run_api(host="0.0.0.0", port=8091):
    """Launch the FastAPI server."""
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    from config import Config
    from api.server import SentinelServer

    config = Config()
    server = SentinelServer(config)
    app = server.create_app()

    logger.info(f"Starting Sentinel Desktop in API mode on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_cli(goal: str):
    """Execute a single goal and exit."""
    from config import Config
    from core.engine import AgentEngine

    logger.info(f"CLI mode — executing goal: {goal}")

    config = Config()
    cfg = config.load()
    engine = AgentEngine(cfg)

    result = engine.run(goal)

    print(f"\n{'='*60}")
    print(f"Goal: {goal}")
    print(f"Steps: {result.get('steps', 0)}")
    print(f"Notes: {len(result.get('notes', []))}")
    if result.get("finish_summary"):
        print(f"\nSummary:\n{result['finish_summary']}")
    print(f"{'='*60}")


def main():
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.api:
        run_api(host=args.host, port=args.port)
    elif args.command:
        run_cli(args.command)
    else:
        run_gui()


if __name__ == "__main__":
    main()
