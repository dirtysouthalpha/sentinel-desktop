#!/bin/bash
# Sentinel Desktop Grind Loop — Sonnet 4.6
cd ~/Projects/sentinel-desktop
mkdir -p ~/grind-logs

# Quick health check — make sure venv exists
if [ ! -f .venv/bin/python ]; then
    echo "[$(date)] ERROR: .venv not found. Run python3 -m venv .venv && .venv/bin/pip install -r requirements.txt first."
    exit 1
fi

# Install missing deps quietly
.venv/bin/pip install -q pytest pytest-timeout pytest-asyncio pytest-cov ruff 2>/dev/null

while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG=~/grind-logs/desktop-${TIMESTAMP}.log

    echo "[$(date)] Starting Sentinel Desktop grind (Sonnet 4.6)..." | tee -a "$LOG"

    cd ~/Projects/sentinel-desktop
    git pull origin main 2>&1 | tee -a "$LOG"
    rm -rf .aider.chat.history.md .aider.input.history .aider.tags.cache.v4/ 2>/dev/null

    # >>> GLM grind-loop routing (fleet hybrid policy) >>>
    export ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
    export ANTHROPIC_AUTH_TOKEN=bf6ef726dad74aa1aea51b8d349b0dbe.kHIqQR8LOwS82l8y
    export ANTHROPIC_MODEL=glm-4.6
    export ANTHROPIC_SMALL_FAST_MODEL=glm-4.5-air
    unset ANTHROPIC_CUSTOM_HEADERS
    # <<< GLM grind-loop routing <<<
    claude -p "Read CLAUDE.md and follow ALL instructions. You are improving Sentinel Desktop v3.0 — a Python desktop automation agent. Use .venv/bin/python for all python commands and .venv/bin/ruff for linting. After EVERY change, run the test suite (.venv/bin/python -m pytest tests/ -q --timeout=10) and verify tests pass BEFORE committing. If a test fails, fix it immediately. Push after every 3-5 commits. Work through every priority in CLAUDE.md systematically." \
        --allowedTools Read,Write,Edit,Bash \
        --dangerously-skip-permissions \
        --max-turns 500 \
        --model claude-sonnet-4-6 \
        2>&1 | tee -a "$LOG"

    # Post-session verification
    echo "[$(date)] Running post-session test verification..." | tee -a "$LOG"
    .venv/bin/python -m pytest tests/ -q --timeout=10 --tb=line 2>&1 | tail -5 | tee -a "$LOG"
    echo "[$(date)] Test exit code: ${PIPESTATUS[0]}" | tee -a "$LOG"

    # Push any unpushed commits
    git push origin main 2>&1 | tee -a "$LOG"

    echo "[$(date)] Session ended. Restarting in 60s..." | tee -a "$LOG"

    # Keep last 10 logs
    cd ~/grind-logs && ls -t desktop-*.log | tail -n +11 | xargs -r rm
    sleep 60
done
