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
import json
import logging
import os
import sys
from argparse import Namespace
from pathlib import Path

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
PROJECT_ROOT = str(Path(__file__).resolve().parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def parse_args() -> Namespace:
    """Parse command-line arguments for the Sentinel Desktop CLI."""
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
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Path to a Sentinel profile directory to adopt on startup",
    )
    return parser.parse_args()


def _save_api_key(key: str, config_file: Path) -> None:
    """Write *key* into *config_file* JSON, preserving all other keys."""
    data: dict = {}
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    data["api_key"] = key
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _prompt_api_key(*, is_gui: bool) -> str | None:
    """Return an API key entered by the user, or None if skipped."""
    if is_gui:
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            key = simpledialog.askstring(
                "Sentinel Desktop — First Run",
                "Enter your LLM API key (e.g. sk-...):\n\n"
                "This will be saved to portable_data/config.json.",
                parent=root,
            )
            root.destroy()
            return key.strip() if key else None
        except Exception as exc:
            logger.warning("GUI API key prompt failed (%s) — falling back to CLI input", exc)
    try:
        key = input("Enter your LLM API key (or press Enter to skip): ").strip()
        return key or None
    except (EOFError, KeyboardInterrupt):
        return None


def _portable_startup(args: Namespace) -> None:
    """Detect and adopt a profile when running in portable mode.

    On first run, if the adopted profile has ``secrets_redacted=True`` and no
    API key is stored, prompt the user for one and save it to
    ``portable_data/config.json``.  In API/headless mode, the key can be
    supplied via the ``SENTINEL_API_KEY`` environment variable instead.
    """
    from core.paths import data_dir, is_portable

    if not is_portable():
        return

    from core.profile import adopt_profile, detect_profile, needs_api_key

    profile = detect_profile(cli_arg=getattr(args, "profile", None))
    if profile is None or not profile.flags.auto_adopt:
        return

    target = data_dir()
    adopt_profile(profile, target_dir=target)
    logger.info("Profile '%s' adopted into %s", profile.name, target)

    config_file = target / "config.json"
    config_data: dict = {}
    if config_file.exists():
        try:
            config_data = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    if not needs_api_key(profile, config_data):
        return

    # Headless mode: check env var, log a warning if missing.
    if getattr(args, "api", False):
        api_key = os.environ.get("SENTINEL_API_KEY", "").strip()
        if api_key:
            _save_api_key(api_key, config_file)
            logger.info("API key loaded from SENTINEL_API_KEY env var and saved.")
        else:
            logger.warning(
                "Profile '%s' has secrets_redacted=True and no API key is configured. "
                "Set the SENTINEL_API_KEY environment variable before starting the server.",
                profile.name,
            )
        return

    # GUI / CLI mode: prompt interactively.
    is_gui = not getattr(args, "command", None)
    api_key = _prompt_api_key(is_gui=is_gui)
    if api_key:
        _save_api_key(api_key, config_file)
        logger.info("API key saved to %s", config_file)
    else:
        logger.warning(
            "No API key entered — Sentinel will not be able to call the LLM until one is set."
        )


def run_gui() -> None:
    """Launch the CustomTkinter GUI."""
    try:
        import customtkinter as ctk  # noqa: F401
    except ImportError:
        logger.exception("customtkinter not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    from config import Config
    from gui.app import SentinelApp

    logger.info("Starting Sentinel Desktop in GUI mode")
    try:
        config = Config()
        config.load()
    except (OSError, ValueError) as exc:
        logger.warning("Config load failed (%s) — proceeding with defaults", exc)
        config = Config()
    app = SentinelApp(config)
    app.run()


def run_api(host: str = "0.0.0.0", port: int = 8091) -> None:
    """Launch the FastAPI server."""
    try:
        import uvicorn
    except ImportError:
        logger.exception("uvicorn not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    from api.server import SentinelServer
    from config import Config

    try:
        config = Config()
        config.load()
    except (OSError, ValueError) as exc:
        logger.warning("Config load failed (%s) — proceeding with defaults", exc)
        config = Config()
    server = SentinelServer(config)
    app = server.create_app()

    logger.info(f"Starting Sentinel Desktop in API mode on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_cli(goal: str, dry_run: bool = False, autonomous: bool = False) -> None:
    """Execute a single goal and exit."""
    from config import Config
    from core.engine import AgentEngine

    logger.info("CLI mode — executing goal: %s", goal)

    try:
        config = Config()
        cfg = config.load()
    except (OSError, ValueError) as exc:
        logger.warning("Config load failed (%s) — proceeding with defaults", exc)
        cfg: dict[str, object] = {}
    if dry_run:
        cfg["dry_run"] = True
        logger.info("DRY-RUN mode: state-changing actions will be logged, not executed")
    if autonomous:
        cfg["autonomous"] = True
        logger.info("AUTONOMOUS mode: no approval prompts")
    try:
        engine = AgentEngine(cfg)
        result = engine.run(goal)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("Engine execution failed: %s", exc)
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"Goal: {goal}")
    print(f"Steps: {result.get('steps', 0)}")
    print(f"Notes: {len(result.get('notes', []))}")
    if result.get("finish_summary"):
        print(f"\nSummary:\n{result['finish_summary']}")
    print(f"{'=' * 60}")


def main() -> None:
    """Main entry point — parse args and dispatch to API or CLI mode."""
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    _portable_startup(args)

    if args.api:
        run_api(host=args.host, port=args.port)
    elif args.command:
        run_cli(args.command, dry_run=args.dry_run, autonomous=args.autonomous)
    else:
        # Surface CLI flags to config so the GUI picks them up this session.
        if args.dry_run or args.autonomous:
            from config import Config

            try:
                cfg = Config()
                data = cfg.load()
            except (OSError, ValueError) as exc:
                logger.warning("Config load failed (%s) — using defaults", exc)
                cfg = Config()
                data = cfg.as_dict()
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
