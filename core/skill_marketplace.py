"""Sentinel Desktop v21 — Skill Marketplace.

A local registry of shareable, versioned automation scripts ("skills").
Each skill is a JSON manifest plus a script file that can be replayed
by the ScriptEngine.

Skills are stored under ``~/.sentinel/marketplace/<name>/``:
  ``<name>/manifest.json`` — SkillManifest metadata
  ``<name>/script.json``   — automation script (ScriptEngine format)

Usage::

    from core.skill_marketplace import SkillMarketplace

    mp = SkillMarketplace()
    mp.install_skill(manifest, script)
    skills = mp.list_skills()
    manifest, script = mp.get_skill("open_notepad")
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MARKETPLACE = Path.home() / ".sentinel" / "marketplace"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SkillManifest:
    """Metadata describing a marketplace skill.

    Attributes:
        name: Unique identifier (alphanumeric, underscores, hyphens).
        description: Short human-readable purpose.
        version: Semantic version string (e.g. ``"1.0.0"``).
        author: Author name or handle.
        category: Grouping category (e.g. ``"web"``, ``"file"``, ``"system"``).
        script_file: Relative path to the script JSON (default: ``script.json``).
        tags: Searchable tag list.
        created: ISO 8601 creation timestamp.
    """

    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    category: str = "general"
    script_file: str = "script.json"
    tags: list[str] = field(default_factory=list)
    created: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillManifest:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            category=data.get("category", "general"),
            script_file=data.get("script_file", "script.json"),
            tags=data.get("tags", []),
            created=data.get("created", ""),
        )


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------


class SkillMarketplace:
    """Local skill registry: list, install, export, and uninstall skills.

    Args:
        marketplace_dir: Root directory for skill storage.  Defaults to
            ``~/.sentinel/marketplace/``.
    """

    def __init__(self, marketplace_dir: Path | None = None) -> None:
        self._root = Path(marketplace_dir or _DEFAULT_MARKETPLACE)
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_skills(self, category: str | None = None) -> list[SkillManifest]:
        """Return all installed skills, optionally filtered by *category*.

        Args:
            category: When provided, only skills whose category matches
                (case-insensitive) are returned.

        Returns:
            Sorted list of :class:`SkillManifest` objects.
        """
        manifests: list[SkillManifest] = []
        for manifest_path in sorted(self._root.glob("*/manifest.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                m = SkillManifest.from_dict(data)
                if category is None or m.category.lower() == category.lower():
                    manifests.append(m)
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                logger.warning("skill_marketplace: bad manifest %s: %s", manifest_path, exc)
        return manifests

    def find_skills(self, query: str) -> list[SkillManifest]:
        """Full-text search across name, description, and tags.

        Args:
            query: Search string (case-insensitive).

        Returns:
            Skills whose name, description, or tags contain *query*.
        """
        query_lower = query.lower()
        results: list[SkillManifest] = []
        for m in self.list_skills():
            haystack = " ".join(
                [m.name, m.description, m.category] + m.tags
            ).lower()
            if query_lower in haystack:
                results.append(m)
        return results

    # ------------------------------------------------------------------
    # Install / uninstall
    # ------------------------------------------------------------------

    def install_skill(
        self,
        manifest: SkillManifest,
        script: dict[str, Any] | None = None,
        script_path: str | None = None,
    ) -> Path:
        """Install a skill into the marketplace.

        Args:
            manifest: Skill metadata.  ``manifest.created`` is set to now
                if empty.
            script: Skill script dict (mutually exclusive with *script_path*).
            script_path: Path to an existing script JSON to copy.

        Returns:
            Path to the installed skill directory.

        Raises:
            ValueError: If neither *script* nor *script_path* is provided.
        """
        if not manifest.created:
            manifest.created = datetime.now(timezone.utc).isoformat()

        skill_dir = self._root / manifest.name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write manifest
        manifest_file = skill_dir / "manifest.json"
        manifest_file.write_text(
            json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
        )

        # Write or copy script
        target_script = skill_dir / (manifest.script_file or "script.json")
        if script is not None:
            target_script.write_text(json.dumps(script, indent=2), encoding="utf-8")
        elif script_path is not None:
            import shutil

            shutil.copy2(script_path, target_script)
        else:
            raise ValueError("install_skill requires either script or script_path")

        logger.info(
            "skill_marketplace: installed '%s' v%s → %s",
            manifest.name,
            manifest.version,
            skill_dir,
        )
        return skill_dir

    def uninstall_skill(self, name: str) -> bool:
        """Remove a skill by *name*.

        Returns:
            True if removed, False if not found.
        """
        import shutil

        skill_dir = self._root / name
        if not skill_dir.exists():
            return False
        shutil.rmtree(skill_dir)
        logger.info("skill_marketplace: uninstalled '%s'", name)
        return True

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get_skill(self, name: str) -> tuple[SkillManifest, dict[str, Any]]:
        """Load a skill's manifest and script by *name*.

        Returns:
            Tuple of (manifest, script_dict).

        Raises:
            FileNotFoundError: If the skill is not installed.
        """
        skill_dir = self._root / name
        manifest_path = skill_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Skill not found: {name!r}")

        manifest = SkillManifest.from_dict(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        script_path = skill_dir / (manifest.script_file or "script.json")
        script: dict[str, Any] = {}
        if script_path.exists():
            try:
                script = json.loads(script_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                logger.warning("skill_marketplace: bad script for '%s': %s", name, exc)
        return manifest, script

    def export_skill(self, name: str) -> dict[str, Any]:
        """Export a skill as a single portable dict.

        The returned dict has ``manifest`` and ``script`` keys and can
        be passed directly back to :meth:`install_skill`.

        Returns:
            ``{"manifest": {...}, "script": {...}}``.
        """
        manifest, script = self.get_skill(name)
        return {"manifest": manifest.to_dict(), "script": script}


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_marketplace: SkillMarketplace | None = None


def get_marketplace() -> SkillMarketplace:
    """Return the process-wide :class:`SkillMarketplace` singleton."""
    global _marketplace
    if _marketplace is None:
        _marketplace = SkillMarketplace()
    return _marketplace
