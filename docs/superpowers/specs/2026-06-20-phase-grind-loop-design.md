# Design Spec — File-Driven Phase-by-Phase Grind Loop (Sentinel Desktop)

**Status:** Design + ready to implement.
**Date:** 2026-06-20
**Author:** ZCode (design) / Brandon (product)
**Replaces:** `grind-loop.sh` (re-reading CLAUDE.md each cycle).
**Deploys to:** `~/Projects/sentinel-desktop/` (where the loop runs) — authored/tested in this repo.

---

## Overview

Replace the current grind loop with one driven by a **curated backlog file**. The
old loop re-reads `CLAUDE.md` every cycle; since CLAUDE.md says "all priorities
complete," the loop either spins or invents work and collides with interactive
sessions (it independently rebuilt the Neuralis Brain bridge overnight while a
human-driven session was building the same thing — pure duplicate effort).

The new loop reads **one phase** from `GRIND-BACKLOG.md`, does exactly that phase,
verifies gates green, commits, pushes, and **stops**. It can only do work that has
been written down, and only one phase per session. This gives a human steering
authority while keeping full autonomy within a bounded task.

This spec also covers the **pre-push gate** (a git hook that blocks pushes to
`main` when ruff or import-smoke fails) — the brake that prevents a broken trunk
from being published while the loop runs.

### Decisions already made (do not re-litigate)

- **Backlog source:** a hand-curated `GRIND-BACKLOG.md` at the repo root. The loop
  does NOT auto-discover specs or invent work. A human (or a prior phase) writes
  phases; the loop consumes them.
- **Cadence:** one phase per session, then stop. Restarting picks up the next
  phase. No chaining inside a single session — each phase gets a clean context.
- **Pre-push gate:** `ruff check` + import-smoke of every test file. Fast (~10s),
  catches the regression class actually observed (broken imports/signatures from
  refactors). Gates pushes to `main` only; feature branches push freely. The
  existing `grind-loop.sh` loop stays running — the gate self-heals the trunk.
- **"Done" definition:** the phase's linked spec deliverables exist + `ruff check`
  clean + `pytest` exit 0 + committed + pushed. The loop ticks `[x]` and records
  the commit SHA only after all five hold.
- **Agent:** reuses the current loop's `claude -p` invocation, env routing
  (`z.ai` GLM-4.6), and `--allowedTools Read,Write,Edit,Bash`. No model change.
- **No new pip dependencies.** Pure shell + python (stdlib only for the gate).

---

## Components

### 1. `GRIND-BACKLOG.md` (repo root)

The single source of truth. The loop reads this; nothing else steers it.

```markdown
# Grind Backlog

Worked top-down by grind-phase.sh. Mark a phase [x] ONLY when done, gates green,
and pushed. The loop does the topmost [ ] phase under ## Active, then STOPS —
one phase per session.

Format:  - [ ] Phase N: <title> — see `docs/superpowers/specs/<spec>.md`
         - [x] Phase N: <title> (commit <short-sha>)

## Active
- [ ] Phase 1: <first real task> — see `docs/.../<spec>.md`
- [ ] Phase 2: <second task>

## Blocked
<!-- move a phase here with a [BLOCKED: reason] note if it can't proceed -->

## Done
- [x] Phase 0: <previous shipped work> (commit a1b2c3d)
```

Seeded (see *Initial backlog* below) with the genuinely-remaining work: design the
stealth tier, cut the v22.0.0 tag, etc.

### 2. `grind-phase.sh` (repo root, replaces `grind-loop.sh`)

