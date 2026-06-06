# Roadmap: Sentinel Desktop v7.0.0 Perception

## Overview

The "Grounding Revolution" -- fix the single biggest failure mode: missed clicks. Build a hybrid accessibility-first grounding pipeline, annotate screenshots with numbered Set-of-Marks targets, support native computer-use tool loops for Anthropic and OpenAI, verify every click landed, calibrate for HiDPI/multi-monitor setups, and optionally support a local offline grounding model. Six phases, 17 requirements, all feeding one outcome: clicks that actually land.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: DPI & Coordinate Calibration** - Detect scaling, transform coordinates, calibrate new displays
- [ ] **Phase 2: Hybrid Grounding Pipeline** - Accessibility-first element map, ID-based targeting, vision fallback
- [ ] **Phase 3: Set-of-Marks Screenshots** - Numbered bounding boxes, mark-based targeting, multi-source mark generation
- [ ] **Phase 4: Native Computer-Use Adapters** - Anthropic and OpenAI native tool loops, JSON fallback preserved
- [ ] **Phase 5: Click Verification & Self-Correction** - Post-action diff, tiered retry, enforced self-healing
- [ ] **Phase 6: Local Grounding Model** - Optional offline bbox prediction, feature-flagged, air-gapped capable

## Phase Details

### Phase 1: DPI & Coordinate Calibration
**Goal**: Coordinates are correct on every display configuration -- HiDPI, multi-monitor, and mixed-scaling setups all resolve to the right pixels
**Depends on**: Nothing (first phase -- coordinate correctness is load-bearing for everything downstream)
**Requirements**: DPI-01, DPI-02, DPI-03
**Success Criteria** (what must be TRUE):
  1. Agent detects DPI scaling factor for each connected monitor at startup and reports it in logs
  2. A click at coordinates (x, y) on a 150% scaled display lands on the correct pixel (verified by screenshot diff)
  3. Multi-monitor setups with different scaling per display resolve coordinates correctly for each monitor
  4. A one-time calibration probe runs when a new display configuration is detected and persists the calibration data
**Plans**: TBD

Plans:
- [ ] 01-01: DPI detection and scaling factor calculation per monitor
- [ ] 01-02: Coordinate transformation for HiDPI and multi-monitor setups
- [ ] 01-03: One-time calibration probe and persistence

### Phase 2: Hybrid Grounding Pipeline
**Goal**: The agent builds a structured element map from the accessibility tree and targets elements by ID instead of raw pixel coordinates, falling back to vision mode only when no a11y match exists
**Depends on**: Phase 1 (correct coordinates are required for a11y bounding boxes to be useful)
**Requirements**: GND-01, GND-02, GND-03
**Success Criteria** (what must be TRUE):
  1. Before asking the model for coordinates, the agent queries the UIAutomation tree and builds a numbered list of interactive elements with their bounding boxes and names
  2. The model receives element IDs as action targets (e.g., `click_element button_Save`) and the executor resolves the ID to the correct screen coordinates
  3. When the model targets an element that has no a11y match (canvas, custom controls), the system transparently falls back to raw coordinate mode
  4. The grounding pipeline is exposed to the model in the system prompt as the primary targeting method
**Plans**: TBD

Plans:
- [ ] 02-01: Element map builder from UIAutomation tree (extend core/ui_tree.py)
- [ ] 02-02: ID-based action targeting in executor (extend core/action_executor.py)
- [ ] 02-03: Vision fallback path and engine integration (core/grounding.py, core/engine.py)

### Phase 3: Set-of-Marks Screenshots
**Goal**: Screenshots sent to the model have numbered bounding boxes overlaid on every clickable/typeable element, and the model targets them by mark ID
**Depends on**: Phase 2 (element map provides the a11y data that feeds mark generation)
**Requirements**: SOM-01, SOM-02, SOM-03
**Success Criteria** (what must be TRUE):
  1. Screenshots sent to the model display numbered bounding boxes on all interactive elements detected from the a11y tree
  2. The model can reference targets by mark ID (e.g., `click_mark 7`) and the executor resolves it to the correct element coordinates
  3. Mark generation includes OCR-detected text regions and CV contour detection for canvas/custom UI elements that lack a11y representation
