#!/usr/bin/env python3
"""Quick verification that Sentinel Desktop v3.1.0 can launch."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    print("Testing imports...")
    from core import __version__

    print(f"✓ Core package loaded (version {__version__})")

    # Each import below is the probe — if the module fails to import, the
    # except block reports it. noqa: F401 because the side effect (a working
    # import) is the point, not the name binding.
    from core.llm_client import LLMClient  # noqa: F401

    print("✓ LLMClient importable")

    from core.action_executor import ActionExecutor  # noqa: F401

    print("✓ ActionExecutor importable")

    from gui.app import SentinelApp  # noqa: F401

    print("✓ GUI app importable")

    from api.server import SentinelServer  # noqa: F401

    print("✓ API server importable")

    print("\n✅ All critical modules import successfully")
    print("Sentinel Desktop v3.1.0 appears to be functional")
    sys.exit(0)

except Exception as e:
    print(f"\n❌ Import failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