```bash
#!/bin/bash
# File-driven phase-by-phase grind loop. One phase per session, then stop.
set -u
cd "$(dirname "$0")"
mkdir -p ~/grind-logs
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG=~/grind-logs/phase-${TIMESTAMP}.log

if [ ! -f .venv/bin/python ]; then
    echo "[$(date)] ERROR: .venv not found." | tee -a "$LOG"; exit 1
fi
.venv/bin/pip install -q pytest pytest-timeout ruff 2>/dev/null

# Pull latest (picks up a human's just-edited backlog, and prior phase's tick).
git pull origin main 2>&1 | tee -a "$LOG"

# >>> GLM grind-loop routing (fleet hybrid policy) >>>
export ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
export ANTHROPIC_AUTH_TOKEN=bf6ef726dad74aa1aea51b8d349b0dbe.kHIqQR8LOwS82l8y
export ANTHROPIC_MODEL=glm-4.6
export ANTHROPIC_SMALL_FAST_MODEL=glm-4.5-air
unset ANTHROPIC_CUSTOM_HEADERS
# <<< GLM grind-loop routing <<<

claude -p "$(cat <<'PROMPT'
You are the Sentinel Desktop phase grind agent. Work in the current repo. Use
.venv/bin/python and .venv/bin/ruff for all commands.

STEP 1 — Read GRIND-BACKLOG.md. Find the FIRST line matching "- [ ] Phase N:"
under "## Active" (the topmost unchecked phase). That is your ONLY task.
Read the spec file it links to, FULLY, before writing any code.

STEP 2 — Implement that one phase only. After EVERY change run:
  ruff check core/ gui/ api/   AND   .venv/bin/python -m pytest tests/ -q --tb=short
Both must be green before you commit. Never break existing tests.

STEP 3 — When the phase is done (deliverables exist + ruff clean + pytest exit 0
+ committed + pushed): edit GRIND-BACKLOG.md — move that line from ## Active to
## Done, tick it [x], and append the commit short SHA: "(commit abc1234)".
Commit + push that backlog edit too.

STEP 4 — STOP. Do NOT start the next phase. One phase per session.

RULES:
- If ## Active has no [ ] phase: run a maintenance pass — verify ruff + pytest
  are green, fix any newly-failing tests, commit+push, then STOP. Never invent
  new features or edit CLAUDE.md's feature claims.
- If the phase is blocked (a dependency is offline, a spec contradicts reality):
  move it to ## Blocked with "- [BLOCKED: <one-line reason>]", commit, push, STOP.
- Never force-push. If a push is rejected, pull --rebase and retry once.
- Safety: never touch the approval gate or the Esc-x3 failsafe.
- Use git commit, not git commit --amend, so history is auditable.
PROMPT
)" \
    --allowedTools Read,Write,Edit,Bash \
    --dangerously-skip-permissions \
    --max-turns 300 \
    --model claude-sonnet-4-6 \
    2>&1 | tee -a "$LOG"

# Post-session verify + push any leftovers (the gate blocks red pushes).
echo "[$(date)] Post-session verify..." | tee -a "$LOG"
.venv/bin/ruff check core/ gui/ api/ >>"$LOG" 2>&1
.venv/bin/python -m pytest tests/ -q --tb=line -p no:cacheprovider >>"$LOG" 2>&1
echo "[$(date)] pytest exit: $?" | tee -a "$LOG"
git push origin main 2>&1 | tee -a "$LOG"

cd ~/grind-logs && ls -t phase-*.log 2>/dev/null | tail -n +11 | xargs -r rm
```

The outer wrapper (restart-on-exit) is a one-liner the operator runs:
`while true; do ./grind-phase.sh; echo "[$(date)] sleeping 60s"; sleep 60; done`
— or keep the existing `grind-loop.sh` running and just swap which script it calls.
Decoupling the per-session script from the restart wrapper lets a human run a
single phase by hand (`./grind-phase.sh`) without the restart loop.

### 3. `scripts/pre-push-gate.sh` + `.git/hooks/pre-push`

The brake. A git `pre-push` hook is invoked by git on every `git push`, regardless
of what called git — so the loop's `git push origin main` and a human's push both
pass through it.

```bash
#!/bin/bash
# pre-push gate: block pushes to main when ruff fails OR test files don't import.
# Fast (~10s). Gates main only; other refs push freely. Override: SKIP_GATE=1 git push.
set -u
REMOTE_REF="$3"   # local ref being pushed; $2 is remote ref. See githooks(5).
# git passes: <local ref> <local sha> <remote ref> <remote sha> per line on stdin.
# We read the first line to get the remote ref name.
read -r LOCAL_REF LOCAL_SHA REMOTE_REF REMOTE_SHA

# Only gate pushes to main.
case "$REMOTE_REF" in
    refs/heads/main) ;;
    *) exit 0 ;;
esac

if [ "${SKIP_GATE:-0}" = "1" ]; then
    echo "[gate] SKIP_GATE=1, allowing push." >&2; exit 0
fi

cd "$(git rev-parse --show-toplevel)" || exit 1
PY=.venv/bin/python
RUFF=.venv/bin/ruff
[ -x "$PY" ]   || PY=python3
[ -x "$RUFF" ] || RUFF=ruff

fail() { echo "[gate] BLOCKED — push to main rejected." >&2
         echo "[gate] Fix the above, or retry with SKIP_GATE=1 git push (emergencies only)." >&2
         exit 1; }

echo "[gate] ruff check..." >&2
"$RUFF" check core/ gui/ api/ || fail

echo "[gate] import smoke (collecting test files)..." >&2
"$PY" - <<'PY' || fail
import importlib, pathlib, sys, traceback
root = pathlib.Path("tests")
errors = []
for f in root.rglob("test_*.py"):
    mod = ".".join(f.with_suffix("").parts)
    try:
        importlib.import_module(mod)
    except Exception as e:
        errors.append(f"{mod}: {type(e).__name__}: {e}")
if errors:
    for e in errors[:20]:
        print("  IMPORT FAIL:", e, file=sys.stderr)
    print(f"  ({len(errors)} test file(s) failed to import)", file=sys.stderr)
    sys.exit(1)
PY

echo "[gate] green — push to main allowed." >&2
exit 0
```

