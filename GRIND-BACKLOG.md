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

- [ ] Phase 3a: PyPI Trusted Publishing configuration — User action required.
  The code changes for OIDC authentication are committed (commit 5d4c5f6) but
  PyPI Trusted Publishing needs to be configured on the PyPI website before
  the release can be tested. See docs/PYPI_TRUSTED_PUBLISHING_SETUP.md for
  step-by-step instructions. Once configured, proceed to Phase 3b.

<!-- STEALTH-TIER IMPLEMENTATION — sourced from the Phase 1 design spec
     (docs/superpowers/specs/2026-06-20-fully-stealth-humanization-tier.md).
     One phase per module, TDD, ordered by dependency. The spec's
     "## Deliverables" lists the exact files + tests for each. A phase is
     done when: the module exists, its tests/test_humanize_stealth_*.py passes,
     ruff clean, full pytest exit 0, committed + pushed. Do NOT wire a module
     into the chokepoints until its own phase is complete — wiring is its own
     dedicated phase (Phase 11) so a broken half-wire never lands on main. -->


## Blocked

<!-- RESOLVED 2026-07-02 (human directive, Brandon): the alien/unrelated-history divergence is settled — push/pull is UNBLOCKED.
     Resolution: a PRIVATE backup remote `backup` = github.com/dirtysouthalpha/sentinel-desktop-grind was created, and local
     `main` now tracks `backup/main` (in sync, 0 ahead / 0 behind). The public `origin`
     (github.com/DirtySouthAlpha/sentinel-desktop) holds a DIFFERENT project's v5-v6 releases and is intentionally left
     untouched — do NOT reconcile with it.
     GRIND GIT PROTOCOL (updated): use a bare `git push` (goes to backup/main via the tracked upstream). NEVER run
     `git push origin main`, NEVER `git pull --rebase`, NEVER force-push origin. Commits/pushes may now proceed normally. -->
- [x] RESOLVED: repository lineage escalation — backup remote wired, `main` → `backup/main`, push/pull unblocked (2026-07-02).
- [x] RESOLVED: PyPI authentication fixed — code changes committed (5d4c5f6), workflow
  updated to use OIDC-only, version bumped to 22.0.2, setup guide added. Now requires
  user action: configure Trusted Publishing on PyPI (see docs/PYPI_TRUSTED_PUBLISHING_SETUP.md).
  Once configured, proceed to Phase 3b to tag v22.0.2 and test the release pipeline.

- [BLOCKED: awaiting user PyPI configuration] Phase 3b: Complete v22.0.2 release test —
  Once Phase 3a is complete (PyPI Trusted Publishing configured), tag v22.0.2 and test
  the full release pipeline:
    1. Tag `v22.0.2` (annotated): `git tag -a v22.0.2 -m "v22.0.2 — Trusted Publishing verification"`.
    2. Push the tag: `git push backup v22.0.2`.
    3. Watch the run: `gh run watch` (or Actions tab).
    4. Verify both PyPI publish job AND GitHub Release job succeed.
    5. Confirm 22.0.2 appears at pypi.org/pypi/sentinel-desktop and in GitHub Releases.
  Gate: release.yml run is green (all jobs), pypi.org shows 22.0.2, GitHub Release exists.
  This phase proves the Trusted Publishing pipeline works — after it, every future release
  (v22.1.0+) is one tag push away.


## Done

- [x] Phase 12: Detector-evasion pipeline — `core/humanize/detector_evasion.py` (NEW).
  Pluggable `DetectorEvasionPipeline` that wraps the stealth modules and applies
  a configurable ordered list of evasion strategies. Spec §"detector_evasion.py",
  Deliverable #8. Implements DetectorEvasionStrategy ABC, NoOpStrategy,
  FittsLawStrategy, OvershootStrategy, ErrorInjectionStrategy, MomentumScrollStrategy,
  AttentionSimulationStrategy, and DetectorEvasionPipeline with DEFAULT_STEALTH_PIPELINE.
  Gate: `tests/test_humanize_stealth_detector_evasion.py` passes (33 tests: pipeline
  applies strategies in order; no-op pipeline is passthrough; adding strategy changes
  output; per-strategy failure degrades gracefully; each strategy applies to relevant
  actions only; naturalistic profile bypass; missing context graceful degrade; default
  pipeline composition). ruff clean (fixed unused math import), all 8,718 tests passing.
  (commit a1d9e6b)

- [x] Phase 11: Stealth wiring at the chokepoints — modify `core/humanize/motion.py`
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
  Implemented all wiring: motion.py now accepts target_size and routes through
  Fitts's-Law timing and overshoot/correction for StealthProfile; typing.py
  accepts errors flag and routes through error injection; action_executor passes
  context parameters and applies attention pauses; desktop.click passes target_size
  and desktop.scroll uses momentum trajectory. ruff clean, all 8,705+ tests passing.
  (commit 5a401a9)

