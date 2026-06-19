"""Sentinel Profile — versioned, self-describing deployment bundles.

A profile is a directory containing a manifest (profile.json) plus optional
config, scripts, brain snapshot, and workflow files. It lets Sentinel be
pre-loaded with everything needed for a specific role (e.g. "field-it-tech")
and dropped onto any machine without manual setup.

Profiles are used by the portable build (Layer A) but also work with any
standard Sentinel installation: copy a profile directory in and adopt it.
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SENTINEL_VERSION = "20.0"  # updated with each release


@dataclass
class ProfileIncludes:
    config: str = "config.json"
    scripts_dir: str = "scripts"
    brain_snapshot: str = "brain-snapshot.jsonl"
    workflows_dir: str = "workflows"


@dataclass
class ProfileFlags:
    auto_adopt: bool = True
    secrets_redacted: bool = True


@dataclass
class Profile:
    """Parsed and validated profile manifest."""

    name: str
    label: str
    version: str
    sentinel_compat: str
    description: str
    includes: ProfileIncludes = field(default_factory=ProfileIncludes)
    flags: ProfileFlags = field(default_factory=ProfileFlags)
    path: Path | None = None  # resolved root directory of the profile

    @property
    def config_path(self) -> Path | None:
        if self.path and self.includes.config:
            p = self.path / self.includes.config
            return p if p.exists() else None
        return None

    @property
    def scripts_dir(self) -> Path | None:
        if self.path and self.includes.scripts_dir:
            p = self.path / self.includes.scripts_dir
            return p if p.is_dir() else None
        return None

    @property
    def brain_snapshot_path(self) -> Path | None:
        if self.path and self.includes.brain_snapshot:
            p = self.path / self.includes.brain_snapshot
            return p if p.exists() else None
        return None

    @property
    def workflows_dir(self) -> Path | None:
        if self.path and self.includes.workflows_dir:
            p = self.path / self.includes.workflows_dir
            return p if p.is_dir() else None
        return None


class ProfileError(Exception):
    """Raised when a profile cannot be loaded or is incompatible."""


def _parse_version(ver: str) -> tuple[int, ...]:
    """Parse a simple semver string like '20.0' or '>=17.0' into a tuple."""
    ver = ver.lstrip(">=<~^").strip()
    parts = ver.split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    return tuple(result)


def _is_compat(compat_expr: str, current: str) -> bool:
    """Check whether *current* satisfies *compat_expr* (only >= supported)."""
    if compat_expr.startswith(">="):
        required = _parse_version(compat_expr[2:])
        actual = _parse_version(current)
        return actual >= required
    # Unknown operator — warn and allow
    logger.warning("Unknown sentinel_compat operator in '%s'; allowing.", compat_expr)
    return True


def load_profile(path: str | Path) -> Profile:
    """Load and validate a profile from *path* (a profile directory or manifest).

    Args:
        path: Profile directory containing ``profile.json``, or the
              ``profile.json`` file itself.

    Returns:
        Validated :class:`Profile` instance.

    Raises:
        ProfileError: If the manifest is missing, malformed, or incompatible.
    """
    path = Path(path)
    if path.is_dir():
        manifest_path = path / "profile.json"
    else:
        manifest_path = path
        path = path.parent

    if not manifest_path.exists():
        raise ProfileError(f"Profile manifest not found: {manifest_path}")

    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Malformed profile manifest: {manifest_path}") from exc

    required = {"name", "label", "version", "sentinel_compat", "description"}
    missing = required - manifest.keys()
    if missing:
        raise ProfileError(f"Profile manifest missing fields: {missing}")

    compat = manifest["sentinel_compat"]
    if not _is_compat(compat, _SENTINEL_VERSION):
        logger.warning(
            "Profile '%s' requires sentinel_compat='%s' but current version is %s. "
            "Loading anyway — some features may not work.",
            manifest["name"],
            compat,
            _SENTINEL_VERSION,
        )

    raw_includes = manifest.get("includes", {})
    raw_flags = manifest.get("flags", {})

    return Profile(
        name=manifest["name"],
        label=manifest["label"],
        version=manifest["version"],
        sentinel_compat=compat,
        description=manifest["description"],
        includes=ProfileIncludes(
            config=raw_includes.get("config", "config.json"),
            scripts_dir=raw_includes.get("scripts_dir", "scripts"),
            brain_snapshot=raw_includes.get("brain_snapshot", "brain-snapshot.jsonl"),
            workflows_dir=raw_includes.get("workflows_dir", "workflows"),
        ),
        flags=ProfileFlags(
            auto_adopt=raw_flags.get("auto_adopt", True),
            secrets_redacted=raw_flags.get("secrets_redacted", True),
        ),
        path=path,
    )


def adopt_profile(profile: Profile, *, target_dir: str | Path, force: bool = False) -> None:
    """Copy profile assets into *target_dir* (the active Sentinel data directory).

    - Config is copied only if it does not already exist (or ``force=True``).
    - Scripts and workflows are merged (existing files are kept unless ``force``).
    - Never silently clobbers user data.

    Args:
        profile: A loaded :class:`Profile`.
        target_dir: Destination data directory (e.g. ``core.paths.data_dir()``).
        force: If True, overwrite existing files.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    if profile.config_path:
        dest = target / "config.json"
        if not dest.exists() or force:
            shutil.copy2(profile.config_path, dest)
            logger.info("Profile: copied config.json → %s", dest)
        else:
            logger.info("Profile: config.json already exists at %s — skipping.", dest)

    if profile.scripts_dir:
        dest_scripts = target / "scripts"
        dest_scripts.mkdir(parents=True, exist_ok=True)
        for src in profile.scripts_dir.iterdir():
            dest_file = dest_scripts / src.name
            if not dest_file.exists() or force:
                shutil.copy2(src, dest_file)
        logger.info("Profile: scripts merged into %s", dest_scripts)

    if profile.workflows_dir:
        dest_workflows = target / "workflows"
        dest_workflows.mkdir(parents=True, exist_ok=True)
        for src in profile.workflows_dir.iterdir():
            dest_file = dest_workflows / src.name
            if not dest_file.exists() or force:
                shutil.copy2(src, dest_file)
        logger.info("Profile: workflows merged into %s", dest_workflows)


