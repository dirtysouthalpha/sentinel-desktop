# Requirements: Sentinel Desktop v7.0.0 Perception

**Defined:** 2026-06-06
**Core Value:** Automate any Windows desktop task through natural language — safely, reliably, and with full visibility.

## v7 Requirements

Requirements for v7.0.0 "Perception" milestone. Each maps to roadmap phases.

### Grounding Pipeline

- [ ] **GND-01**: Agent builds structured element map from accessibility tree (UIAutomation) before asking model for coordinates
- [ ] **GND-02**: Model selects target by element ID (not raw pixel coordinates) when a11y elements are available
- [ ] **GND-03**: System falls back to vision/coordinate mode only when no accessibility element matches target

### Set-of-Marks (SoM)

- [ ] **SOM-01**: Annotated screenshots render numbered bounding boxes on every clickable/typeable element
- [ ] **SOM-02**: Model references targets by mark ID (e.g., "click_mark 7") instead of coordinates
- [ ] **SOM-03**: Mark generation combines a11y tree + OCR + CV contour detection for canvas/custom UIs

### Native Computer-Use Models

- [ ] **NCU-01**: First-class adapter for Anthropic computer_20250124 tool — model uses its own native screen-control loop
- [ ] **NCU-02**: First-class adapter for OpenAI computer-use-preview tool — model uses its own native screen-control loop
- [ ] **NCU-03**: JSON action protocol preserved as universal fallback for all other 18+ providers

### Local Grounding

- [ ] **LCL-01**: Optional local grounding model (OmniParser/Florence-2/UGround style) converts "click the Save button" → bbox with no cloud round-trip
- [ ] **LCL-02**: Feature-flag gated behind `local_grounding` config, optional dependency, works air-gapped

### Click Verification

- [ ] **VER-01**: After-action screenshot diff detects whether click landed (region changed)
- [ ] **VER-02**: Auto-retry through grounding tiers (a11y → SoM → coords → keyboard nav) on click miss
- [ ] **VER-03**: Self-healing logic promoted from system prompt prose to enforced executor code

### DPI & Calibration

- [ ] **DPI-01**: Detect DPI scaling per monitor at runtime
- [ ] **DPI-02**: Transform coordinates correctly for HiDPI, multi-monitor, and mixed-scaling setups
- [ ] **DPI-03**: One-time calibration probe for new display configurations

## Future Requirements

Deferred to future milestones (v8.0+ per master roadmap).

### Web Browser Control (v8.0 "Webhand")
- **WEB-01**: Embedded controlled browser via Playwright with CDP
- **WEB-02**: DOM-aware web actions (web_click, web_type, web_read, etc.)
- **WEB-03**: Dual-mode unification (browser DOM vs native vision)

### Network Operations (v9.0 "Netops")
- **NET-01**: SSH/serial/Telnet/WinRM/SNMP connection layer
- **NET-02**: Network device profiles (SonicWall, Cisco, FortiGate, etc.)
- **NET-03**: Diagnostic playbooks for common network issues

### Server & Fleet (v10.0 "Sentinel Server")
- **SRV-01**: Service/daemon mode (Windows Service + systemd)
- **SRV-02**: Remote agent + control plane for fleet management
- **SRV-03**: Web control center (React dashboard)

### Memory & Learning (v11.0 "Memory")
- **MEM-01**: Persistent agent memory for environment facts
- **MEM-02**: Skill library (learned procedures from successful runs)
- **MEM-03**: RAG over forensic log run history

### Multi-Agent Orchestration (v12.0 "Conductor")
- **ORC-01**: Hierarchical planner → executor → critic
- **ORC-02**: Parallel task graphs on separate virtual desktops/agents
- **ORC-03**: Specialist sub-agents (browser, terminal, netops, desktop)

### Linux Desktop Parity (v13.0 "Penguin")
- **LNX-01**: Linux accessibility tree via AT-SPI (pyatspi/D-Bus)
- **LNX-02**: Input on Wayland (ydotool/libei) and X11 (xdotool/Xlib)
- **LNX-03**: Platform abstraction layer formalization

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web browser automation (Playwright) | v8.0 "Webhand" — requires grounding first |
| SSH/network device control | v9.0 "Netops" — requires grounding first |
| Fleet/daemon mode | v10.0 "Sentinel Server" — requires single-agent reliability first |
| Persistent memory / RAG | v11.0 "Memory" — requires reliable actions first |
| Multi-agent orchestration | v12.0 "Conductor" — requires memory + grounding |
| Voice I/O | v14.0 "Voice" — far future |
| Mobile platform support | Not desktop automation |
| Custom action plugins | Plugin system exists, not prioritized |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DPI-01 | Phase 1 | Pending |
| DPI-02 | Phase 1 | Pending |
| DPI-03 | Phase 1 | Pending |
| GND-01 | Phase 2 | Pending |
| GND-02 | Phase 2 | Pending |
| GND-03 | Phase 2 | Pending |
| SOM-01 | Phase 3 | Pending |
| SOM-02 | Phase 3 | Pending |
| SOM-03 | Phase 3 | Pending |
| NCU-01 | Phase 4 | Pending |
| NCU-02 | Phase 4 | Pending |
| NCU-03 | Phase 4 | Pending |
| VER-01 | Phase 5 | Pending |
| VER-02 | Phase 5 | Pending |
| VER-03 | Phase 5 | Pending |
| LCL-01 | Phase 6 | Pending |
| LCL-02 | Phase 6 | Pending |

**Coverage:**
- v7 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-06-06*
*Last updated: 2026-06-06 — Traceability added during roadmap creation*
