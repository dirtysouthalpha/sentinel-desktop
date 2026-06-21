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

<!-- Phase 3 moved to Blocked: PyPI trusted-publishing not configured -->

<!-- STEALTH-TIER IMPLEMENTATION — sourced from the Phase 1 design spec
     (docs/superpowers/specs/2026-06-20-fully-stealth-humanization-tier.md).
     One phase per module, TDD, ordered by dependency. The spec's
     "## Deliverables" lists the exact files + tests for each. A phase is
     done when: the module exists, its tests/test_humanize_stealth_*.py passes,
     ruff clean, full pytest exit 0, committed + pushed. Do NOT wire a module
     into the chokepoints until its own phase is complete — wiring is its own
     dedicated phase (Phase 11) so a broken half-wire never lands on main. -->

- [ ] Phase 6: Overshoot + sweep-back — `core/humanize/overshoot.py` (NEW).
  `overshoot_target(target, current, *, rng, profile, target_width_px) -> tuple`
  returning a point past the target (overshoot) or short of it (undershoot),
  probabilistically scaled by target size. Spec §"overshoot.py", Deliverable #4.
  Gate: `tests/test_humanize_stealth_overshoot.py` passes (overshoot probability
  scales inversely with target width; undershoot vs overshoot distribution;
  sweep-back lands within jitter of target). Depends on rng.py (exists) only.

- [ ] Phase 7: Error + self-correction injection — `core/humanize/errors.py`
  (NEW). `inject_errors(text, *, rng, profile) -> list[(char, delay)]` that, at a
  profile-driven rate, inserts a wrong char + backspace + correct char with human
  correction delays. Spec §"errors.py", Deliverable #5. Gate:
  `tests/test_humanize_stealth_errors.py` passes (error rate within bounds;
  backspace handling; correction delay distribution; seed reproducibility).

- [ ] Phase 8: Inertial scroll momentum — `core/humanize/scroll.py` (NEW).
  `momentum_scroll(delta, *, rng, profile) -> list[int]` decomposing a discrete
  scroll delta into a decaying momentum frame sequence with jitter. Spec
  §"scroll.py", Deliverable #6. Gate: `tests/test_humanize_stealth_scroll.py`
  passes (momentum decay, jitter, frame-count caps, sum preserves net delta).

- [ ] Phase 9: Attention drift + dwell — `core/humanize/attention.py` (NEW).
  `attention_pause(action_context, *, rng, profile) -> float` returning an
  occasional gaze-like pause, scaled by context (longer on ambiguous UI). Spec
  §"attention.py", Deliverable #7. Gate: `tests/test_humanize_stealth_attention.py`
  passes (pause probability, context-aware scaling, re-read pause branch, zero
  when disabled).

- [ ] Phase 10: Biometric sampler — `core/humanize/biometric_sampler.py` (NEW).
  `sample_operator(session_log_path) -> BiometricStats` extracting real inter-key
  + inter-move distributions from a captured session, returning a dataclass the
  StealthProfile can consume. Spec §"biometric_sampler.py", Deliverable #2.
  IMPORTANT: the spec forbids inventing synthetic values — if no real samples
  exist, return None / raise a clear error, don't fake it. Gate:
  `tests/test_humanize_stealth_biometric.py` passes (parses a fixture session log
  into correct stats; returns None/raises on empty input; never synthesizes).
  Last of the leaf modules since it only feeds StealthProfile defaults.

- [ ] Phase 11: Stealth wiring at the chokepoints — modify `core/humanize/motion.py`
  (`humanized_path` accepts `target_size`, routes through fitts+overshoot when
  profile is StealthProfile), `core/humanize/typing.py` (`keystroke_delays`
  accepts `errors: bool`, routes through errors.py),
  `core/action_executor.py` (`_click`/`_type_text`/`_scroll` pass context:
  target_size, field_type, action_context), `core/desktop.py` (physical chokepoint
  uses `fitts_move_duration` for StealthProfile). Spec Deliverables #9-12.
  Gate: existing humanize tests still green with `SENTINEL_HUMANIZE=0` (the
  naturalistic path must NOT change); new tests assert the stealth path activates
  only under StealthProfile. ruff + full pytest exit 0. Do this ONLY after Phases
  4-10 are done — it's the integration point where a half-wire breaks main.

- [ ] Phase 12: Detector-evasion pipeline — `core/humanize/detector_evasion.py`
  (NEW). A pluggable `EvasionPipeline` that wraps the stealth modules and applies
  a configurable ordered list of evasion strategies. Spec §"detector_evasion.py",
  Deliverable #8. Gate: `tests/test_humanize_stealth_detector_evasion.py` passes
  (pipeline applies strategies in order; a no-op pipeline is a passthrough;
  adding a strategy changes output; per-strategy failure degrades gracefully).
  Last — it wraps everything, so all other stealth phases must be done first.


## Blocked

<!-- Move a phase here with a [BLOCKED: <one-line reason>] note if it can't proceed. -->

- [BLOCKED: PyPI trusted-publishing not configured] Phase 3: Cut v22.0.0 release tag —
  push an annotated tag, confirm `.github/workflows/release.yml` runs (test → build →
  publish), verify the PyPI + GitHub Release succeeds. GATED: before doing this,
  confirm PyPI trusted-publishing is configured per `RELEASING.md`
  (owner/repo/workflow/environment). If not set up, move this to ## Blocked with
  [BLOCKED: PyPI trusted-publishing not configured] rather than attempting a release
  that will fail mid-publish. Demoted from Phase 1 because firing a PyPI release is
  high-blast-radius and shouldn't be the loop's first autonomous action.

## Done

- [x] Phase 5: Fitts's-Law targeting — `core/humanize/fitts.py`. Pure function
  `fitts_move_duration(start, target, target_size, *, rng, profile) -> float`
  computing Fitts's Law: time = a + b * log2(2 * distance / target_width).
  Implements ID computation, duration scaling with fitts_width_scaling,
  fallback to distance-only timing for NATURALISTIC profile, edge cases
  (tiny target < 5px clamped, zero-distance returns base intercept 0.05s,
  non-negative duration guarantee). 16 tests covering ID computation,
  duration scaling, edge cases, profile fallback, determinism. ruff clean,
  all humanize tests green (138 passing). (commit a9237cf)
- [x] Phase 4: StealthProfile extension — `core/humanize/profile.py`. Added a
  frozen `StealthProfile(Profile)` dataclass (subclass — inherits the naturalistic
  fields, overrides with biometric-sampled defaults) + a `STEALTH` preset registered
  in `_PRESETS`. Spec §"profile.py — StealthProfile extension", Deliverable #1.
  Gate: `tests/test_humanize_stealth_profile.py` passes (31/31 tests: instantiation,
  field validation, preset registry lookup via `get_default_profile()` under
  `SENTINEL_HUMANIZE_PROFILE=stealth`). ruff clean + full pytest exit 0. This is the
  foundation every other stealth phase imports — do it first. (commit 67f60ad)
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
