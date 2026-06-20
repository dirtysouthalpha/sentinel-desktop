#!/bin/bash
# Restart wrapper around grind-phase.sh — the continuous-run equivalent of the
# old grind-loop.sh. Runs one phase per grind-phase.sh invocation, sleeps, repeats.
#
# Launch it the same way you launched grind-loop.sh (open terminal, tmux, or nohup).
# To stop: Ctrl-C, or `pkill -f run-grind-phase.sh`.
#
# Swap from the old loop:
#   pkill -f "grind-loop.sh"        # stop the old one
#   nohup ./run-grind-phase.sh >/dev/null 2>&1 &   # start the new one (background)
#   # or in a dedicated terminal:    ./run-grind-phase.sh

set -u
cd "$(dirname "$0")"

# Drop a marker so it's easy to find/stop later.
echo "[$(date)] run-grind-phase.sh starting (PID $$)" >&2

while true; do
    ./grind-phase.sh
    rc=$?
    echo "[$(date)] grind-phase.sh exited (rc=$rc); sleeping 60s before next phase." >&2
    sleep 60
done