- [x] Phase 10: Biometric sampler — `core/humanize/biometric_sampler.py` (NEW).
  `sample_operator(session_log_path) -> BiometricStats` extracting real inter-key
  + inter-move distributions from a captured session, returning a dataclass the
  StealthProfile can consume. Spec §"biometric_sampler.py", Deliverable #2.
  IMPORTANT: the spec forbids inventing synthetic values — if no real samples
  exist, return None / raise a clear error, don't fake it. Gate:
  `tests/test_humanize_stealth_biometric.py` passes (parses a fixture session log
  into correct stats; returns None/raises on empty input; never synthesizes).
  Last of the leaf modules since it only feeds StealthProfile defaults.
  Implements BiometricStatistics dataclass, sample_operator() with JSONL parsing,
  analyze_events() extracting keystroke timing, move duration by target size,
  Fitts coefficient regression, overshoot rates, error rate, correction delays,
  scroll momentum decay, attention drift probability. 21 comprehensive tests:
  file not found, empty/insufficient samples, valid parsing, error-correction,
  attention drift, malformed input, no synthesis guarantee, analyze_events().
  ruff clean (4 lint fixes), all 8,726+ tests passing. (commit 4dc0813)
- [x] Phase 9: Attention drift + dwell — `core/humanize/attention.py` (NEW).
  `attention_pause(action_context, *, rng, profile) -> float` returning an
  occasional gaze-like pause, scaled by context (longer on ambiguous UI). Spec
  §"attention.py", Deliverable #7. Gate: `tests/test_humanize_stealth_attention.py`
  passes (pause probability, context-aware scaling, re-read pause branch, zero
  when disabled).
  Implements attention_pause() and re_read_pause() functions with context-aware
  probability (destructive 2×, password 1.5×, repetitive 0.5×), Gaussian duration
  sampling, StealthProfile-only activation, deterministic seeded RNG.
  19 comprehensive tests covering pause probability, context-aware scaling,
  re-read pauses, zero when disabled, determinism, duration bounds.
  ruff clean, all 8,810 tests passing. (commit bdd2c96)
- [x] Phase 8: Inertial scroll momentum — `core/humanize/scroll.py` (NEW).
  `momentum_scroll_trajectory()` producing exponential decay
  (`delta[t] = delta[0] * momentum^t`) with per-frame Gaussian jitter, 16ms base
  + 4ms/frame dwell timing, a 60-frame safety cap (~1s of momentum), a <1px
  stopping threshold, momentum clamped 0.0–1.0, and a single-discrete-scroll
  fallback for non-StealthProfile. Spec §"scroll.py", Deliverable #6. Gate:
  `tests/test_humanize_stealth_scroll.py` passes (22 tests: decay patterns for
  positive/negative deltas, jitter application, 60-frame cap, stopping threshold,
  naturalistic fallback, edge cases, momentum clamping, seed reproducibility).
  ruff clean, 8,810 tests passing. (commit 583851b)
- [x] Phase 7: Error + self-correction injection — `core/humanize/errors.py`
  (NEW). `inject_errors_and_corrections(text, *, rng, profile) -> list[(str,float)]`
  emitting mistype + backspace + correction sequences (40% adjacent-key, 30%
  shifted-case, 20% skip, 10% random), StealthProfile-only (naturalistic returns
  the text unchanged), no error on the first character. Spec §"errors.py",
  Deliverable #5. NOTE: built + unit-tested here, but NOT yet wired into the live
  type path — `desktop._humanized_type` calls `keystroke_delays(..., errors=False)`,
  so typing errors are dormant at runtime even under StealthProfile (see
  docs/superpowers/guides/stealth-mode-activation.md). Wiring is future work.
  Gate: `tests/test_humanize_stealth_errors.py` passes (20 tests: error-rate
  bounds, backspace handling, correction delays, seed reproducibility, adjacent-key
  mistypes, integration scenarios). ruff clean. (commit 59282a5)
- [x] Phase 6: Overshoot + sweep-back — `core/humanize/overshoot.py` (NEW).
  `overshoot_target(target, current, *, rng, profile, target_width_px) -> tuple`
  returning a point past the target (overshoot) or short of it (undershoot),
  probabilistically scaled by target size. Spec §"overshoot.py", Deliverable #4.
  Gate: `tests/test_humanize_stealth_overshoot.py` passes (overshoot probability
  scales inversely with target width; undershoot vs overshoot distribution;
  sweep-back lands within jitter of target). Depends on rng.py (exists) only.
  Implements overshoot probability scaling (60% small/30% medium/10% large),
  undershoot vs overshoot 50/50, miss magnitude scaling, correction jitter,
  non-StealthProfile fallback. 17 tests, all pass (8,702 total). ruff clean.
  (commit 89ad6a9)
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