Install (one-time, per clone):
```bash
mkdir -p scripts
cp <spec's script> scripts/pre-push-gate.sh
chmod +x scripts/pre-push-gate.sh
ln -sf ../../scripts/pre-push-gate.sh .git/hooks/pre-push
```

The symlink (not a copy) means edits to `scripts/pre-push-gate.sh` take effect
without reinstalling the hook. `.git/hooks/` isn't version-controlled, so the
script source lives in `scripts/` (tracked) and the hook is a symlink to it.

**Override:** `SKIP_GATE=1 git push` for genuine emergencies (e.g. pushing a hotfix
to a partially-broken state deliberately). The loop never sets this — only a human.

### 4. Initial `GRIND-BACKLOG.md` seed

Genuinely-remaining work (verified 2026-06-20 — NOT duplicate of shipped v18-v22):

```markdown
## Active
- [ ] Phase 1: Cut v22.0.0 release tag — push tag, confirm release.yml runs,
      verify PyPI/GitHub Release succeeds. See RELEASING.md.
- [ ] Phase 2: Design the deferred fully-stealth humanization tier — write a
      spec to docs/superpowers/specs/ covering biometric typing, Fitts's-Law
      targeting, overshoot+correction, error injection. See
      docs/superpowers/notes/future-stealth-mode.md.
- [ ] Phase 3: Wire Sentinel Desktop into the avatar/companion app vision
      (browser-first → desktop) per the long-term goal in the Neuralis brain.

## Done
- [x] Phase 0: v18-v22 shipped, red suite repaired (commit 1e48802)
```

(Phase 1 is the release tag the user asked for; Phases 2-3 are the real next
plateaus. A human can reorder/add phases freely.)

---

## Data flow

