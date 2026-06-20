#!/bin/bash
# Smoke test for the GRIND-BACKLOG.md parsing contract that grind-phase.sh's
# agent prompt depends on. Confirms the "topmost unchecked phase under ## Active"
# extraction works, so a format drift is caught before the loop misfires.
#
# Run:  bash scripts/test-backlog-parser.sh

set -u
cd "$(dirname "$0")/.."

PASS=0
FAIL=0

assert_eq() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        echo "  ok: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc"
        echo "    expected: $expected"
        echo "    actual:   $actual"
        FAIL=$((FAIL + 1))
    fi
}

# Build a sample backlog in a temp file.
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

cat >"$TMP" <<'EOF'
# Grind Backlog

## Active

- [ ] Phase 1: first task — see docs/x.md
- [ ] Phase 2: second task
- [x] Phase 3: already done

## Blocked

- [ ] Phase 4: blocked one

## Done

- [x] Phase 0: old work (commit aaa)
EOF

echo "=== backlog-parser smoke test ==="

# Extract the ## Active section, then the first "- [ ] Phase" line within it.
# This mirrors the contract the loop's prompt assumes.
ACTIVE_SECTION=$(awk '/^## Active/{f=1; next} /^## /{f=0} f' "$TMP")
FIRST_UNCHECKED=$(echo "$ACTIVE_SECTION" | grep -m1 -E '^- \[ \] Phase [0-9]+:')

assert_eq "finds topmost unchecked phase" \
    "- [ ] Phase 1: first task — see docs/x.md" \
    "$FIRST_UNCHECKED"

# A fully-ticked Active section yields no unchecked phase → loop does maintenance.
ALL_DONE=$(mktemp)
cat >"$ALL_DONE" <<'EOF'
## Active

- [x] Phase 1: done
- [x] Phase 2: done

## Done
EOF
ACTIVE2=$(awk '/^## Active/{f=1; next} /^## /{f=0} f' "$ALL_DONE")
NONE=$(echo "$ACTIVE2" | grep -m1 -E '^- \[ \] Phase [0-9]+:' || true)
assert_eq "no unchecked phase → empty (triggers maintenance pass)" \
    "" "$NONE"
rm -f "$ALL_DONE"

# Blocked section must NOT be picked up as active work.
ACTIVE3=$(awk '/^## Active/{f=1; next} /^## /{f=0} f' "$TMP")
BLOCKED_LEAK=$(echo "$ACTIVE3" | grep -c "Phase 4" || true)
assert_eq "Blocked section not leaked into Active" "0" "$BLOCKED_LEAK"

echo ""
echo "=== results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
