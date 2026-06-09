"""Tests for v13.0 Credential Vault + Registry integration."""

from __future__ import annotations

import sys

import pytest

from core.action_schemas import (
    ACTION_MODELS,
    CredReadAction,
    CredStoreAction,
    RegistryDeleteAction,
    RegistryReadAction,
    RegistryWriteAction,
)
from core.tool_schemas import TOOLS

# ── Schema registration tests ────────────────────────────────────────


class TestCredSchemas:
    def test_registered(self):
        assert "cred_store" in ACTION_MODELS
        assert "cred_read" in ACTION_MODELS

    def test_cred_store_valid(self):
        a = CredStoreAction(action="cred_store", key="api_key", value="secret")
        assert a.key == "api_key"

    def test_cred_read_valid(self):
        a = CredReadAction(action="cred_read", key="api_key")
        assert a.key == "api_key"


class TestRegistrySchemas:
    def test_registered(self):
        for name in ["registry_read", "registry_write", "registry_delete"]:
            assert name in ACTION_MODELS

    def test_registry_read_defaults(self):
        a = RegistryReadAction(action="registry_read", path="HKLM\\Software")
        assert a.value_name == ""

    def test_registry_write_defaults(self):
        a = RegistryWriteAction(
            action="registry_write",
            path="HKCU\\Software\\Test",
            value_name="foo",
            data="bar",
        )
        assert a.reg_type == "REG_SZ"

    def test_registry_delete_optional_value(self):
        a = RegistryDeleteAction(
            action="registry_delete", path="HKCU\\Software\\Test",
        )
        assert a.value_name is None


# ── Executor dispatch tests ──────────────────────────────────────────


class TestCredExecutor:
    def test_dispatch_entries(self):
        from core.action_executor import ActionExecutor
        assert "cred_store" in ActionExecutor._dispatch_table
        assert "cred_read" in ActionExecutor._dispatch_table

    def test_store_and_read(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        store = executor._cred_store(
            key="test_v13_key", value="test_v13_val",
        )
        assert store["success"] is True
        read = executor._cred_read(key="test_v13_key")
        assert read["success"] is True
        assert read["output"] == "test_v13_val"
        # Cleanup
        from core.encryption import CredentialVault
        vault = CredentialVault()
        vault.delete("test_v13_key")

    def test_read_missing(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        result = executor._cred_read(key="nonexistent_key_xyz")
        assert result["success"] is False
        assert result["error"] == "cred_not_found"


class TestRegistryExecutor:
    def test_dispatch_entries(self):
        from core.action_executor import ActionExecutor
        for name in ["registry_read", "registry_write", "registry_delete"]:
            assert name in ActionExecutor._dispatch_table

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Windows-only",
    )
    def test_read_known_value(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        # Read a value that always exists on Windows
        result = executor._registry_read(
            path="HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion",
            value_name="ProductName",
        )
        assert result["success"] is True
        assert "Windows" in str(result["output"])

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Windows-only",
    )
    def test_write_read_delete_cycle(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        path = "HKCU\\SOFTWARE\\SentinelTest_v13"
        # Write
        w = executor._registry_write(
            path=path, value_name="TestVal", data="hello",
        )
        assert w["success"] is True
        # Read back
        r = executor._registry_read(path=path, value_name="TestVal")
        assert r["success"] is True
        # Delete value
        d = executor._registry_delete(path=path, value_name="TestVal")
        assert d["success"] is True
        # Delete key
        d2 = executor._registry_delete(path=path)
        assert d2["success"] is True

    def test_read_invalid_path(self):
        from core.action_executor import ActionExecutor
        executor = ActionExecutor.__new__(ActionExecutor)
        result = executor._registry_read(
            path="INVALID_HIVE\\NoSuch\\Path", value_name="x",
        )
        assert result["success"] is False


# ── Tool schema tests ────────────────────────────────────────────────


class TestCredToolSchemas:
    def test_all_tools_exist(self):
        names = [t["function"]["name"] for t in TOOLS]
        for tool in ["cred_store", "cred_read"]:
            assert tool in names

    def test_cred_store_params(self):
        tool = next(
            t for t in TOOLS
            if t["function"]["name"] == "cred_store"
        )
        props = tool["function"]["parameters"]["properties"]
        assert "key" in props
        assert "value" in props


class TestRegistryToolSchemas:
    def test_all_tools_exist(self):
        names = [t["function"]["name"] for t in TOOLS]
        for tool in ["registry_read", "registry_write", "registry_delete"]:
            assert tool in names

    def test_registry_write_params(self):
        tool = next(
            t for t in TOOLS
            if t["function"]["name"] == "registry_write"
        )
        props = tool["function"]["parameters"]["properties"]
        assert "path" in props
        assert "value_name" in props
        assert "data" in props
        assert "reg_type" in props
