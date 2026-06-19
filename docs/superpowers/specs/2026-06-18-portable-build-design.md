# Design Spec — Portable + Pre-loaded Build (Sentinel Desktop v18.x)

**Status:** Design only — not yet implemented.
**Date:** 2026-06-18
**Author:** Sentinel (design) / Brandon (product)
**Depends on:** `2026-06-18-neuralis-brain-bridge-design.md` (the `brain-snapshot.jsonl`
offline cache is a brain-bridge artifact).

---

## Overview

Let Brandon **drag-and-drop a single, pre-loaded, badass Sentinel** onto a server or
workstation and double-click to start fixing issues — no Python install, no dependency
fetch, no separate Tesseract setup, already carrying his config, his 19 IT scripts, and a
snapshot of fleet brain knowledge for offline recall.

This is **two layers stacked**, each building on existing machinery:

- **Layer A — Sentinel Profile:** a versioned, self-describing directory that carries
  everything that makes a Sentinel *ready*. Highest value-to-effort ratio; drops onto
  any Sentinel (portable or installed).
- **Layer B — Portable Build:** a `--portable` target extending the **existing**
  `installer/build.py` PyInstaller pipeline. Produces a self-contained folder (no
  installer, no registry writes) with Tesseract bundled and a default profile embedded.

### Honest constraint (must be stated up front)

Sentinel is a **vision-driven desktop automation agent**. Its power is seeing pixels and
moving a real cursor in a GUI session. So "drag onto servers" fully applies to servers
reached via **RDP / GUI console** — not to SSH-only headless boxes (for those, the
existing SSH/netops tooling is the right fit and a portable GUI build is overkill). The
portable build targets the RDP/console case.

PyInstaller builds **per-OS**. There is no single cross-platform portable file for this
dependency set. We produce `SentinelDesktop-portable-windows/` and
`SentinelDesktop-portable-linux/` as separate artifacts. Claiming otherwise would be a
lie; this spec doesn't.

### Decisions already made (do not re-litigate)

- **Both layers**, as a layered product: portable build ships with a default badass
  profile embedded.
- **Build target extends existing `installer/build.py`** — not a new build system.
- **Per-OS builds** accepted.
- **Playwright bundling is opt-out** — it's huge and not always needed on a fix job.

---

## Architecture

```
   build: python installer/build.py --portable [--profile field-it-tech] [--no-playwright]
                         │
        ┌────────────────┴────────────────┐
        ▼ Layer B (packaging)             ▼ Layer A (content)
   PyInstaller --onedir                 profiles/field-it-tech/
   + Tesseract binary bundled             ├── profile.json (manifest)
   + English traineddata bundled          ├── config.json
   + embedded profile copied in           ├── scripts/ (19 IT scripts)
   + config → ./portable_data/            ├── brain-snapshot.jsonl (offline cache)
   (NOT %APPDATA%)                        └── workflows/
        │
        ▼
   dist/SentinelDesktop-portable-<os>/
   ├── SentinelDesktop(.exe)
   ├── _internal/  (PyInstaller bundle: python, deps, tesseract, tessdata)
   ├── profiles/field-it-tech/   (embedded default profile)
   └── portable_data/            (writable: config, checkpoints, logs)
```

At runtime, Sentinel detects it's running portably (presence of `./portable_data/` or a
`--portable` marker file) and **redirects all storage to that folder** instead of
`%APPDATA%` / `~/.sentinel-desktop`. It also auto-adopts an embedded or dropped profile.

---

## Components

### Layer A — `core/profile.py` + `profiles/`

A new **Profile** concept: a directory with a manifest.

**`profiles/field-it-tech/profile.json`** (manifest schema):
```json
{
  "name": "field-it-tech",
  "label": "Field IT Tech (default badass)",
  "version": "1.0.0",
  "sentinel_compat": ">=17.0",
  "description": "Pre-loaded for IT support on servers & workstations.",
  "includes": {
    "config": "config.json",
    "scripts_dir": "scripts",
    "brain_snapshot": "brain-snapshot.jsonl",
    "workflows_dir": "workflows"
  },
  "flags": {
    "auto_adopt": true,
    "secrets_redacted": true
  }
}
```

**`core/profile.py`** responsibilities:
- `load_profile(path) -> Profile` — validate manifest, check `sentinel_compat`.
- `adopt_profile(profile, *, target_dir)` — copy config/scripts/workflows into the active
  Sentinel's data dir; **never overwrite** existing user config unless `force=True`.
- `detect_profile() -> Profile | None` — search order: (1) `--profile` CLI arg,
  (2) `./profiles/*/profile.json` next to the exe (embedded), (3) a dropped
  `./sentinel-profile/` folder, (4) `SENTINEL_PROFILE` env var.
