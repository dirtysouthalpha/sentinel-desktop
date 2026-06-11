#!/bin/bash
cd /mnt/c/Users/Administrator/Projects/sentinel-desktop
# >>> GLM grind-loop routing (fleet hybrid policy) >>>
export ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
export ANTHROPIC_AUTH_TOKEN=bf6ef726dad74aa1aea51b8d349b0dbe.kHIqQR8LOwS82l8y
export ANTHROPIC_MODEL=glm-4.6
export ANTHROPIC_SMALL_FAST_MODEL=glm-4.5-air
unset ANTHROPIC_CUSTOM_HEADERS
# <<< GLM grind-loop routing <<<
claude -p "You are an autonomous code improvement agent. Read CLAUDE.md for instructions. Start by running tests and fixing failures, then systematically improve the codebase. After each improvement: run tests, run lint, commit, push. Keep going until you run out of turns." --allowedTools Read,Write,Edit,Bash --dangerously-skip-permissions --max-turns 200
