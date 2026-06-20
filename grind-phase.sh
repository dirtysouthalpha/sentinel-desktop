#!/bin/bash
# File-driven phase-by-phase grind loop for Sentinel Desktop.
# Replaces grind-loop.sh's CLAUDE.md-reread model. One phase per session, then stop.
#
# Driven by GRIND-BACKLOG.md: reads the topmost unchecked phase under ## Active,
# does exactly that one phase, verifies gates, commits, pushes, ticks it done, stops.
#
# Wrap in a restart loop to run continuously:
#   while true; do ./grind-phase.sh; echo "[$(date)] sleeping 60s"; sleep 60; done
# Or run a single phase by hand:  ./grind-phase.sh
#
# The pre-push gate (.git/hooks/pre-push) blocks pushes to main when ruff or test
# collection fails — so a broken phase can't publish a red trunk.

set -u
cd "$(dirname "$0")"
mkdir -p ~/grind-logs
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG=~/grind-logs/phase-${TIMESTAMP}.log

echo "[$(date)] === grind-phase start ===" | tee -a "$LOG"

if [ ! -x .venv/bin/python ]; then
    echo "[$(date)] ERROR: .venv/bin/python not found. Run: python3 -m venv .venv && .venv/bin/pip install -e '.[all,dev]'" | tee -a "$LOG"
    exit 1
fi
.venv/bin/pip install -q pytest pytest-timeout ruff 2>/dev/null

if [ ! -f GRIND-BACKLOG.md ]; then
    echo "[$(date)] ERROR: GRIND-BACKLOG.md not found — nothing to work." | tee -a "$LOG"
    exit 1
fi

# Pull latest (picks up a human's just-edited backlog + prior phase's tick).
git pull origin main 2>&1 | tee -a "$LOG"

# >>> GLM grind-loop routing (fleet hybrid policy) — reused from grind-loop.sh >>>
export ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
export ANTHROPIC_AUTH_TOKEN=bf6ef726dad74aa1aea51b8d349b0dbe.kHIqQR8LOwS82l8y
export ANTHROPIC_MODEL=glm-4.6
export ANTHROPIC_SMALL_FAST_MODEL=glm-5-air
unset ANTHROPIC_CUSTOM_HEADERS
# <<< GLM grind-loop routing <<<

claude -p "$(cat <<'PROMPT'
You are the Sentinel Desktop phase grind agent. Work in the current repo. Use
.venv/bin/python and .venv/bin/ruff for ALL commands. Never use system python/ruff.

STEP 1 — Find your task. Read GRIND-BACKLOG.md. Find the FIRST line matching
"- [ ] Phase N:" under the "## Active" heading (the topmost unchecked phase).
That single phase is your ONLY task for this session. Read the spec file it links
to, FULLY, before writing any code. If "## Active" has NO unchecked phase, run a
maintenance pass (STEP 3b) instead.

STEP 2 — Implement that ONE phase. After EVERY change, run both and require green:
  .venv/bin/ruff check core/ gui/ api/
  .venv/bin/python -m pytest tests/ -q --tb=short --timeout=30
Never break existing tests. Commit focused changes with clear messages as you go.

STEP 3 — Finish the phase:
  3a. When the phase is DONE (deliverables exist + ruff clean + pytest exit 0 +
      committed + pushed): edit GRIND-BACKLOG.md — move that phase's line from
      "## Active" to "## Done", tick it "[x]", and append the short SHA:
      "(commit abc1234)". Commit that backlog edit and push it.
  3b. MAINTENANCE PASS (only if "## Active" had no unchecked phase): verify ruff +
      pytest are green. If anything is red, fix it, commit, push. Do NOT invent new
      features or edit CLAUDE.md's feature claims.
  3c. BLOCKED (only if the phase genuinely cannot proceed — a dependency is offline,
      a spec contradicts shipped reality): move the phase to "## Blocked" with
      "- [BLOCKED: <one-line reason>]", commit, push.

STEP 4 — STOP. Do NOT start the next phase. One phase per session. Period.

RULES:
- Push after every 1-3 commits (small focused commits). The pre-push gate blocks
  pushes to main if ruff or test collection fails — if your push is rejected, the
  gate's message tells you what's broken; FIX IT, then retry. Never force-push.
- If a push is rejected as non-fast-forward (someone else pushed first), run
  `git pull --rebase origin main` and retry once. If it still fails, stop and log it.
- Never add pip dependencies without a compelling reason.
- Safety is paramount: NEVER touch the approval gate or the Esc-x3 failsafe.
- Use `git commit` (not --amend) so history stays auditable.
- If you hit a wall, skip to STEP 3c (BLOCKED) — do not stall or spin.
PROMPT
)" \
    --allowedTools Read,Write,Edit,Bash \
    --dangerously-skip-permissions \
    --max-turns 300 \
    --model claude-sonnet-4-6 \
    2>&1 | tee -a "$LOG"

# Post-session verify + push any leftovers. The gate blocks red pushes; that's
# the safety net — if the agent left the suite red, this push is rejected and
# the next session's git pull surfaces the uncommitted state.
echo "[$(date)] Post-session gate check..." | tee -a "$LOG"
.venv/bin/ruff check core/ gui/ api/ >>"$LOG" 2>&1 && echo "[ruff ok]" >>"$LOG"
.venv/bin/python -m pytest tests/ -q --tb=line --timeout=30 -p no:cacheprovider >>"$LOG" 2>&1
echo "[$(date)] post-session pytest exit: $?" | tee -a "$LOG"
git push origin main 2>&1 | tee -a "$LOG"

echo "[$(date)] === grind-phase end ===" | tee -a "$LOG"

# Keep last 10 phase logs.
cd ~/grind-logs && ls -t phase-*.log 2>/dev/null | tail -n +11 | xargs -r rm
