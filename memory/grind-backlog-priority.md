---
name: grind-backlog-priority
description: The GRIND-BACKLOG.md file is the real priority queue for Sentinel Desktop work
metadata:
  type: reference
---

# GRIND-BACKLOG.md Priority Protocol

## How It Works
The `grind-phase.sh` autonomous loop works top-down through `GRIND-BACKLOG.md`:
- Executes the topmost `[ ]` phase under **## Active**
- Does ONE phase per session (stops after completion)
- Each restart picks up the next phase with clean context
- Never invents work — if **## Active** is empty, runs maintenance pass only

## Current Status
**Active Phase**: Phase 3a — PyPI Trusted Publishing configuration
- **Status**: `[ ]` (awaiting manual user action on PyPI website)
- **Blocker**: User must manually configure Trusted Publishing on PyPI
- **Reference**: `docs/PYPI_TRUSTED_PUBLISHING_SETUP.md`

**Blocked Phases**: Phase 3b (blocked until Phase 3a complete)

**Done Phases**: All phases 0, 1, 2, 4-12 marked `[x]`

## Rules
- Mark phase `[x]` ONLY when: deliverables exist + ruff clean + pytest exit 0 + committed + pushed
- Append commit SHA when complete: `(commit abc1234)`
- If blocked, move to **## Blocked** with `[BLOCKED: <reason>]`
- Human can reorder/add/edit phases freely at any time

## Maintenance Pass Protocol
When **## Active** is empty (or only contains manual-action items):
1. Verify all quality gates green (ruff + pytest)
2. Fix any newly-failing tests
3. Stop — do not invent new work

## See Also
- `GRIND-BACKLOG.md` — authoritative source
- `docs/PYPI_TRUSTED_PUBLISHING_SETUP.md` — Phase 3a instructions
- `grind-loop-protocol.md` — how the loop operates
