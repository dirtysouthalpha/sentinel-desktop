---
name: v22-quality-gates
description: Quality gate status for v22.0 "Aria" production release
metadata:
  type: project
---

# v22.0 "Aria" Quality Gates

**Status**: ✅ ALL PASSED (verified 2026-07-11)

## Test Suite
- **Passing**: 9,159 tests
- **Skipped**: 153 tests (platform-specific, optional deps)
- **Failed**: 0 tests
- **Command**: `python -m pytest tests/ -q --timeout=10`

## Lint Check
- **Status**: Zero errors
- **Command**: `ruff check core/ gui/ api/`
- **Result**: Clean across all code packages

## Deliverables (v22.0 Features)
- ✅ `core/voice.py` — VoiceEngine with IDLE/LISTENING/SPEAKING/AMBIENT state machine
- ✅ `core/triggers.py` — EventType enum, Trigger dataclass, TriggerRegistry, TriggerEngine
- ✅ 9 new executor actions (trigger_*, voice_*)
- ✅ 9 new tool schemas for LLM tool calling
- ✅ No new dependencies (reuses v17 `core/audio.py`)

## Release Readiness
- ✅ Version bumped to v22.0.2
- ✅ PyPI Trusted Publishing code changes committed (commit 5d4c5f6)
- ⏳ Awaiting manual PyPI Trusted Publishing configuration (Phase 3a)

## Historical Context
Previous version quality gates:
- v21.0: 8,581 passing tests
- v20.0: 8,411 passing tests
- v19.0: 8,393 passing tests
- v18.x: 8,000+ passing tests

## Verification Protocol
Run this command to verify gates:
```bash
# Test suite
.venv/bin/python -m pytest tests/ -q --timeout=10

# Lint check
.venv/bin/ruff check core/ gui/ api/
```

Expected results:
- Test exit code: 0 (all pass)
- Lint exit code: 0 (clean)

## See Also
- `current-project-status.md` — overall project state
- `grind-backlog-priority.md` — current work priorities
