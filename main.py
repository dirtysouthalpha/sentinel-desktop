"""
Sentinel Desktop v2.0 - Entry Point
AI-powered Windows desktop automation assistant.

Usage:
    python main.py          # Launch GUI
    python main.py --cli    # CLI mode
    python main.py --version
"""
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Sentinel Desktop v2.0")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    parser.add_argument("--version", action="store_true", help="Show version")
    args = parser.parse_args()

    if args.version:
        from src.config import VERSION, APP_NAME
        print(f"{APP_NAME} v{VERSION}")
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
