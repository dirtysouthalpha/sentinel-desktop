"""Tests for core/skill_marketplace.py (v21 skill marketplace)."""

from __future__ import annotations

import json

import pytest

from core.skill_marketplace import SkillManifest, SkillMarketplace, get_marketplace


@pytest.fixture()
def marketplace(tmp_path) -> SkillMarketplace:
    return SkillMarketplace(marketplace_dir=tmp_path / "marketplace")


def _manifest(name: str = "open_notepad", **kw) -> SkillManifest:
    defaults = {
        "description": "Open Notepad and type some text",
        "version": "1.0.0",
        "author": "test",
        "category": "system",
        "tags": ["notepad", "text"],
    }
    defaults.update(kw)
    return SkillManifest(name=name, **defaults)


def _script() -> dict:
    return {
        "name": "open_notepad",
        "steps": [{"action": "screenshot", "params": {}}],
    }


class TestSkillManifest:
    def test_to_dict(self):
        m = _manifest()
        d = m.to_dict()
        assert d["name"] == "open_notepad"
        assert d["category"] == "system"

    def test_from_dict_roundtrip(self):
        m = _manifest()
        d = m.to_dict()
        m2 = SkillManifest.from_dict(d)
        assert m2.name == m.name
        assert m2.tags == m.tags

    def test_from_dict_defaults(self):
        m = SkillManifest.from_dict({"name": "x", "description": "y"})
        assert m.version == "1.0.0"
        assert m.category == "general"
        assert m.tags == []


class TestSkillMarketplaceInstall:
    def test_install_creates_files(self, marketplace, tmp_path):
        m = _manifest()
        skill_dir = marketplace.install_skill(m, script=_script())
        assert (skill_dir / "manifest.json").exists()
        assert (skill_dir / "script.json").exists()

    def test_manifest_created_set(self, marketplace):
        m = _manifest()
        assert m.created == ""
        marketplace.install_skill(m, script=_script())
        assert m.created != ""

    def test_install_without_script_raises(self, marketplace):
        m = _manifest()
        with pytest.raises(ValueError):
            marketplace.install_skill(m)

    def test_install_with_script_path(self, marketplace, tmp_path):
        script_file = tmp_path / "my_script.json"
        script_file.write_text(json.dumps(_script()), encoding="utf-8")
        m = _manifest("by_path")
        marketplace.install_skill(m, script_path=str(script_file))
        _, loaded_script = marketplace.get_skill("by_path")
        assert loaded_script["name"] == "open_notepad"


class TestSkillMarketplaceList:
    def test_list_empty(self, marketplace):
        assert marketplace.list_skills() == []

    def test_list_returns_installed(self, marketplace):
        marketplace.install_skill(_manifest("a"), script=_script())
        marketplace.install_skill(_manifest("b", category="web"), script=_script())
        skills = marketplace.list_skills()
        assert len(skills) == 2

    def test_list_filtered_by_category(self, marketplace):
        marketplace.install_skill(_manifest("a", category="system"), script=_script())
        marketplace.install_skill(_manifest("b", category="web"), script=_script())
        system_skills = marketplace.list_skills(category="system")
        assert len(system_skills) == 1
        assert system_skills[0].name == "a"

    def test_list_category_case_insensitive(self, marketplace):
        marketplace.install_skill(_manifest("a", category="System"), script=_script())
        assert len(marketplace.list_skills(category="system")) == 1


class TestSkillMarketplaceFind:
    def test_find_by_name(self, marketplace):
        marketplace.install_skill(_manifest("open_notepad"), script=_script())
        results = marketplace.find_skills("notepad")
        assert len(results) == 1

    def test_find_by_tag(self, marketplace):
        marketplace.install_skill(_manifest("a", tags=["browser", "web"]), script=_script())
        marketplace.install_skill(_manifest("b", tags=["file"]), script=_script())
        results = marketplace.find_skills("browser")
        assert len(results) == 1
        assert results[0].name == "a"

    def test_find_by_description(self, marketplace):
        m = SkillManifest(name="x", description="resize the application window")
        marketplace.install_skill(m, script=_script())
        results = marketplace.find_skills("resize")
        assert len(results) == 1

    def test_find_no_match(self, marketplace):
        marketplace.install_skill(_manifest(), script=_script())
        assert marketplace.find_skills("xyzzy_nonexistent") == []


