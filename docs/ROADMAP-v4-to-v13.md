# Sentinel Desktop — The 10-Version Master Roadmap (v4.0 → v13.0)

> **Mission:** Make Sentinel Desktop the best autonomous computer-control agent on the
> planet. Windows-first (it's the daily driver, ~90% of use), Linux-capable, server-
> deployable. Give it a goal in plain English and it does *anything you could do at a
> keyboard* — click icons, write documents, drive a terminal, run commands, pull up a
> website and troubleshoot a SonicWall, diagnose a sick server, and self-heal when it
> goes wrong.

---

## 0. Where We Are Today (honest baseline)

**v3.1 is a strong, well-tested foundation** — 21k LOC, 45 core modules, ~5,000 tests,
99% coverage, 40 action types, 20+ LLM providers, GUI + headless API + CLI, approval
gate + Esc-x3 failsafe, checkpoint/resume, forensic logging, recorder, workflows,
scheduler, multi-agent pool, recovery + popup handling, encryption + RBAC + audit export.

**But to be "the best on the planet," four structural truths must be faced:**

1. **Grounding is the bottleneck.** The agent asks a vision LLM to emit raw pixel
   coordinates (`{"action":"click","x":500,"y":300}`). This is the single biggest
   failure mode of *every* computer-use agent. UIAutomation (`click_control`,
   `list_controls`) is a great fallback but is treated as secondary and is Windows-only.
   **Accuracy of "where do I click" is the #1 lever for everything else.**

2. **No browser-native control.** Web admin (SonicWall, FortiGate, Meraki, Unifi,
   M365 admin, Azure portal) is half of real IT work. Driving it through screen-pixels
   is fragile. We have zero Playwright/CDP/DOM capability today.

3. **No network/infra reach.** No SSH, serial, SNMP, or device CLI. "Install it on a
   server and have it diagnose issues" and "troubleshoot a firewall" need a real
   ops toolkit, not just desktop pixels.

4. **Linux is dev/test only.** `pywin32`, `uiautomation`, `pygetwindow`, `keyboard`,
   PowerShell are all win32-gated. On Linux we can move a mouse via pyautogui but we
   have no accessibility tree, no window manager control, no Wayland story.

The roadmap below is sequenced so each version unlocks the next. **v4.0 (grounding)
is load-bearing** — do it first, everything compounds from there.

---

## Roadmap at a glance

| Ver | Codename | One-line theme |
|-----|----------|----------------|
| **v4.0** | **Perception** | Hybrid accessibility-first grounding + set-of-marks + native computer-use models. Clicks that actually land. |
| **v5.0** | **Webhand** | Embedded browser control (Playwright/CDP). Drive any web app / firewall UI by DOM, not pixels. |
| **v6.0** | **Netops** | SSH / serial / SNMP + network-device profiles. SonicWall, Cisco, Fortinet, Unifi, Meraki. |
| **v7.0** | **Sentinel Server** | Headless daemon, fleet of remote agents, "install on the server and let it diagnose." |
| **v8.0** | **Memory** | Persistent memory + learned skill library + RAG over run history. It gets better the more you use it. |
| **v9.0** | **Conductor** | Planner/executor/critic multi-agent orchestration. Long-horizon tasks, parallel work graphs. |
| **v10.0** | **Penguin** | Full Linux desktop parity (AT-SPI + Wayland/X11) and cross-platform unification. |
| **v11.0** | **Voice** | Voice I/O, wake word, ambient monitoring, proactive "watch & alert." |
| **v12.0** | **Fortress** | Enterprise security, SSO, secrets vault, policy guardrails, compliance reporting, MDM deploy. |
| **v13.0** | **Operator** | Long-horizon autonomy, eval/simulation harness, self-healing at scale, skill marketplace. The product. |

---

## v4.0 — "Perception": the grounding revolution  ⭐ FOUNDATION

**Why first:** if the click misses, nothing downstream works. Today's coordinate-from-
vision approach is the ceiling on reliability. Raise the ceiling.

**Headline features**
- **Hybrid grounding pipeline (accessibility-first, vision-fallback).** Before asking
  the model for coordinates, build a structured element map of the focused window from
  the accessibility tree (`core/ui_tree.py`, UIAutomation) and expose it to the model as
  a *numbered list of targets*. The model picks a target *id*, not a pixel. Fall back to
  vision coordinates only when no element matches. Extend `ui_tree.py` from "available"
  to "primary path."
- **Set-of-Marks (SoM) screenshots.** Render the annotated screenshot the model sees:
  overlay numbered boxes on every clickable/typeable element (from the a11y tree +
  OCR + CV contour detection for canvas/custom UIs). Model says `click_mark 7`. This is
  the technique that took GPT-4V/Claude computer-use accuracy from ~30% to ~70%+.
  New module: `core/grounding.py` (mark generation, overlay rendering, id→bbox map).
- **Native computer-use tool support.** First-class adapters for **Anthropic's
  `computer_20250124` tool** and OpenAI's `computer-use-preview`, so when the user runs
  Claude/GPT we hand the provider its *own* native screen-control tool loop instead of
  our JSON protocol. Detect capability in `provider_registry.py`; route in `llm_client.py`.
  Keep the JSON protocol as the universal fallback for the other 18 providers.
- **Local grounding model (optional, offline).** Bundle support for an OmniParser /
  Florence-2 / UGround-style local model that converts "click the Save button" → bbox
  with no cloud round-trip. Massive latency + cost win; works air-gapped on a locked-down
  server. Optional dependency, behind a feature flag.
- **Click verification + self-correction.** After every action, diff before/after
  screenshots in the target region; if nothing changed, auto-retry through the grounding
  tiers (a11y → SoM → coords → keyboard nav) before reporting failure. Promote the
  "self-healing" prose in the system prompt into enforced executor logic.
- **Coordinate calibration for HiDPI / multi-monitor / scaling.** Today's biggest silent
  bug source on real machines. Detect DPI scaling per monitor and transform coordinates;
  add a one-time calibration probe.

**Files:** `core/grounding.py` (new), `core/ui_tree.py`, `core/llm_client.py`,
`core/provider_registry.py`, `core/tool_schemas.py`, `core/action_executor.py`,
`core/engine.py`, `core/screenshot.py`.

**Success metric:** on a fixed 50-task desktop benchmark (see eval harness, v13 but
stub it here), click-target accuracy ≥ 90%; median steps-to-completion down 30%.

---

## v5.0 — "Webhand": browser & web command

**Why:** "pull up a website and troubleshoot a SonicWall / firewall / anything" =
browser automation. Web UIs have a real DOM — far more reliable than pixels.

**Headline features**
- **Embedded controlled browser** via Playwright (Chromium/Firefox/WebKit) with CDP.
  New module: `core/browser.py`. Launches a managed browser the agent drives directly.
- **DOM-aware web actions:** `web_open`, `web_click(selector|text|role)`, `web_type`,
  `web_read`, `web_extract`, `web_wait_for`, `web_screenshot`, `web_eval_js`,
  `web_download`, `web_upload`, `web_tabs`. Accessibility-tree + ARIA-role targeting so
  the model names elements semantically.
- **Dual-mode unification:** the agent automatically chooses *browser DOM mode* when the
  target is a web app and *native vision mode* otherwise — and can hand off mid-task
  (e.g. download a file in the browser, then open it in Excel natively).
- **Self-signed cert / appliance UX handling** (firewalls love expired self-signed
  certs): auto-accept warnings *for explicitly whitelisted appliance hosts only*, login
  form detection, session keep-alive. Ties into the existing popup handler.
- **Authenticated session vault:** save/restore cookies + storage per site so the agent
  doesn't re-login every run (encrypted via existing `core/encryption.py`).
- **Web recorder:** extend `core/recorder.py` to capture browser interactions into
  replayable scripts (Playwright-codegen style → Sentinel script JSON).

**Files:** `core/browser.py` (new), `core/action_executor.py`, `core/engine.py` (mode
routing), `core/recorder.py`, `core/encryption.py`, `requirements.txt` (playwright,
optional extra).

**Success metric:** complete a full SonicWall/Unifi web-admin task (login → navigate →
read a config value → change a setting → confirm) end-to-end, unattended, with approval
gate on the write step.

---

## v6.0 — "Netops": network & infrastructure operations

**Why:** real IT support and server diagnosis happen over SSH/serial/SNMP and against
network appliances, not just GUIs.

**Headline features**
- **Connection layer:** SSH (paramiko/asyncssh), serial console, Telnet (legacy gear),
  WinRM, SNMP (v2c/v3) get/walk. New module: `core/connections.py`.
- **Network-device profiles** (the analogue of `app_profiles.py` for hardware):
  SonicWall, Cisco IOS/NX-OS, FortiGate, Juniper, Ubiquiti/UniFi, MikroTik, Aruba,
  Meraki (Dashboard API). Each profile knows prompts, paging (`--More--`), enable/config
  modes, and common diagnostic commands. New: `core/device_profiles/`.
- **Diagnostic playbooks:** "why is the internet down," "show me dropped packets on the
  WAN," "back up the firewall config," "diff running vs startup config," "find the
  blocking firewall rule," "check VPN tunnel status." Shipped as parameterized scripts in
  `scripts/netops/`.
- **Config backup + drift detection:** pull device configs on a schedule (reuse
  `core/scheduler.py`), store + version + diff them, alert on unexpected change.
- **Server diagnosis toolkit (local + remote):** structured collectors for CPU/mem/disk/
  IO/process/service/eventlog/journald/dmesg/netstat, a "triage" report generator, and a
  guided root-cause loop. Works whether Sentinel is *on* the server or SSH'd *into* it.
- **Safety:** all device-config writes go through the approval gate with a rendered diff;
  read-only diagnostics run freely. Credentials via the secrets vault (v12 preview).

**Files:** `core/connections.py` (new), `core/device_profiles/` (new),
`scripts/netops/` (new), `core/scheduler.py`, `core/action_executor.py`.

**Success metric:** SSH into a Linux server with a real symptom (full disk / runaway
process / down service) and produce a correct diagnosis + proposed fix without human
hand-holding; back up a SonicWall config nightly with drift alerting.

---

## v7.0 — "Sentinel Server": headless daemon & remote fleet

**Why:** "install it on the server and have it diagnose issues." Sentinel becomes
infrastructure, not just an app on one desktop.

**Headline features**
- **Service/daemon mode:** run as a Windows Service and a systemd unit. Survives logoff,
  auto-starts, self-restarts. New: `installer/service/` + `core/daemon.py`.
- **Remote agent + control plane:** a lightweight Sentinel agent installs on many
  machines and registers with a central controller (extend `api/server.py` into a hub).
  Issue a goal once, target one box or a fleet. mTLS between agent and hub.
- **Session brokering into targets:** the agent can RDP/SSH/console into a *target*
  machine and drive *its* desktop/CLI (nested control), so one Sentinel can service many
  endpoints. Builds on v6 connections + v5 browser-in-VNC.
- **Web control center (finally):** the React dashboard sketched in the v3 roadmap —
  live screen view, click-to-act, run history with replay, fleet status, script/workflow
  library, log streaming. Served from the API server. New: `web/`.
- **Job queue + results store:** durable task queue, structured results, retries, SLAs.
  Extend `core/agent_pool.py` + `core/scheduler.py` with a persistence backend (SQLite
  default, Postgres optional).

**Files:** `core/daemon.py` (new), `installer/service/` (new), `api/server.py` (→ hub),
`web/` (new React app), `core/agent_pool.py`, `core/scheduler.py`.

**Success metric:** deploy the agent to 5 machines from one installer, fire a "run
Windows Update health check" goal at all 5 from the web dashboard, watch live, collect a
consolidated report.

---

## v8.0 — "Memory": persistent memory, skills & learning

**Why:** the difference between a demo and a daily driver is that it *remembers* how you
do things and stops re-deriving them. (Explicitly reverses the old "no learning" scope —
that constraint no longer serves the mission.)

**Headline features**
- **Persistent agent memory:** facts about *this* environment — where apps live, AD
  domain, server names, your naming conventions, "the ticketing system is at this URL."
  Stored encrypted, surfaced into the system prompt as context. New: `core/memory.py`.
- **Skill library (learned procedures):** when a task succeeds, distill the action trace
  into a reusable, parameterized *skill* ("reset_outlook_profile", "onboard_user"). Next
  time, the planner calls the skill directly instead of re-exploring. Bridges
  recorder + workflow + memory.
- **RAG over run history:** index every forensic log; before a new task, retrieve similar
  past runs and inject "last time you did this, here's what worked." Local embeddings
  (works offline) with optional cloud.
- **Failure memory:** remember what *didn't* work ("this dialog needs Tab×2 then Enter")
  so the same mistake isn't repeated.
- **"Teach me" mode:** user demonstrates once (via recorder), Sentinel generalizes it
  into a skill with named parameters and a natural-language trigger.

**Files:** `core/memory.py` (new), `core/skills.py` (new), `core/recorder.py`,
`core/workflow.py`, `core/engine.py`, `core/forensic_log.py`.

**Success metric:** a task that took 15 exploratory steps the first time completes in ≤ 4
the second time via a learned skill; user can say "onboard a new user named X" and it
runs the learned procedure.

---

## v9.0 — "Conductor": planner / multi-agent orchestration

**Why:** long-horizon, multi-app, multi-machine tasks need decomposition, parallelism,
and a critic — not one linear loop.

**Headline features**
- **Hierarchical planner → executor → critic.** A planner LLM decomposes the goal into a
  task graph; executors (the v4 loop) run leaves; a critic/verifier agent checks each
  subgoal's *actual* completion against evidence before proceeding. New: `core/planner.py`,
  `core/critic.py`.
- **Parallel task graphs:** independent branches run on separate virtual desktops /
  remote agents concurrently (reuse `core/agent_pool.py`, `core/virtual_desktop.py`).
- **Specialist sub-agents:** a browser agent, a terminal agent, a netops agent, a
  desktop agent — each tuned (prompt + toolset) for its domain, dispatched by the
  conductor.
- **Reflection & replan:** on subgoal failure, the planner replans rather than the
  executor blindly retrying; budget-aware (stop when cost/steps exceed thresholds).
- **Human-in-the-loop checkpoints:** planner can pause at defined gates ("about to change
  prod firewall rule — approve?") with full context surfaced.

**Files:** `core/planner.py` (new), `core/critic.py` (new), `core/engine.py`,
`core/agent_pool.py`, `core/virtual_desktop.py`.

**Success metric:** a 30-minute, cross-application goal ("collect logs from 3 servers,
correlate the errors, write a summary doc, and email it") completes unattended with
correct intermediate verification.

---

## v10.0 — "Penguin": full Linux desktop parity

**Why:** the user wants a version that genuinely works on Linux — not just dev/test, but
real desktop control. Today Linux can only move a mouse.

**Headline features**
- **Linux accessibility tree via AT-SPI** (`pyatspi`/D-Bus) — the Linux analogue of
  UIAutomation, feeding the v4 grounding pipeline. New: `core/linux_a11y.py`.
- **Input on Wayland *and* X11:** `ydotool`/`libei` for Wayland, `xdotool`/Xlib for X11;
  capability detection at runtime. Window management via `wmctrl`/D-Bus.
- **Linux screenshot path:** Pipewire/portal capture on Wayland, mss/X11 fallback.
- **Linux app + shell profiles:** GNOME/KDE quirks, bash/zsh terminal control, package
  managers, journald, systemctl — mirroring the Windows PowerShell/CMD path.
- **Platform abstraction cleanup:** formalize a `core/platform/` layer so Windows, Linux
  (and a stub macOS) share one interface; retire scattered `sys_platform` gates.
- **Parity test matrix:** the eval benchmark runs on Windows *and* Linux in CI.

**Files:** `core/linux_a11y.py` (new), `core/platform/` (new abstraction),
`core/desktop.py`, `core/window_manager.py`, `core/screenshot.py`, `core/stealth_input.py`.

**Success metric:** the v4 desktop benchmark hits ≥ 80% on Ubuntu (GNOME/Wayland) and
the IT-support scripts have Linux equivalents.

---

## v11.0 — "Voice": ambient, proactive, hands-free

**Why:** the most natural way to drive an autonomous operator is to *talk* to it, and the
highest-value mode is one that *watches* and tells you when something needs attention.

**Headline features**
- **Voice in/out:** local STT (whisper.cpp/faster-whisper) + TTS, push-to-talk and wake
  word ("Sentinel…"). Fully offline option for locked-down environments. New: `core/voice.py`.
- **Conversational task control:** start, steer, pause, and approve actions by voice;
  spoken status updates on long runs.
- **Ambient monitoring & proactive alerts:** watch screen regions / log streams / device
  status and notify (existing `core/notifications.py`) when a condition triggers — "the
  backup job failed," "disk on SRV-01 crossed 90%," "a new ticket came in."
- **Triggers & automations:** event-driven runs (file appears, email arrives, webhook,
  metric threshold) → kick off a workflow. Extend `core/scheduler.py` into a general
  trigger engine.

**Files:** `core/voice.py` (new), `core/triggers.py` (new), `core/notifications.py`,
`core/scheduler.py`.

**Success metric:** fully hands-free: speak a goal, hear progress, approve by voice; an
ambient watcher catches a real failure and alerts before the user notices.

---

## v12.0 — "Fortress": enterprise security & compliance

**Why:** to be deployed on real servers and across a fleet, it must be *trustworthy* and
*auditable*. Builds on existing `auth.py` / `encryption.py` / `audit_export.py`.

**Headline features**
- **Secrets vault:** first-class encrypted credential store (Windows DPAPI / libsecret /
  optional HashiCorp Vault + cloud KMS), with per-credential scoping and never-log
  guarantees. Integrates with v5 site sessions and v6 device logins.
- **SSO / OIDC / SAML** for the web control center; SCIM user provisioning.
- **Hardened RBAC + policy guardrails:** declarative policy ("this role may never delete
  files / may only touch these hosts / writes require dual approval"). Enforced in the
  executor, not just the prompt. New: `core/policy.py`.
- **Sandboxing & blast-radius limits:** per-run scoping (allowed dirs/hosts/apps), rate
  limits, kill-switch, and a "simulation/shadow" mode that proposes a full plan diff
  before any execution.
- **Compliance-grade audit:** tamper-evident, signed forensic logs; manager-ready PDF
  reports with screenshots, timestamps, approvals, and outcomes (extend `audit_export.py`).
- **MDM / silent enterprise deployment:** MSI + Intune/GPO, config-as-code, fleet policy
  push.

**Files:** `core/policy.py` (new), `core/auth.py`, `core/encryption.py`,
`core/audit_export.py`, `api/server.py`, `installer/`.

**Success metric:** pass a self-administered security review; deploy fleet-wide via Intune
with policy enforced and a clean compliance report generated for a week of activity.

---

## v13.0 — "Operator": long-horizon autonomy & the product

**Why:** the capstone — turn a powerful toolbox into *the best autonomous computer
operator*, reliable enough to leave running.

**Headline features**
- **Evaluation & simulation harness:** a versioned benchmark suite (desktop + web +
  netops tasks) with automated scoring, regression gates in CI, and per-release accuracy
  reporting. (The metric backbone referenced by every version above.) New: `eval/`.
- **Long-horizon autonomy:** durable multi-hour/multi-day goals with checkpointing,
  cost/step governance, scheduled resumption, and graceful degradation.
- **Self-healing at scale:** automatic detection + recovery from app crashes, network
  blips, model outages (provider failover via `provider_registry.py`), and drift.
- **Skill & profile marketplace:** share/import skills (v8), app profiles, device
  profiles (v6), and workflows; signed + sandboxed community packs.
- **Cost & performance dashboard:** per-run token/$/latency accounting, model routing
  (cheap model for easy steps, frontier for hard ones), and caching.
- **Product polish:** onboarding wizard, first-run calibration, in-app skill recording,
  one-click installers for Windows + Linux, and the cyberpunk HUD brought to the web.

**Files:** `eval/` (new), `core/engine.py`, `core/provider_registry.py`,
`core/llm_client.py`, `core/agent_pool.py`, GUI + web polish across the board.

**Success metric:** Sentinel runs an 8-hour autonomous IT shift (queue of real tickets)
unattended, with a benchmark score that's improved every release and a published changelog
of accuracy gains.

---

## Cross-cutting principles (every version honors these)

- **Windows-first, Linux-real.** Default and best experience on Windows; Linux is a
  first-class target by v10, scaffolded from v4's platform abstraction onward.
- **Safety is non-negotiable.** The approval gate + Esc-x3 failsafe + dry-run survive and
  *strengthen* every release. New powers (web writes, device config, fleet actions) ship
  *with* their guardrails, never before them.
- **Don't break the suite.** 99% coverage is a feature. Every version adds tests; the v13
  eval harness becomes the north-star metric from v4 onward (stub early, grow it).
- **Offline-capable where it matters.** Local grounding (v4), local embeddings (v8), local
  voice (v11) so a locked-down/air-gapped server still works.
- **Dependencies stay optional.** New heavyweight deps (Playwright, AT-SPI, whisper) are
  extras behind feature flags — `pip install sentinel-desktop[web,netops,voice,linux]`.

## Suggested sequencing for the 1M-context Opus build sessions

1. **Start with v4.0** — it's load-bearing and the highest ROI. Land hybrid grounding +
   SoM + native computer-use + click verification before anything else.
2. **v5 and v6 can interleave** — both are "reach" features (web + network) and share the
   approval-with-diff pattern; pick whichever unblocks today's real work first
   (firewall web UI → v5; SSH server triage → v6).
3. **v7 only after v4–v6** — the fleet is only worth deploying once a single agent is
   genuinely reliable and reaches browsers + devices.
4. **v8/v9 are the intelligence layer** — memory then orchestration; they multiply
   everything below them.
5. **v10–v13** harden, broaden (Linux), humanize (voice), secure (enterprise), and
   polish into the finished product.

*Each "version" here is a milestone, not a sprint — slice freely into minor releases
(v4.0, v4.1, …) and ship continuously. Commit early, commit often, push after every
commit. Safety gates first, capabilities second.*