- `brain_snapshot` loading is delegated to the brain bridge (see *Dependency on Brain
  Bridge*) — this layer only carries the file; `core/brain/snapshot.py` (later) reads it.

**`scripts/` in the profile** — the existing 19 IT scripts
(`scripts/it_support/*.json`: account_unlock, disk_cleanup, dns_flush, …) are copied in.
Custom user scripts can be added; the manifest `scripts_dir` points the script engine at
them.

**`brain-snapshot.jsonl`** — an offline cache of selected brain thoughts (the most useful
N entries per region) for recall when the box can't reach homeserver. **This is produced
by the brain bridge** (`core/brain/snapshot.py`, future). The profile layer only carries
and points to it. Until the bridge ships, this field is optional/empty.

**Secrets handling:** `config.json` in a profile carries the LLM provider/model/theme but
the **API key is redacted** (`secrets_redacted: true`); first run prompts for the key and
stores it in `portable_data/`. We do not ship keys inside a portable build.

### Layer B — `installer/build.py` `--portable` target

Extends the existing build script (which today does `--exe` / `--installer` / `--all`).
New function `build_portable(profile="field-it-tech", bundle_playwright=True) -> bool`:

- **PyInstaller `--onedir`** (not `--onefile`). Faster startup, easier debugging, and
  lets the profile folder sit naturally alongside the binary. (Current `build_exe` uses
  `--onefile`.)
- **No Inno Setup step** — no installer, no registry writes, no admin rights. Output is a
  folder the user copies/USBs anywhere.
- **Bundle Tesseract** — locate the Tesseract binary + `eng.traineddata` at build time
  (via `pytesseract.pytesseract.tesseract_cmd` or a `TESSERACT_BIN` env/arg), copy into
  the bundle, and patch `core/ocr.py` to resolve the bundled path when running portably.
  This is the main capability the current build lacks (OCR silently unavailable without a
  separate Tesseract install).
- **Embed the default profile** — copy `profiles/<profile>/` into the output folder.
- **Config-next-to-exe** — drop a `portable_data/` folder marker; runtime storage
  resolver (below) writes there instead of `%APPDATA%`.
- **`--no-playwright` flag** — skip bundling Playwright + browsers (saves hundreds of MB).
  Web actions then degrade as they do today when Playwright isn't installed.
- **`--profile <name>` flag** — which profile to embed (default `field-it-tech`).

CLI additions to `installer/build.py` argparse: `--portable`, `--profile`, `--no-playwright`,
`--tesseract-bin <path>` (auto-detected if unset).

### Runtime: shared storage resolver (required refactor)

Today, config-path logic is **duplicated** in `config.py` (line 88) and
`core/checkpoint.py` (line 29) — both compute `APPDATA/SentinelDesktop` or
`~/.sentinel-desktop`. For portability we need **one** resolver that redirects when
portable. Proposed `core/paths.py`:

```python
def is_portable() -> bool: ...        # ./portable_data/ marker next to exe
def data_dir() -> Path:               # single source of truth
    return _exe_sibling("portable_data") if is_portable() else _default_dir()
def config_path() -> Path: return data_dir() / "config.json"
def checkpoint_dir() -> Path: return data_dir() / "checkpoints"
```

`config.py` and `core/checkpoint.py` are refactored to call `core.paths` (behavior
unchanged in the non-portable case → existing tests stay green). This is the one place
this spec touches existing modules, and it's a pure extraction with identical default
behavior.

---

## Data flow

**Build time:**
1. `python installer/build.py --portable` → `build_portable()`.
2. PyInstaller `--onedir` bundles Python + deps (minus Playwright if `--no-playwright`).
3. Tesseract + `eng.traineddata` copied into `_internal/`.
4. `profiles/field-it-tech/` copied in; `brain-snapshot.jsonl` included if present.
5. `portable_data/` marker folder created (empty, writable).
6. Output: `dist/SentinelDesktop-portable-<os>/`.

**Run time (on the target box):**
1. User copies the folder to the server/workstation, double-clicks the exe.
2. `core.paths.is_portable()` detects the marker → storage redirects to `portable_data/`.
3. `core.profile.detect_profile()` finds the embedded profile → adopts it (copies scripts
   in, loads config — prompting for the redacted API key on first run).
4. `core/brain/snapshot.py` (when it exists) loads `brain-snapshot.jsonl` for offline
   recall; live brain ops still attempt homeserver and degrade if unreachable.
5. Sentinel runs as a full badass instance: OCR works (bundled Tesseract), scripts are
   loaded, config persists in the folder (travels with the USB stick).

---

## Error handling & graceful degradation