class TestSkillMarketplaceGet:
    def test_get_returns_manifest_and_script(self, marketplace):
        marketplace.install_skill(_manifest(), script=_script())
        manifest, script = marketplace.get_skill("open_notepad")
        assert manifest.name == "open_notepad"
        assert "steps" in script

    def test_get_missing_raises(self, marketplace):
        with pytest.raises(FileNotFoundError):
            marketplace.get_skill("ghost")


class TestSkillMarketplaceExport:
    def test_export_returns_bundle(self, marketplace):
        marketplace.install_skill(_manifest(), script=_script())
        bundle = marketplace.export_skill("open_notepad")
        assert "manifest" in bundle
        assert "script" in bundle
        assert bundle["manifest"]["name"] == "open_notepad"

    def test_export_missing_raises(self, marketplace):
        with pytest.raises(FileNotFoundError):
            marketplace.export_skill("ghost")


class TestSkillMarketplaceUninstall:
    def test_uninstall_removes_directory(self, marketplace):
        marketplace.install_skill(_manifest(), script=_script())
        assert marketplace.uninstall_skill("open_notepad") is True
        assert marketplace.list_skills() == []

    def test_uninstall_missing_returns_false(self, marketplace):
        assert marketplace.uninstall_skill("ghost") is False


class TestSkillNameValidation:
    """Path-traversal hardening: install/uninstall/get/export must reject
    names that could escape the marketplace root."""

    @pytest.mark.parametrize(
        "bad_name",
        [
            "../../etc/evil",
            "..",
            "../../../",
            "/etc/passwd",
            "sub/../../escape",
            "lead/slash",
            "trailing/slash/",
            ".hidden",
            "-flag",
            "",
            "has space",
            "shell;rm",
        ],
    )
    def test_install_rejects_bad_name(self, marketplace, bad_name):
        with pytest.raises(ValueError):
            marketplace.install_skill(
                SkillManifest(name=bad_name, description="x"), script=_script()
            )

    @pytest.mark.parametrize("bad_name", ["../../", "..", "/etc/p", "-x", "a/b"])
    def test_uninstall_rejects_bad_name(self, marketplace, bad_name):
        with pytest.raises(ValueError):
            marketplace.uninstall_skill(bad_name)

    @pytest.mark.parametrize("bad_name", ["../../", "..", "/etc/p", "-x", "a/b"])
    def test_get_rejects_bad_name(self, marketplace, bad_name):
        with pytest.raises(ValueError):
            marketplace.get_skill(bad_name)

    def test_uninstall_traversal_does_not_touch_filesystem(self, marketplace, tmp_path):
        """The worst case: a traversal name reaching shutil.rmtree must fail
        before any filesystem deletion happens."""
        sentinel = tmp_path / "canary"
        sentinel.write_text("alive", encoding="utf-8")
        # Build a name that, unguarded, would resolve above the marketplace root.
        evil = "../" * 10
        with pytest.raises(ValueError):
            marketplace.uninstall_skill(evil)
        assert sentinel.read_text(encoding="utf-8") == "alive"

    @pytest.mark.parametrize("good_name", ["a", "open_notepad", "web.v2", "skill-1", "v2_0"])
    def test_valid_names_accepted(self, marketplace, good_name):
        skill_dir = marketplace.install_skill(
            SkillManifest(name=good_name, description="x"), script=_script()
        )
        assert skill_dir.exists()


class TestGetMarketplaceSingleton:
    def test_returns_same_instance(self):
        m1 = get_marketplace()
        m2 = get_marketplace()
        assert m1 is m2

    def test_is_marketplace_instance(self):
        assert isinstance(get_marketplace(), SkillMarketplace)
