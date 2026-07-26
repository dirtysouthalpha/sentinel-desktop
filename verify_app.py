#!/usr/bin/env python3
"""Quick verification that Sentinel Desktop can launch.

Checks that every critical subsystem imports cleanly. Safe to run headless
(CI/servers): GUI and desktop-input imports degrade to a warning when no
display is available instead of failing the whole check.
"""

import os
import sys
import traceback

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

failures: list[str] = []

print("Testing imports...")

try:
    from core import __version__
    print(f"✓ Core package loaded (version {__version__})")
except Exception as exc:
    traceback.print_exc()
    print(f"\n❌ Core package failed to import: {exc}")
    sys.exit(1)

try:
    from core.llm_client import LLMClient  # noqa: F401
    print("✓ LLMClient importable")
except Exception as exc:
    failures.append(f"core.llm_client: {exc}")
    traceback.print_exc()

# ActionExecutor and the GUI pull in pyautogui/tkinter, which need a
# display on Linux/macOS. Skip them (with a warning) when headless.
_headless = sys.platform != "win32" and not os.environ.get("DISPLAY")
if _headless:
    print("⚠ ActionExecutor/GUI checks skipped (headless: no DISPLAY)")
else:
    try:
        from core.action_executor import ActionExecutor  # noqa: F401
        print("✓ ActionExecutor importable")
    except Exception as exc:
        failures.append(f"core.action_executor: {exc}")
        traceback.print_exc()

    try:
        from gui.app import SentinelApp  # noqa: F401
        print("✓ GUI app importable")
    except Exception as exc:
        failures.append(f"gui.app: {exc}")
        traceback.print_exc()

try:
    from api.server import SentinelServer  # noqa: F401
    print("✓ API server importable")
except Exception as exc:
    failures.append(f"api.server: {exc}")
    traceback.print_exc()

try:
    from core.engine import AgentEngine  # noqa: F401
    print("✓ AgentEngine importable")
except Exception as exc:
    failures.append(f"core.engine: {exc}")
    traceback.print_exc()

if failures:
    print(f"\n❌ {len(failures)} import(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print("\n✅ All critical modules import successfully")
print(f"Sentinel Desktop v{__version__} appears to be functional")
sys.exit(0)