| Failure | Behavior |
|---------|----------|
| Tesseract binary not found at build | Warn + build anyway (OCR degrades at runtime, as today). |
| Tesseract not bundled (older build) | `core/ocr.py` falls back to system Tesseract / marks OCR unavailable. |
| Profile manifest missing/invalid | Log + start with defaults; don't crash. |
| Profile `sentinel_compat` mismatch | Warn; load anyway but flag in GUI. |
| `brain-snapshot.jsonl` missing | Skip offline cache; live recall still attempted. |
| `portable_data/` not writable | Fall back to `%APPDATA%`/`~/.sentinel-desktop` with a warning. |
| Playwright not bundled | Web actions degrade exactly as today when Playwright is absent. |
| Adopting profile would overwrite user config | Refuse unless `force`; never silently clobber. |

---

## Testing plan

All additions are new files; the one existing-module touch (`core/paths.py` extraction)
preserves identical default behavior so existing tests stay green.

**`tests/test_profile.py`**:
- `test_load_valid_profile`, `test_load_missing_manifest_raises`,
  `test_compat_mismatch_warns`.
- `test_adopt_copies_scripts`, `test_adopt_no_clobber_existing_config`,
  `test_adopt_force_overwrites`.
- `test_detect_embedded_profile`, `test_detect_dropped_folder`,
  `test_detect_cli_arg_wins`, `test_detect_env_var`, `test_detect_none_when_absent`.

**`tests/test_paths.py`**:
- `test_default_dir_non_portable` — matches today's `%APPDATA%`/`~` resolution (parity).
- `test_is_portable_true_with_marker`, `test_is_portable_false_without`.
- `test_data_dir_redirects_when_portable`.
- `test_config_and_checkpoint_use_shared_resolver` — the dedup guarantee.

**`tests/test_build_portable.py`** (build logic, mocked PyInstaller subprocess):
- `test_build_portable_invokes_onedir` — assert `--onedir` in the PyInstaller call.
- `test_build_portable_no_inno_setup` — assert Inno step NOT invoked.
- `test_tesseract_bundled_when_found`, `test_tesseract_missing_warns_not_fails`.
- `test_profile_embedded`, `test_no_playwright_skips_browsers`.
- `test_portable_data_marker_created`.

Existing tests (`test_main_and_build.py`) keep passing because the non-portable path is
unchanged; new tests run under the same `pytest tests/ -q` harness.

---

## Dependency on Brain Bridge

This spec **references** the brain bridge but does not block on it:
- The profile **carries** `brain-snapshot.jsonl`; the brain bridge **produces** it (via a
  future `core/brain/snapshot.py`). Until the bridge ships, the field is optional/empty
  and offline recall is simply unavailable — everything else in the portable build works.
- Build order: the portable build can ship **before** the brain bridge; the snapshot slot
  is filled in later with no profile-manifest change (it's already in the schema).

---

## Open questions

1. **Tesseract licensing/attribution** — bundling Tesseract + traineddata requires
   carrying its LICENSE. Confirm the bundle includes it (it's Apache-2.0/BSD-3; fine, but
   must be included).
2. **Size budget** — a `--onedir` bundle + Tesseract + (optional) Playwright can exceed
   300–500 MB. Acceptable for Brandon's use? If not, `--no-playwright` + minimal
   traineddata (English only) is the default lean path.
3. **Code signing** — unsigned exes trigger SmartScreen on customer boxes. Out of scope
   here, but flagged: a signed build is a future ops task, not a code task.
4. **Profile secrets** — proposal redacts the API key and prompts on first run. Confirm
   Brandon is OK with that (vs. an encrypted key bundled with a passphrase).
5. **Update path** — how does a portable instance update? Proposal: re-drop a new folder;
   `portable_data/` is preserved by copying it aside. Needs a real story before v1.

---

## Out of scope (this phase)

- **A single cross-platform portable file** — not possible with this dep set; per-OS only.
- **Code signing / notarization** — ops task, separate effort.
- **Auto-update mechanism** for portable instances — future.
- **Brain snapshot generation** itself — lives in the brain bridge
  (`core/brain/snapshot.py`), separate spec.
- **Headless/SSH-only server support** — wrong tool; use existing netops.
- **New runtime dependencies** — bundling is a build-time concern; runtime adds none.

---

## Recommended build order (within this spec)

1. `core/paths.py` extraction + refactor `config.py`/`core/checkpoint.py` to use it;
   `test_paths.py` proving parity. (Do this first — it unblocks everything and is low-risk.)
2. `core/profile.py` + `profiles/field-it-tech/` skeleton + `test_profile.py`.
3. `installer/build.py` `build_portable()` + `test_build_portable.py`.
4. Tesseract bundling + `core/ocr.py` portable-path resolution.
5. Profile embedding + first-run key prompt.
6. End-to-end: build on Windows, copy to a fresh dir, run, verify OCR + scripts + config
   persistence in `portable_data/`.
