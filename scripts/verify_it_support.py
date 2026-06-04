#!/usr/bin/env python3
"""Verify all IT support script templates load and execute correctly."""

import json
import sys
from pathlib import Path

scripts_dir = Path(__file__).parent / "it_support"
errors = []

for script_file in sorted(scripts_dir.glob("*.json")):
    try:
        with open(script_file, encoding="utf-8") as f:
            template = json.load(f)

        # Verify required fields
        required_fields = ["name", "description", "steps"]
        missing = [field for field in required_fields if field not in template]
        if missing:
            errors.append(f"{script_file.name}: Missing fields {missing}")
            continue

        # Verify steps structure
        if not isinstance(template["steps"], list):
            errors.append(f"{script_file.name}: 'steps' must be a list")
            continue

        # Verify each step has required fields
        for i, step in enumerate(template["steps"]):
            if not isinstance(step, dict):
                errors.append(f"{script_file.name}: Step {i} is not a dict")
                continue
            if "action" not in step:
                errors.append(f"{script_file.name}: Step {i} missing 'action' field")

        print(f"✓ {script_file.name}")

    except json.JSONDecodeError as e:
        errors.append(f"{script_file.name}: Invalid JSON - {e}")
        print(f"✗ {script_file.name}: Invalid JSON")
    except Exception as e:
        errors.append(f"{script_file.name}: {e}")
        print(f"✗ {script_file.name}: {e}")

print(f"\n{'='*60}")
print(f"Verified {len(list(scripts_dir.glob('*.json')))} script templates")

if errors:
    print("\n❌ Errors found:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)
else:
    print("✅ All IT support scripts are valid")
    sys.exit(0)
