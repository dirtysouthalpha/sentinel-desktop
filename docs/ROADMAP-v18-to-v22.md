# Roadmap — v18 → v22

v18 ("Foundation") reconciled the project with its own claims: synced versions and docs,
unified the dependency manifest, removed deprecated public surface, introduced action/
endpoint registries, and cut the first real release tag. The themes below were deferred
from the original `ROADMAP-v4-to-v13.md` plan and are now scheduled as v19–v22. Each
returns as a **real, tested** feature (the v13–v17 phantom-feature claims were removed from
docs in v18 so these can be built properly).

## v19 — Fortress (enterprise security)

**Theme:** Make Sentinel deployable in an enterprise / fleet context.

- SSO / OIDC / SAML login for the API server and dashboard.
- Declarative policy guardrails — a `core/policy.py` that enforces allow/deny rules over
  actions, endpoints, and file paths (operator-editable, version-controlled).
- Secrets vault — integrate with OS keychain / a dedicated secrets backend (the existing
  `core/encryption.py` + `config/vault.json` are the scaffolding).
- Tamper-evident signed audit logs (append-only, hash-chained).
- MDM deployment — MSI installer + Intune configuration profile.

**Depends on:** v18's release pipeline (real tags, PyPI Trusted Publishing) and the
`[mcp]`/`[net]` extras being installable.

## v20 — Penguin (real Linux desktop parity)

**Theme:** Turn "Windows-first with stubs" into genuinely cross-platform.

- Route the ~60 scattered inline `win32` / `uiautomation` / `ctypes.wintypes` imports
  through the existing `core/platform/` abstraction layer.
- AT-SPI accessibility backend on Linux (the `linux_backend.py` stub becomes real).
- Wayland support (coordinate the screenshot/input story across X11 and Wayland).
- A cross-platform parity test matrix so regressions surface on all three OSes in CI.

**Pairs naturally with:** a Docker management action group (the phantom v16 "DOK-*"
features) — once Linux parity is real, container control is a coherent feature set.

**Depends on:** v18's unified dependency manifest (so platform-conditional deps are
declared cleanly in extras).

## v21 — Operator (eval harness + skill marketplace)

**Theme:** Make agent quality measurable and composable.

- `eval/` — an evaluation / simulation harness: recorded scenarios, deterministic scoring,
  regression tracking across versions. The roadmap has called this "the north-star metric"
  since v4.
- Cost dashboard — per-run token / dollar accounting across providers.
- Skill / profile marketplace — shareable, versioned automation profiles.
- Long-horizon autonomy improvements enabled by the eval loop.

**Pairs naturally with:** goal-learning (`learn_pattern`, `suggest_action` — the phantom
v17 "ADP-*" features) — only worth building once there's an eval harness to prove they
help.

**Depends on:** v18's action registry (so skills register cleanly) and the reconciled
test-count reality (so the eval harness reports against a trustworthy baseline).

## v22 — Voice (ambient / proactive)

**Theme:** Turn audio from an output modality into a continuous sensing + proactive channel.

- Wake-word detection.
- Ambient monitoring — the agent listens for events and proactively surfaces alerts.
- Event triggers (`core/triggers.py`) — fire automations on spoken or system events.
- Full `core/voice.py` — the v17 `core/audio.py` (TTS/STT/volume) is the foundation.

**Depends on:** v18's `[voice]` extra (SpeechRecognition, pyaudio, pycaw) being cleanly
declared so the ambient path is installable.
