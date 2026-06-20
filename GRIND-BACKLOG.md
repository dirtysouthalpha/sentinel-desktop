# Grind Backlog

Worked top-down by `grind-phase.sh`. The loop does the topmost `[ ]` phase under
**## Active**, then **STOPS** — one phase per session. Each restart picks up the
next phase, so every phase gets a clean context.

**Rules:**
- Mark a phase `[x]` ONLY when: deliverables exist + `ruff check core/ gui/ api/`
  clean + `pytest` exit 0 + committed + pushed. Append the commit SHA: `(commit abc1234)`.
- The loop never invents work. If **## Active** is empty, it runs a maintenance pass
  (verify gates green, fix any newly-failing tests) and stops.
- Blocked? Move the phase to **## Blocked** with `[BLOCKED: <reason>]`, commit, push.
- A human can reorder/add/edit phases here freely at any time.

Format: `- [ ] Phase N: <title> — see \`docs/superpowers/specs/<spec>.md\``

---

## Active

- [ ] Phase 3: Cut v22.0.0 release tag — push an annotated tag, confirm
  `.github/workflows/release.yml` runs (test → build → publish), verify the PyPI +
  GitHub Release succeeds. GATED: before doing this, confirm PyPI trusted-publishing
  is configured per `RELEASING.md` (owner/repo/workflow/environment). If not set up,
  move this to ## Blocked with [BLOCKED: PyPI trusted-publishing not configured]
  rather than attempting a release that will fail mid-publish. Demoted from Phase 1
  because firing a PyPI release is high-blast-radius and shouldn't be the loop's
  first autonomous action.

## Blocked

<!-- Move a phase here with a [BLOCKED: <one-line reason>] note if it can't proceed. -->

_(none)_

## Done

- [x] Phase 2: Pre-load the Neuralis brain with the sentinel-desktop knowledge base
  — created scripts/seed_brain.py and successfully persisted v18-v22 architecture,
  grind-loop coordination protocol, and fleet topology to the brain (neurons 8891,
  8892, 8893). All fleet agents can now recall this knowledge. (commit 223d07b)
- [x] Phase 1: Design the deferred fully-stealth humanization tier — wrote
  comprehensive 1160-line design spec covering biometric profiles, Fitts's-Law,
  overshoot/correction, error injection, scroll momentum, attention simulation,
  and pluggable detector-evasion pipeline. Design-only, no code. (commit ff9f7e8)
- [x] Phase 0: v18-v22 shipped, red suite repaired (51 → 0 failures from the
  ExecutorConfig refactor), CLAUDE.md v18 section corrected. (commit 1e48802, 8f3ebb5)