**Per session (restart loop fires `grind-phase.sh`):**
1. `git pull` — picks up the latest backlog (human edits, prior phase's tick).
2. Agent reads `GRIND-BACKLOG.md`, finds the topmost `[ ]` phase, reads its spec.
3. Agent implements that one phase, running ruff + pytest after each change.
4. Agent commits + pushes. **The pre-push gate runs** — if ruff/import-smoke
   fails, the push is blocked with a message; the agent reads it and self-corrects.
5. On green push: agent ticks the phase `[x]`, moves it to `## Done`, commits+pushes
   that edit, and **stops**.
6. Restart loop sleeps 60s, fires again → next phase.

**Maintenance pass (when `## Active` is empty):**
1. Agent verifies ruff + pytest green.
2. If anything's red, fixes it, commits, pushes.
3. Stops. Never invents features.

**Blocked phase:**
1. Agent moves the phase to `## Blocked` with `[BLOCKED: reason]`, commits, pushes.
2. Stops. A human triages `## Blocked`.

---

## Error handling & graceful degradation

| Situation | Behavior |
|-----------|----------|
| `git push` rejected by gate (ruff/import fail) | Push aborted. Agent sees the gate's stderr, fixes the cause, retries. |
| `git push` rejected (non-fast-forward) | Agent does `git pull --rebase`, retries once. If still rejected, notes it in the log and stops (avoiding a force-push war with a concurrent session). |
| Phase spec missing or contradicts shipped code | Agent moves phase to `## Blocked` with reason, stops. Doesn't guess. |
| `## Active` empty | Maintenance pass (verify gates, fix reds), then stop. |
| Agent exceeds `--max-turns` mid-phase | Post-session push fires; next session resumes the same phase (it's still `[ ]`). |
| Gate's import-smoke itself crashes (env broken) | Gate fails closed (blocks). Human runs `SKIP_GATE=1 git push` to recover, then fixes the env. |
| Concurrent human session edits the same files | The pull --rebase surfaces the conflict; agent is instructed to resolve cleanly or stop. The one-phase-per-session rule minimizes the overlap window. |

The gate **fails closed**: on any internal error it blocks the push. A broken
trunk is recoverable; a silently-pushed broken trunk propagates to CI, the loop's
next pull, and any other clone. Closed is the safe default.

---

## Testing plan

**`scripts/pre-push-gate.sh`** — exercised via `tests/test_pre_push_gate.py` (shell
test driven by pytest, no live git push needed):
- `test_gate_allows_when_green` — in a temp repo with clean ruff + importable tests,
  run the gate; assert exit 0.
- `test_gate_blocks_on_ruff_failure` — drop a lint error into a tracked file;
  assert exit non-zero + "BLOCKED" on stderr.
- `test_gate_blocks_on_import_failure` — add a test file that raises at import;
  assert exit non-zero.
- `test_gate_skips_for_non_main_ref` — `REMOTE_REF=refs/heads/feature/x` → exit 0
  even with a lint error present.
- `test_gate_respects_skip_env` — `SKIP_GATE=1` → exit 0 regardless.
- `test_gate_uses_venv_bins` — asserts it prefers `.venv/bin/ruff` when present.

**`grind-phase.sh`** — not unit-tested (it's a thin wrapper over `claude -p`); a
`scripts/test-backlog-parser.sh` smoke test verifies the backlog-reading contract:
given a sample `GRIND-BACKLOG.md`, `grep`/`awk` extracts the correct topmost
unchecked phase line. This catches drift if the format changes.

**Manual (operator runbook, documented in the spec, not automated):**
- First run: `./grind-phase.sh` with a seeded backlog → confirm it does Phase 1 only.
- Force a lint error, `git push` → confirm gate blocks.
- `SKIP_GATE=1 git push` → confirm override works.

---

## Deployment notes

- **Two clones:** this repo is authored/tested at
  `/home/dad/Downloads/sentinel-desktop`; the running loop lives at
  `~/Projects/sentinel-desktop`. After committing the new files here, the operator
  pulls in the loop's clone, installs the pre-push hook there, and swaps the
  restart wrapper to call `grind-phase.sh` instead of `grind-loop.sh`. `grind-loop.sh`
  is kept (not deleted) as a fallback.
- **The hook must be installed per-clone** (`.git/hooks/` isn't shared). Both the
  interactive clone and the loop's clone need it for the gate to hold everywhere.
- **The current running `grind-loop.sh` processes** (PID 78204, 78205) should be
  left running until the operator swaps to `grind-phase.sh`, to avoid a gap.

---

## Open questions (operator decisions, not blocking implementation)

1. **Restart wrapper:** keep the existing restart-on-exit loop, or run
   `grind-phase.sh` under `systemd`/a supervisor? Proposal: keep the bash restart
   loop for now (matches current behavior); supervisor is a later ops task.
2. **Backlog edit authority:** should the agent be allowed to *prepend* a newly-
   discovered phase to `## Active` while working (hybrid autonomy), or only ever
   *consume* phases a human wrote? Proposal: consume-only for v1; add prepend-permission
   later if the curated backlog runs dry. (Default is the safer consume-only.)
3. **Notification on block:** when a phase moves to `## Blocked`, notify the
   operator (Discord/Telegram, both already wired in the fleet)? Proposal: yes,
   via the existing sentinel notify MCP tool — but as a follow-up, not v1.

---

## Out of scope (this phase)

- **Switching the loop to PR-based flow** — explicitly declined; direct-to-main
  with a pre-push gate is the chosen model.
- **Full-suite runs in the gate** — too slow/flaky; CI already does this.
- **Auto-discovery of specs as phases** — rejected; curated backlog only.
- **Rewriting `grind-loop.sh`'s model/env routing** — reused as-is.
- **Supervisor/systemd migration** — later ops task.

---

## Recommended build order

1. `scripts/pre-push-gate.sh` + `tests/test_pre_push_gate.py` — verify the gate
   blocks/passes correctly in isolation. (Do this first — it's the safety net for
   everything after.)
2. Install the hook symlink in this clone; verify it blocks a deliberately-broken
   push and allows a green one.
3. `GRIND-BACKLOG.md` seed (3 phases above).
4. `grind-phase.sh`.
5. `scripts/test-backlog-parser.sh` smoke test.
6. Operator runbook section: deploy to `~/Projects/sentinel-desktop`, swap the
   restart wrapper, install the hook there.
7. Phase 1 of the backlog (the v22.0.0 tag) is the first real work the new loop
   (or a human) does once this lands.