_DETECT_ORDER = (
    "cli",          # --profile arg (caller responsibility to pass)
    "embedded",     # profiles/ next to exe
    "dropped",      # ./sentinel-profile/ next to exe
    "env",          # SENTINEL_PROFILE env var
)


def detect_profile(*, cli_arg: str | None = None) -> "Profile | None":
    """Discover an available profile using the documented search order.

    Search order:
    1. ``--profile`` CLI argument (*cli_arg*).
    2. ``profiles/*/profile.json`` next to the executable (embedded).
    3. ``./sentinel-profile/`` dropped alongside the exe.
    4. ``SENTINEL_PROFILE`` environment variable.

    Returns the first valid profile found, or ``None``.
    """
    import os
    import sys

    exe_dir = Path(sys.executable).parent

    # 1. CLI arg
    if cli_arg:
        try:
            return load_profile(cli_arg)
        except ProfileError as exc:
            logger.warning("CLI --profile '%s' failed to load: %s", cli_arg, exc)

    # 2. Embedded profiles/ directory next to exe
    embedded_profiles = exe_dir / "profiles"
    if embedded_profiles.is_dir():
        for profile_dir in sorted(embedded_profiles.iterdir()):
            if profile_dir.is_dir() and (profile_dir / "profile.json").exists():
                try:
                    return load_profile(profile_dir)
                except ProfileError as exc:
                    logger.debug("Embedded profile '%s' skipped: %s", profile_dir.name, exc)

    # 3. Dropped profile folder next to exe
    dropped = exe_dir / "sentinel-profile"
    if dropped.is_dir():
        try:
            return load_profile(dropped)
        except ProfileError as exc:
            logger.debug("Dropped profile at %s skipped: %s", dropped, exc)

    # 4. SENTINEL_PROFILE env var
    env_path = os.environ.get("SENTINEL_PROFILE")
    if env_path:
        try:
            return load_profile(env_path)
        except ProfileError as exc:
            logger.warning("SENTINEL_PROFILE='%s' failed to load: %s", env_path, exc)

    return None
