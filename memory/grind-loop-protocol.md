---
name: grind-loop-protocol
description: How the autonomous grind-phase.sh loop operates
metadata:
  type: project
---

# Grind Loop Protocol

## Overview
The `grind-phase.sh` script is the autonomous work loop for Sentinel Desktop. It systematically works through phases defined in `GRIND-BACKLOG.md`.

## How It Works
1. **Read GRIND-BACKLOG.md** — parses the file to find active phases
2. **Execute Top Phase** — runs the first `[ ]` phase under **## Active**
3. **Stop After One Phase** — completes exactly one phase per session
4. **Clean Context** — each restart picks up next phase with fresh context

## Phase Completion Criteria
A phase is marked `[x]` ONLY when ALL of:
- ✅ Deliverables exist (code/files created)
- ✅ `ruff check core/ gui/ api/` clean (zero errors)
- ✅ `pytest` exit 0 (all tests pass)
- ✅ Changes committed to git
- ✅ Changes pushed to remote (backup/main)
- ✅ Commit SHA appended: `(commit abc1234)`

## When Active is Empty
If **## Active** contains no automatable phases:
1. Run **maintenance pass** — verify gates green, fix newly-failing tests
2. **Stop** — do not invent new work
3. Wait for human to add new phases or unblock current work

## Blocked Phases
If a phase is blocked:
- Move to **## Blocked** section with `[BLOCKED: <reason>]`
- Commit and push the blocked state
- Human intervention required to unblock

## Current Repository Protocol
- **Primary remote**: `backup` (github.com/dirtysouthalpha/sentinel-desktop-grind)
- **Tracked branch**: `main` → `backup/main`
- **Public remote**: `origin` (github.com/DirtySouthAlpha/sentinel-desktop) — different project, DO NOT touch
- **Rules**: Never `git push origin main`, never `git pull --rebase`, never force-push origin

## Git Workflow
Use bare `git push` (goes to backup/main via tracked upstream):
```bash
git commit -m "message"
git push  # goes to backup/main automatically
```

## See Also
- `GRIND-BACKLOG.md` — authoritative source of truth
- `grind-backlog-priority.md` — current priorities
- `grind-loop-working-tree-race.md` — working tree sharing protocol
