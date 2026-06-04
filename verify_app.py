#!/usr/bin/env python3
"""Quick verification that Sentinel Desktop v3.1.0 can launch."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    print("Testing imports...")
    from core import __version__
    print(f"✓ Core package loaded (version {__version__})")

    from core.llm_client import LLMClient
    print("✓ LLMClient importable")

    from core.action_executor import ActionExecutor
    print("✓ ActionExecutor importable")

    from gui.app import SentinelDesktopApp
    print("✓ GUI app importable")

    from api.server import create_app
    print("✓ API server importable")

    print("\n✅ All critical modules import successfully")
    print("Sentinel Desktop v3.1.0 appears to be functional")
    sys.exit(0)

except Exception as e:
    print(f"\n❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
