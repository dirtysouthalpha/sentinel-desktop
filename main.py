"""
Sentinel Desktop v2.0 - Entry Point
AI-powered Windows desktop automation assistant.

Usage:
    python main.py          # Launch GUI
    python main.py --cli    # CLI mode
    python main.py --api    # Headless API server
    python main.py --version
"""
import argparse
import sys


def parse_args():
    """Parse command-line arguments. Exported for testing."""
    parser = argparse.ArgumentParser(description="Sentinel Desktop v2.0")
    parser.add_argument("--cli", "-c", nargs="?", const=True, default=False,
                        help="Run in CLI mode (optionally with command)")
    parser.add_argument("--api", action="store_true", help="Run headless API server")
    parser.add_argument("--host", default="0.0.0.0", help="API listen host")
    parser.add_argument("--port", type=int, default=8091, help="API listen port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no actions)")
    parser.add_argument("--autonomous", action="store_true", help="Autonomous mode")
    parser.add_argument("--version", action="store_true", help="Show version")
    args = parser.parse_args()
    # Convert -c with value into command string
    if isinstance(args.cli, str):
        args.command = args.cli
        args.cli = True
    else:
        args.command = None
    return args


def main():
    """Entry point for Sentinel Desktop."""
    args = parse_args()

    if args.version:
        from core import __version__
        print(f"Sentinel Desktop v{__version__}")
        return

    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    if args.api:
        import uvicorn

        from api.server import SentinelServer
        from config import Config
        config = Config()
        config.load()
        server = SentinelServer(config)
        app = server.create_app()
        uvicorn.run(app, host=args.host, port=args.port)
        return

    if args.cli:
        from src.cli import cli_main
        cli_main()
        return

    # GUI mode
    try:
        from src.ui.app import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"GUI dependencies missing: {e}")
        print("Install with: pip install customtkinter pyautogui psutil")
        sys.exit(1)


if __name__ == "__main__":
    main()
