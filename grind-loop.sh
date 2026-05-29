#!/bin/bash
cd ~/Projects/sentinel-desktop
mkdir -p ~/grind-logs

# Wait for deps to finish installing
echo "[$(date)] Waiting for pip install to finish..."
while ! source .venv/bin/activate && python -c "import customtkinter" 2>/dev/null; do
    echo "[$(date)] Deps not ready, waiting 30s..."
    sleep 30
done
echo "[$(date)] Deps ready!"

while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG=~/grind-logs/desktop-${TIMESTAMP}.log
    
    echo "[$(date)] Starting Sentinel Desktop PRODUCTION POLISH grind (Opus)..." | tee -a "$LOG"
    
    source .venv/bin/activate
    
    claude -p "Read CLAUDE.md. You are polishing Sentinel Desktop v3.0 — a massive Python desktop automation agent (234 files, 71K lines). Your priority: (1) Run the test suite and fix ALL failures, (2) Run ruff and fix ALL lint errors, (3) Improve test coverage for untested modules, (4) Complete any in-progress features (workflow builder API handlers, IT support scripts), (5) Edge case hardening for recovery/scheduler/LLM client, (6) Performance optimization, (7) Documentation gaps. Work through every item in CLAUDE.md systematically. After each fix, commit with conventional commit messages and push. Do NOT stop until everything passes clean." \
        --allowedTools Read,Write,Edit,Bash \
        --dangerously-skip-permissions \
        --max-turns 500 \
        --model opus \
        2>&1 | tee -a "$LOG"
    
    echo "[$(date)] Session ended. Restarting in 60s..." | tee -a "$LOG"
    
    # Keep last 10 logs
    ls -t ~/grind-logs/desktop-*.log | tail -n +11 | xargs -r rm
    sleep 60
done
