"""Tests for core.web.appliance — cert whitelist handling."""

from __future__ import annotations

from pathlib import Path

from core.web.appliance import (
    is_whitelisted,
    load_whitelist,
    save_whitelist,
    should_ignore_cert_errors,
)


class TestIsWhitelisted:
    def test_exact_match(self):
        assert is_whitelisted("192.168.1.1", ["192.168.1.1", "10.0.0.1"]) is True

    def test_no_match(self):
        assert is_whitelisted("172.16.0.1", ["192.168.1.1", "10.0.0.1"]) is False

    def test_case_insensitive(self):
        assert is_whitelisted("Firewall.local", ["firewall.local"]) is True

    def test_wildcard_suffix(self):
        assert is_whitelisted("router.local", ["*.local"]) is True

    def test_wildcard_no_match(self):
        assert is_whitelisted("router.com", ["*.local"]) is False

    def test_empty_whitelist(self):
        assert is_whitelisted("192.168.1.1", []) is False

    def test_none_whitelist_loads_from_disk(self):
        """When whitelist=None, loads from disk (file may not exist)."""
        # Just verify it doesn't crash
        result = is_whitelisted("192.168.1.1", whitelist=None)
        assert isinstance(result, bool)


class TestShouldIgnoreCertErrors:
    def test_https_whitelisted(self):
        assert (
            should_ignore_cert_errors(
                "https://192.168.1.1/login",
                ["192.168.1.1"],
            )
            is True
        )

    def test_https_not_whitelisted(self):
        assert (
            should_ignore_cert_errors(
                "https://192.168.1.1/login",
                ["10.0.0.1"],
            )
            is False
        )

    def test_url_with_port(self):
        assert (
            should_ignore_cert_errors(
                "https://firewall.local:8443/admin",
                ["firewall.local"],
            )
            is True
        )

    def test_http_url(self):
        assert (
            should_ignore_cert_errors(
                "http://192.168.1.1/",
                ["192.168.1.1"],
            )
            is True
        )

    def test_ip_only_url(self):
        assert (
            should_ignore_cert_errors(
                "10.0.0.1/config",
                ["10.0.0.1"],
            )
            is True
        )

    def test_empty_url(self):
        assert should_ignore_cert_errors("", ["10.0.0.1"]) is False

    def test_malformed_url(self):
        assert should_ignore_cert_errors("://broken", ["*"]) is False


class TestSaveLoadWhitelist:
    def test_save_and_load(self, tmp_path: Path):
        filepath = tmp_path / "cert_whitelist.json"
        save_whitelist(["192.168.1.1", "10.0.0.1", "firewall.local"], filepath)

        loaded = load_whitelist(filepath)
        assert "192.168.1.1" in loaded
        assert "10.0.0.1" in loaded
        assert "firewall.local" in loaded

    def test_save_deduplicates(self, tmp_path: Path):
        filepath = tmp_path / "cert_whitelist.json"
        save_whitelist(["a.local", "b.local", "a.local"], filepath)

        loaded = load_whitelist(filepath)
        assert loaded.count("a.local") == 1

    def test_save_sorts(self, tmp_path: Path):
        filepath = tmp_path / "cert_whitelist.json"
        save_whitelist(["z.local", "a.local", "m.local"], filepath)

        loaded = load_whitelist(filepath)
        assert loaded == ["a.local", "m.local", "z.local"]

    def test_load_missing_file(self, tmp_path: Path):
        filepath = tmp_path / "nonexistent.json"
        loaded = load_whitelist(filepath)
        assert loaded == []

    def test_load_invalid_json(self, tmp_path: Path):
        filepath = tmp_path / "bad.json"
        filepath.write_text("not valid json{{{")
        loaded = load_whitelist(filepath)
        assert loaded == []

    def test_save_creates_directory(self, tmp_path: Path):
        filepath = tmp_path / "subdir" / "cert_whitelist.json"
        save_whitelist(["10.0.0.1"], filepath)
        assert filepath.exists()
