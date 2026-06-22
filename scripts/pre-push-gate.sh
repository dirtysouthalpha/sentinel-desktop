#!/bin/bash
# pre-push gate for Sentinel Desktop.
#
# Blocks pushes to main when ruff fails OR a test file fails to import.
# Fast (~10s). Gates main only; other refs push freely.
# Override (emergencies only): SKIP_GATE=1 git push
#
# Installed as .git/hooks/pre-push (symlink to this file). git invokes pre-push
# on every `git push` regardless of caller, so both the grind loop's pushes and
# a human's pushes pass through this gate.
#
# Fails closed: on any internal error it blocks the push. A broken trunk is
# recoverable; a silently-pushed broken trunk propagates.

set -u

# git passes lines of "<local ref> <local sha> <remote ref> <remote sha>" on stdin,
# one per ref being pushed. We inspect the first line for the remote ref name.
read -r LOCAL_REF LOCAL_SHA REMOTE_REF REMOTE_SHA

# Only gate pushes to main. Feature branches push freely.
case "$REMOTE_REF" in
    refs/heads/main) ;;
    *) exit 0 ;;
esac

# Explicit override for emergencies. The grind loop never sets this — only a human.
if [ "${SKIP_GATE:-0}" = "1" ]; then
    echo "[gate] SKIP_GATE=1 set — allowing push to main without checks." >&2
    exit 0
fi

# Run from the repo root so the .venv + paths resolve regardless of cwd.
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "[gate] BLOCKED — could not resolve repo root." >&2
    exit 1
}

# Prefer the project venv bins; fall back to PATH for environments without one.
PY=.venv/bin/python
RUFF=.venv/bin/ruff
[ -x "$PY" ]   || PY="$(command -v python3 || echo python)"
[ -x "$RUFF" ] || RUFF="$(command -v ruff || echo ruff)"

fail() {
    echo "[gate] BLOCKED — push to main rejected." >&2
    echo "[gate] Fix the failures above, then retry." >&2
    echo "[gate] Emergency override: SKIP_GATE=1 git push" >&2
    exit 1
}

echo "[gate] ruff check core/ gui/ api/ ..." >&2
"$RUFF" check core/ gui/ api/ || fail

echo "[gate] import smoke (pytest --collect-only) ..." >&2
# Use pytest collection rather than bare importlib: pytest loads conftest.py,
# which installs the headless X11/tkinter stubs. A bare import would try to
# connect to a display on headless hosts and false-positive on every push.
# This catches the regression class we care about (broken imports/signatures
# surface as collection errors) while respecting the test env's stubs.
#
# Isolate the inner pytest's basetemp (--basetemp=.pytest_tmp-gate) so it
# cannot collide with a concurrently-running outer pytest that owns
# .pytest_tmp. Without this, the inner pytest's tmp_path factory races the
# outer one on the shared basetemp directory, surfacing as sporadic
# FileNotFoundError at setup for unrelated tests.
"$PY" -m pytest tests/ --collect-only -q -p no:cacheprovider --basetemp=.pytest_tmp-gate >/dev/null 2>&1
collect_rc=$?
if [ "$collect_rc" -ne 0 ]; then
    echo "[gate] test collection failed (broken import/signature). Re-run for detail:" >&2
    echo "[gate]   .venv/bin/python -m pytest tests/ --collect-only -q" >&2
    "$PY" -m pytest tests/ --collect-only -q -p no:cacheprovider --basetemp=.pytest_tmp-gate 2>&1 | tail -15 >&2
    fail
fi

echo "[gate] green — push to main allowed." >&2
exit 0