**Plans**: TBD

Plans:
- [ ] 03-01: SoM overlay renderer on screenshots (extend core/screenshot.py, core/grounding.py)
- [ ] 03-02: Mark-based targeting in action executor and mark ID resolution
- [ ] 03-03: Multi-source mark generation (a11y + OCR + CV contours)

### Phase 4: Native Computer-Use Adapters
**Goal**: Anthropic and OpenAI models use their own native screen-control tool loops for maximum accuracy, while all other providers continue using the JSON action protocol
**Depends on**: Phase 3 (SoM screenshots and grounding pipeline must exist for JSON fallback path)
**Requirements**: NCU-01, NCU-02, NCU-03
**Success Criteria** (what must be TRUE):
  1. When using Anthropic Claude, the agent sends screenshots and receives tool-use actions via the `computer_20250124` native tool format -- no JSON action parsing involved
  2. When using OpenAI models with computer-use support, the agent uses the `computer-use-preview` native tool format for screen-control actions
  3. All other providers (18+) continue to work unchanged via the existing JSON action protocol
  4. Provider capability detection in the registry automatically routes to the correct adapter without user configuration
**Plans**: TBD

Plans:
- [ ] 04-01: Provider capability detection in registry (extend core/provider_registry.py)
- [ ] 04-02: Anthropic computer_20250124 adapter (extend core/llm_client.py)
- [ ] 04-03: OpenAI computer-use-preview adapter (extend core/llm_client.py)
- [ ] 04-04: JSON protocol fallback verification and integration

### Phase 5: Click Verification & Self-Correction
**Goal**: Every click is verified by a post-action screenshot diff, and misses trigger automatic retry through progressively simpler targeting methods
**Depends on**: Phase 2 (a11y targeting), Phase 3 (SoM targeting), Phase 4 (action execution paths)
**Requirements**: VER-01, VER-02, VER-03
**Success Criteria** (what must be TRUE):
  1. After every click action, the agent captures a screenshot and diffs the target region to detect whether the visual state changed
  2. When a click miss is detected, the agent automatically retries through grounding tiers: a11y element -> SoM mark -> raw coordinates -> keyboard navigation
  3. Self-healing retry logic is enforced in executor code (not dependent on system prompt prose) and triggers on verified miss, not just error
**Plans**: TBD

Plans:
- [ ] 05-01: Post-action screenshot diff and click-landed detection
- [ ] 05-02: Tiered retry through grounding methods on miss
- [ ] 05-03: Enforced self-healing logic in executor (promote from prompt to code)

### Phase 6: Local Grounding Model
**Goal**: An optional local model can predict bounding boxes from screenshots without any cloud round-trip, enabling air-gapped operation
**Depends on**: Phase 2 (grounding pipeline interface), Phase 3 (SoM mark generation)
**Requirements**: LCL-01, LCL-02
**Success Criteria** (what must be TRUE):
  1. When the `local_grounding` feature flag is enabled, the agent uses a local model to convert natural language targets (e.g., "the Save button") into bounding boxes without any API call
  2. The feature is fully optional: disabled by default, dependency is optional, and the agent works identically without it installed
**Plans**: TBD

Plans:
- [ ] 06-01: Local grounding model adapter (OmniParser/Florence-2/UGround interface)
- [ ] 06-02: Feature flag gating, optional dependency, and air-gapped configuration

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. DPI & Coordinate Calibration | 0/3 | Not started | - |
| 2. Hybrid Grounding Pipeline | 0/3 | Not started | - |
| 3. Set-of-Marks Screenshots | 0/3 | Not started | - |
| 4. Native Computer-Use Adapters | 0/4 | Not started | - |
| 5. Click Verification & Self-Correction | 0/3 | Not started | - |
| 6. Local Grounding Model | 0/2 | Not started | - |
