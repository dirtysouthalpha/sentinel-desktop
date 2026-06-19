"""Tests for installer/mdm.py — MDM deployment artefact generator (v19)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from installer.mdm import (
    _INTUNE_SETTINGS,
    OMA_URI_BASE,
    REGISTRY_BASE,
    _admx_value_type,
    build_admx,
    build_intune_profile,
)

# ---------------------------------------------------------------------------
# _admx_value_type helper
# ---------------------------------------------------------------------------


class TestAdmxValueType:
    def test_integer_maps_to_decimal(self):
        assert _admx_value_type("Integer") == "decimal"

    def test_boolean_maps_to_boolean(self):
        assert _admx_value_type("Boolean") == "boolean"

    def test_string_maps_to_text(self):
        assert _admx_value_type("String") == "text"

    def test_unknown_defaults_to_text(self):
        assert _admx_value_type("Unknown") == "text"


# ---------------------------------------------------------------------------
# Settings catalogue sanity
# ---------------------------------------------------------------------------


class TestSettingsCatalogue:
    def test_all_settings_have_four_fields(self):
        for entry in _INTUNE_SETTINGS:
            assert len(entry) == 4, f"Bad entry: {entry}"

    def test_no_duplicate_suffixes(self):
        suffixes = [s[1] for s in _INTUNE_SETTINGS]
        assert len(suffixes) == len(set(suffixes)), "Duplicate suffix keys"

    def test_data_types_are_valid(self):
        valid = {"Integer", "Boolean", "String"}
        for name, suffix, dtype, desc in _INTUNE_SETTINGS:
            assert dtype in valid, f"{suffix}: invalid dtype {dtype!r}"

    def test_descriptions_not_empty(self):
        for name, suffix, dtype, desc in _INTUNE_SETTINGS:
            assert desc.strip(), f"{suffix}: empty description"


# ---------------------------------------------------------------------------
# build_intune_profile
# ---------------------------------------------------------------------------


class TestBuildIntuneProfile:
    def test_creates_json_file(self, tmp_path):
        out = build_intune_profile(tmp_path)
        assert out.exists()
        assert out.suffix == ".json"

    def test_valid_json(self, tmp_path):
        out = build_intune_profile(tmp_path)
        data = json.loads(out.read_text("utf-8"))
        assert isinstance(data, dict)

    def test_contains_oma_settings(self, tmp_path):
        out = build_intune_profile(tmp_path)
        data = json.loads(out.read_text("utf-8"))
        assert "omaSettings" in data
        assert len(data["omaSettings"]) == len(_INTUNE_SETTINGS)

    def test_oma_uri_prefix(self, tmp_path):
        out = build_intune_profile(tmp_path)
        data = json.loads(out.read_text("utf-8"))
        for row in data["omaSettings"]:
            assert row["OMAUri"].startswith(OMA_URI_BASE), row["OMAUri"]

    def test_all_settings_have_display_name(self, tmp_path):
        out = build_intune_profile(tmp_path)
        data = json.loads(out.read_text("utf-8"))
        for row in data["omaSettings"]:
            assert "DisplayName" in row
            assert row["DisplayName"]

    def test_app_name_in_profile(self, tmp_path):
        out = build_intune_profile(tmp_path)
        data = json.loads(out.read_text("utf-8"))
        assert "Sentinel" in data["displayName"]

    def test_idempotent(self, tmp_path):
        """Second call overwrites, no duplicate-key error."""
        build_intune_profile(tmp_path)
        out = build_intune_profile(tmp_path)
        data = json.loads(out.read_text("utf-8"))
        assert len(data["omaSettings"]) == len(_INTUNE_SETTINGS)


# ---------------------------------------------------------------------------
# build_admx
# ---------------------------------------------------------------------------


class TestBuildAdmx:
    def test_creates_admx_and_adml(self, tmp_path):
        admx, adml = build_admx(tmp_path)
        assert admx.exists()
        assert adml.exists()
        assert admx.suffix == ".admx"
        assert adml.suffix == ".adml"

    def test_admx_is_valid_xml(self, tmp_path):
        admx, _ = build_admx(tmp_path)
        root = ET.fromstring(admx.read_text("utf-8"))
        assert root is not None

    def test_adml_is_valid_xml(self, tmp_path):
        _, adml = build_admx(tmp_path)
        root = ET.fromstring(adml.read_text("utf-8"))
        assert root is not None

    def test_admx_contains_policies_element(self, tmp_path):
        admx, _ = build_admx(tmp_path)
        root = ET.fromstring(admx.read_text("utf-8"))
        ns = "http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions"
        policies = root.find(f"{{{ns}}}policies")
        assert policies is not None

    def test_admx_policy_count_matches_settings(self, tmp_path):
        admx, _ = build_admx(tmp_path)
        root = ET.fromstring(admx.read_text("utf-8"))
        ns = "http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions"
        policies = root.find(f"{{{ns}}}policies")
        assert policies is not None
        policy_list = list(policies)
        # Boolean settings have no elements block, but are still policies
        assert len(policy_list) == len(_INTUNE_SETTINGS)

    def test_admx_registry_key_correct(self, tmp_path):
        admx, _ = build_admx(tmp_path)
        text = admx.read_text("utf-8")
        # HKLM\ prefix is stripped; only the SOFTWARE\... part should appear
        expected_key = REGISTRY_BASE.replace("HKLM\\", "")
        assert expected_key in text

    def test_adml_has_string_for_each_setting(self, tmp_path):
        _, adml = build_admx(tmp_path)
        text = adml.read_text("utf-8")
        for name, suffix, dtype, desc in _INTUNE_SETTINGS:
            policy_id = f"Sentinel_{suffix}"
            assert policy_id in text, f"Missing string for {policy_id}"

    def test_adml_supported_win10_string(self, tmp_path):
        _, adml = build_admx(tmp_path)
        text = adml.read_text("utf-8")
        assert "SUPPORTED_WIN10" in text

    def test_creates_output_dir_if_missing(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        assert not deep.exists()
        build_admx(deep)
        assert deep.exists()
