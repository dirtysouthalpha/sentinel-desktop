# Roadmap: Sentinel Desktop v8.0.0 Webhand

## Overview

Embedded browser control via Playwright with DOM-aware web actions. Drive any web app / firewall UI by DOM, not pixels. Four phases, 19 requirements, all feeding one outcome: reliable web automation for IT admin tasks.

## Phases

- [ ] **Phase 1: Browser Core** — Playwright integration, browser lifecycle, basic web actions
- [ ] **Phase 2: Advanced Web Actions** — Wait, screenshot, JS eval, download, upload, tabs, extract
- [ ] **Phase 3: Dual-Mode & Appliance UX** — Mode detection, handoff, self-signed certs, login detection
- [ ] **Phase 4: Session Vault & Web Recorder** — Cookie persistence, session restore, browser recording

## Phase Details

### Phase 1: Browser Core
**Goal**: Launch a managed browser and perform basic navigation, clicking, typing, and reading
**Depends on**: Nothing (first phase)
**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04, WEB-05
**Success Criteria**:
  1. Browser launches headless or headed and is accessible via Playwright API
  2. web_open navigates to a URL and waits for page load
  3. web_click finds and clicks elements by CSS selector, text, or ARIA role
  4. web_type fills form fields and clears existing content first
  5. web_read extracts text from the page or specific elements
**Plans**:
- [ ] 01-01: Browser manager (core/browser.py) — launch, close, status, page access
- [ ] 01-02: web_open + web_read actions — navigation and text extraction
- [ ] 01-03: web_click + web_type actions — element interaction by selector/text/role

### Phase 2: Advanced Web Actions
**Goal**: Full web interaction toolkit — waiting, screenshots, JS execution, file I/O, tabs
**Depends on**: Phase 1
**Requirements**: WEB-06, WEB-07, WEB-08, WEB-09, WEB-10, WEB-11, WEB-12
**Success Criteria**:
  1. web_wait_for handles element, navigation, and network idle waits
  2. web_screenshot captures viewport as PIL Image
  3. web_eval_js executes JS and returns results
  4. web_download saves files with tracking
  5. web_upload sets file inputs
  6. web_tabs lists, switches, creates, and closes tabs
  7. web_extract pulls structured data from tables and lists
**Plans**:
- [ ] 02-01: web_wait_for + web_screenshot + web_eval_js — observation actions
- [ ] 02-02: web_download + web_upload — file I/O actions
- [ ] 02-03: web_tabs + web_extract — tab management and data extraction

### Phase 3: Dual-Mode & Appliance UX
**Goal**: Auto-detect web vs native, handle appliance quirks, enable mid-task handoff
**Depends on**: Phase 1, Phase 2
**Requirements**: DUAL-01, DUAL-02, CERT-01, CERT-02
**Success Criteria**:
  1. Engine detects web-related goals and activates browser mode automatically
  2. Browser-to-native handoff works (download file then open in Excel)
  3. Self-signed cert warnings auto-accepted for whitelisted hosts
  4. Common IT admin login pages detected and credentials offered
**Plans**:
- [ ] 03-01: Dual-mode detection and routing in engine
- [ ] 03-02: Self-signed cert handling and login form detection

### Phase 4: Session Vault & Web Recorder
**Goal**: Persist browser sessions across runs, record browser actions as scripts
**Depends on**: Phase 1, Phase 2
**Requirements**: SESS-01, SESS-02, REC-01
**Success Criteria**:
  1. Cookies and localStorage saved per site, encrypted
  2. Saved sessions restored on return visits without re-login
  3. Browser interactions captured into replayable Sentinel script JSON
**Plans**:
- [ ] 04-01: Session vault — save/restore cookies encrypted
- [ ] 04-02: Web recorder integration with core/recorder.py

## Progress

**Execution Order:** 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Browser Core | 0/3 | Not started | - |
| 2. Advanced Web Actions | 0/3 | Not started | - |
| 3. Dual-Mode & Appliance UX | 0/2 | Not started | - |
| 4. Session Vault & Web Recorder | 0/2 | Not started | - |
