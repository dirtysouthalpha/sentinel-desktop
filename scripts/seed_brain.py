#!/usr/bin/env python3
"""
Pre-load the Neuralis brain with the sentinel-desktop knowledge base.

This script persists critical sentinel-desktop knowledge to the fleet brain so
every agent (Sentinel Desktop, Claude Code, opencode, mimo) can access it.

Run via: python scripts/seed_brain.py

Requirements:
- Neuralis brain API must be reachable (http://100.70.240.55:8000)
- Run once per brain lifetime (idempotent — safe to re-run)
"""

from core import brain

# Knowledge base to persist
KNOWLEDGE_ITEMS = [
    {
        "topic": "sentinel-desktop-architecture-v18-v22",
        "region": "knowledge",
        "content": """
# Sentinel Desktop Architecture (v18.0 - v22.0)

## v18.x — Humanization Engine (June 2026)
- Naturalistic input: curved bezier paths, eased velocity, variable typing cadence
- core/humanize/ subpackage: profile.py (tempo interface), motion.py (bezier paths), typing.py (keystroke cadence), timing.py (micro-pauses)
- Inserted at two chokepoints: core/desktop.py (physical input) and core/stealth_input.py (timing-only stealth input)
- Seeded RNG for reproducible trajectories
- Profile interface enables future stealth tier (biometric profiles, Fitts's-Law, overshoot/correction)

## v19.0 — Fortress (June 2026)
- HS256 JWT auth layer (core/jwt_auth.py)
- OIDC id_token validation (core/oidc.py)
- Declarative policy guardrails (core/policy.py)
- Tamper-evident audit chain (core/audit_chain.py)
- Secrets vault broker (core/secrets.py)
- MDM deployment toolkit (installer/mdm.py)

## v20.0 — Penguin: Linux Desktop Parity (June 2026)
- core/window_manager.py cross-platform window management
- core/stealth_input.py routes through LinuxStealthInputBackend when available
- 18 cross-platform parity tests

## v21.0 — Operator: Eval Harness + Cost Tracker (June 2026)
- eval/ package: ScenarioStep, ScenarioRunner, EvalRegistry, EvalReport
- core/cost_tracker.py: pricing table for 20+ models, session summaries
- core/skill_marketplace.py: skill manifests, install/uninstall/list/find

## v22.0 — Aria: Voice Engine + Event Trigger System (June 2026)
- core/voice.py: VoiceEngine with IDLE/LISTENING/SPEAKING/AMBIENT modes, wake-word polling, on_wake callback
- core/triggers.py: EventType enum, Trigger dataclass, TriggerRegistry (JSON persistence), TriggerEngine
- 6 trigger executor actions: trigger_add, trigger_remove, trigger_list, trigger_enable, trigger_disable, trigger_fire_custom
- 3 voice executor actions: voice_start_ambient, voice_stop_ambient, voice_status
- 9 new tool schemas for LLM tool calling

## Core Engine Structure
- core/platform/ — Platform abstraction layer (base interfaces + Windows/Linux/macOS backends)
- core/ — 45+ modules: agent loop, LLM client, screenshot, OCR, actions, scheduler, workflows
- core/web/ — Web automation subpackage (v8.0): dual-mode detection, cert whitelist, login detector, session vault
- core/browser.py — Playwright browser manager with 11 web actions
- core/netops/ — SSH/network device control (v9.0)
- core/server/ — Fleet/daemon mode (v10.0)
- core/memory/ — Persistent memory (v11.0): episodic (JSONL), semantic (SQLite), working memory
- core/conductor/ — Multi-agent orchestration (v12.0)
- core/humanize/ — Humanization Engine (v18.x)
- core/brain/ — Neuralis Brain bridge (v18.0)

## Cross-Platform Abstraction
- base.py defines abstract base classes
- windows_backend.py: UIA, PostMessage, DPAPI, PowerShell, win32gui
- linux_backend.py: AT-SPI, xdotool, libsecret, bash, wnck
- macos_backend.py: NSAccessibility, AppleScript, Keychain, zsh

## Testing
- 8,685 passing tests as of v22.0
- ruff for linting
- pytest for testing
- Platform-specific tests skip when dependencies unavailable

## Key Design Principles
- Platform abstraction via base interfaces
- Humanization at input chokepoints (not per-action)
- Graceful degradation when services unavailable
- No new dependencies without compelling reason
- Safety paramount: approval gate and Esc-x3 failsafe
""",
    },
    {
        "topic": "sentinel-grind-loop-coordination",
        "region": "decision",
        "content": """
# Sentinel Desktop Grind Loop Coordination Protocol

## Purpose
The grind loop (GRIND-BACKLOG.md) is a phased development protocol where each session implements ONE phase from the "## Active" section, then stops. This ensures every phase gets a clean context and focused implementation.

## How the Loop Works
1. Read GRIND-BACKLOG.md to find the FIRST unchecked phase under "## Active"
2. Read that phase's spec file FULLY before writing any code
3. Implement that ONE phase only
4. After EVERY change, run both and require green:
   - .venv/bin/ruff check core/ gui/ api/
   - .venv/bin/python -m pytest tests/ -q --tb=short --timeout=30
5. When phase is DONE (deliverables exist + ruff clean + pytest exit 0 + committed + pushed):
   - Edit GRIND-BACKLOG.md
   - Move that phase from "## Active" to "## Done"
   - Tick it [x]
   - Append short SHA: "(commit abc1234)"
   - Commit that backlog edit and push it
6. STOP. One phase per session. Period.

## Rules
- Push after every 1-3 commits (small focused commits)
- Pre-push gate blocks if ruff or test collection fails
- Never force-push
- If push rejected as non-fast-forward: git pull --rebase origin main and retry once
- Never add pip dependencies without compelling reason
- Safety paramount: NEVER touch approval gate or Esc-x3 failsafe
- Use git commit (not --amend) so history stays auditable
- If you hit a wall, move phase to "## Blocked" with [BLOCKED: <reason>]

## Maintenance Pass
If "## Active" has NO unchecked phase, run a maintenance pass:
- Verify ruff + pytest are green
- Fix any newly-failing tests
- Do NOT invent new features or edit CLAUDE.md's feature claims
- Commit and push fixes
- STOP

## Blocking a Phase
If a phase genuinely cannot proceed (dependency offline, spec contradicts reality):
- Move the phase to "## Blocked" with "- [BLOCKED: <one-line reason>]"
- Commit and push

## Current Status (as of v22.0)
- Phase 0: v18-v22 shipped, red suite repaired (DONE)
- Phase 1: Design fully-stealth humanization tier (DONE)
- Phase 2: Pre-load Neuralis brain (IN PROGRESS)
- Phase 3: Cut v22.0.0 release tag (ACTIVE - gated on PyPI trusted-publishing setup)

## Coordination Lesson
The grind loop is the single source of truth for phased development. No work happens outside the backlog. Each agent works the topmost unchecked phase, then stops. This prevents context bleed and ensures every phase is completed with full attention before moving to the next.

## Fleet Impact
When this protocol is stored in the brain, every agent can:
- Understand the grind loop without reading GRIND-BACKLOG.md
- Know which phase is currently active
- Follow the protocol when working on sentinel-desktop
- Avoid duplicate work or skipped phases

This is a coordination pattern that can be reused by other projects in the fleet.
""",
    },
    {
        "topic": "sentinel-fleet-topology",
        "region": "knowledge",
        "content": """
# Sentinel Fleet Topology

## Overview
The Sentinel fleet is Brandon's multi-agent automation ecosystem. Sentinel Desktop is one component of a larger coordinated fleet that shares memory and context via the Neuralis brain.

## Fleet Nodes
- **NUKE** — Main workstation, Tailscale 100.86.200.42
  - Runs the shared composio hub (:9191)
  - Runs the Sentinel hub (:9192)
  - Primary development environment for sentinel-desktop

- **homeserver** — 100.70.240.55, Windows
  - Runs the Neuralis Brain API (:8000) — fleet-wide shared memory
  - Runs Sentinel Desktop API (:8091)
  - Runs Sentinel proxy (:8080)
  - Runs many NSSM services
  - Central coordination node

- **hackbox** — 100.115.63.94, edge node
  - Currently has a btrfs FS issue (mostly idle)

- **Sentinel Desktop** — The automation agent itself
  - Cross-platform desktop automation (Windows/Linux/macOS)
  - AI-powered: sees screen, moves mouse, types, interacts with applications
  - Used daily by IT Support Technician
  - v22.0 "Aria" with wake-word detection and event triggers

- **Neuralis** — The brain itself
  - Fleet-wide persistent memory
  - HTTP API at :8000
  - Operations: think (persist), recall (retrieve), search (free-text), fire (reinforce), stats (health)
  - Used by all agents in the fleet

- **Sentinel Prime / Sentinel Desktop** — The automation ecosystem
  - Sentinel Desktop is the agent
  - Sentinel Prime is the broader automation platform

- **AgentLink** — Fleet orchestration
  - Coordinates multiple agents
  - Manages task distribution across the fleet

## Services
- Composio Hub (:9191) — Tool execution hub
- Sentinel Hub (:9192) — Sentinel-specific service hub
- Neuralis Brain (:8000) — Memory service
- Sentinel Desktop API (:8091) — Sentinel's headless server
- Sentinel Proxy (:8080) — Proxy service

## Network
- All nodes connected via Tailscale
- Internal IPs: 100.86.200.42 (NUKE), 100.70.240.55 (homeserver), 100.115.63.94 (hackbox)
- Services reachable via internal Tailscale network

## Agent Coordination
- All agents can read/write to the Neuralis brain
- Sentinel Desktop persists learnings via brain_think
- Other agents (Claude Code, opencode, mimo) recall knowledge via brain_recall
- Shared context enables fleet-wide learning

## Purpose
The fleet topology is important context for:
- Understanding service dependencies (e.g., brain availability)
- Troubleshooting connectivity issues
- Coordinating multi-agent workflows
- Planning deployments and updates

## Access
- Brain: http://100.70.240.55:8000 (internal Tailscale network)
- Composio: http://100.86.200.42:9191
- Sentinel Desktop API: http://100.70.240.55:8091
- Sentinel Proxy: http://100.70.240.55:8080

## Notes
- homeserver is the central coordination node
- NUKE is the primary development workstation
- hackbox is currently idle (FS issues)
- All communication happens over Tailscale mesh VPN
""",
    },
]


