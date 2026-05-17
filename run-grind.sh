#!/bin/bash
cd /mnt/c/Users/Administrator/Projects/sentinel-desktop
claude -p "You are an autonomous code improvement agent. Read CLAUDE.md for instructions. Start by running tests and fixing failures, then systematically improve the codebase. After each improvement: run tests, run lint, commit, push. Keep going until you run out of turns." --allowedTools Read,Write,Edit,Bash --dangerously-skip-permissions --max-turns 200