def main() -> None:
    """Pre-load the brain with sentinel-desktop knowledge."""
    print("Sentinel Desktop Brain Seeding")
    print("=" * 60)

    # Check brain availability
    if not brain.is_available():
        print("ERROR: Brain API is unreachable at http://100.70.240.55:8000")
        print("Please ensure homeserver is running and brain API is accessible.")
        return

    print("✓ Brain API is reachable")
    print()

    # Get current brain stats
    try:
        stats = brain.stats()
        print(f"Current brain state: {stats.get('neuron_count', 'unknown')} neurons")
        print()
    except Exception as e:
        print(f"WARNING: Could not fetch brain stats: {e}")
        print()

    # Seed knowledge items
    seeded_count = 0
    for item in KNOWLEDGE_ITEMS:
        topic = item["topic"]
        region = item["region"]
        content = item["content"]

        print(f"Seeding: {topic}...")

        try:
            result = brain.think(content=content, region=region, source="sentinel-desktop-seeder")
            print(f"  ✓ Persisted (neuron ID: {result.get('neuron_id', 'unknown')})")
            seeded_count += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")

    print()
    print("=" * 60)
    print(f"Seeding complete: {seeded_count}/{len(KNOWLEDGE_ITEMS)} items persisted")
    print()

    # Verify by searching for one of the items
    print("Verifying seed...")
    try:
        results = brain.search("sentinel-desktop-architecture")
        if results and results.get("neurons"):
            print(f"✓ Verification passed: found {len(results['neurons'])} matching neurons")
        else:
            print("✗ Verification failed: no neurons found for test query")
    except Exception as e:
        print(f"✗ Verification failed: {e}")

    print()
    print("Brain seeding complete. Fleet agents can now recall this knowledge.")
    print("Example: brain.recall('sentinel-desktop architecture')")


if __name__ == "__main__":
    main()
