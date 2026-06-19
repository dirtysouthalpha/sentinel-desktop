"""Tests for portable-mode startup: profile adoption and first-run API key prompt."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# needs_api_key
# ---------------------------------------------------------------------------


class TestNeedsApiKey:
    def _profile(self, *, secrets_redacted: bool) -> object:
        from core.profile import Profile, ProfileFlags, ProfileIncludes

        return Profile(
            name="test",
            label="Test",
            version="1.0",
            sentinel_compat=">=20.0",
            description="Test profile",
            flags=ProfileFlags(auto_adopt=True, secrets_redacted=secrets_redacted),
        )

    def test_true_when_redacted_and_key_empty(self):
        from core.profile import needs_api_key

        profile = self._profile(secrets_redacted=True)
        assert needs_api_key(profile, {"api_key": ""}) is True

    def test_true_when_redacted_and_key_absent(self):
        from core.profile import needs_api_key

        profile = self._profile(secrets_redacted=True)
        assert needs_api_key(profile, {}) is True

    def test_false_when_not_redacted(self):
        from core.profile import needs_api_key

        profile = self._profile(secrets_redacted=False)
        assert needs_api_key(profile, {}) is False

    def test_false_when_key_present(self):
        from core.profile import needs_api_key

        profile = self._profile(secrets_redacted=True)
        assert needs_api_key(profile, {"api_key": "sk-real-key"}) is False


# ---------------------------------------------------------------------------
# _save_api_key
# ---------------------------------------------------------------------------


class TestSaveApiKey:
    def test_creates_file_when_missing(self, tmp_path):
        from main import _save_api_key

        cfg = tmp_path / "config.json"
        _save_api_key("sk-new", cfg)
        data = json.loads(cfg.read_text())
        assert data["api_key"] == "sk-new"

    def test_merges_with_existing_keys(self, tmp_path):
        from main import _save_api_key

        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"provider": "openai", "api_key": ""}))
        _save_api_key("sk-updated", cfg)
        data = json.loads(cfg.read_text())
        assert data["api_key"] == "sk-updated"
        assert data["provider"] == "openai"

    def test_creates_parent_dirs(self, tmp_path):
        from main import _save_api_key

        cfg = tmp_path / "sub" / "deep" / "config.json"
        _save_api_key("sk-x", cfg)
        assert cfg.exists()


# ---------------------------------------------------------------------------
# _portable_startup
# ---------------------------------------------------------------------------


def _make_args(**kwargs) -> Namespace:
    defaults = {"api": False, "command": None, "profile": None, "debug": False}
    defaults.update(kwargs)
    return Namespace(**defaults)


def _make_fake_profile(tmp_path: Path, *, secrets_redacted: bool = True, auto_adopt: bool = True):
    """Create a minimal fake Profile instance."""
    from core.profile import Profile, ProfileFlags, ProfileIncludes

    return Profile(
        name="field-it-tech",
        label="Field IT Tech",
        version="1.0",
        sentinel_compat=">=20.0",
        description="Test",
        flags=ProfileFlags(auto_adopt=auto_adopt, secrets_redacted=secrets_redacted),
        path=tmp_path / "profiles" / "field-it-tech",
    )


class TestPortableStartup:
    def test_skips_when_not_portable(self, tmp_path):
        """_portable_startup is a no-op when is_portable() returns False."""
        with patch("core.paths.is_portable", return_value=False), \
             patch("core.profile.detect_profile") as mock_detect:
            from main import _portable_startup

            _portable_startup(_make_args())
        mock_detect.assert_not_called()

    def test_adopts_profile_when_portable(self, tmp_path):
        """adopt_profile() is called when portable + profile found + auto_adopt=True."""
        import main as main_mod

        profile = _make_fake_profile(tmp_path, secrets_redacted=False)

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=tmp_path / "data"), \
             patch("core.profile.detect_profile", return_value=profile), \
             patch("core.profile.adopt_profile") as mock_adopt, \
             patch("core.profile.needs_api_key", return_value=False):
            from main import _portable_startup

            _portable_startup(_make_args())

        mock_adopt.assert_called_once_with(profile, target_dir=tmp_path / "data")

    def test_skips_adopt_when_auto_adopt_false(self, tmp_path):
        """When profile has auto_adopt=False, adopt_profile() is NOT called."""
        import main as main_mod

        profile = _make_fake_profile(tmp_path, auto_adopt=False)

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=tmp_path / "data"), \
             patch("core.profile.detect_profile", return_value=profile), \
             patch("core.profile.adopt_profile") as mock_adopt:
            from main import _portable_startup

            _portable_startup(_make_args())

        mock_adopt.assert_not_called()

    def test_skips_adopt_when_no_profile(self, tmp_path):
        """When no profile is detected, adopt_profile() is NOT called."""
        import main as main_mod

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=tmp_path / "data"), \
             patch("core.profile.detect_profile", return_value=None), \
             patch("core.profile.adopt_profile") as mock_adopt:
            from main import _portable_startup

            _portable_startup(_make_args())

        mock_adopt.assert_not_called()

    def test_prompts_and_saves_key_gui_mode(self, tmp_path):
        """In GUI mode, _prompt_api_key is called and key is saved when needed."""
        import main as main_mod

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        profile = _make_fake_profile(tmp_path, secrets_redacted=True)

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=data_dir), \
             patch("core.profile.detect_profile", return_value=profile), \
             patch("core.profile.adopt_profile"), \
             patch("core.profile.needs_api_key", return_value=True), \
             patch.object(main_mod, "_prompt_api_key", return_value="sk-entered") as mock_prompt, \
             patch.object(main_mod, "_save_api_key") as mock_save:
            from main import _portable_startup

            _portable_startup(_make_args(command=None, api=False))

        mock_prompt.assert_called_once_with(is_gui=True)
        mock_save.assert_called_once()
        assert mock_save.call_args[0][0] == "sk-entered"

    def test_prompts_cli_mode_when_command_given(self, tmp_path):
        """In CLI mode (--command), _prompt_api_key is called with is_gui=False."""
        import main as main_mod

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        profile = _make_fake_profile(tmp_path, secrets_redacted=True)

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=data_dir), \
             patch("core.profile.detect_profile", return_value=profile), \
             patch("core.profile.adopt_profile"), \
             patch("core.profile.needs_api_key", return_value=True), \
             patch.object(main_mod, "_prompt_api_key", return_value="sk-cli") as mock_prompt, \
             patch.object(main_mod, "_save_api_key"):
            from main import _portable_startup

            _portable_startup(_make_args(command="open notepad"))

        mock_prompt.assert_called_once_with(is_gui=False)

    def test_api_mode_uses_env_var(self, tmp_path):
        """In API mode, SENTINEL_API_KEY env var is used instead of a prompt."""
        import main as main_mod
        import os

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        profile = _make_fake_profile(tmp_path, secrets_redacted=True)

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=data_dir), \
             patch("core.profile.detect_profile", return_value=profile), \
             patch("core.profile.adopt_profile"), \
             patch("core.profile.needs_api_key", return_value=True), \
             patch.dict(os.environ, {"SENTINEL_API_KEY": "sk-from-env"}), \
             patch.object(main_mod, "_prompt_api_key") as mock_prompt, \
             patch.object(main_mod, "_save_api_key") as mock_save:
            from main import _portable_startup

            _portable_startup(_make_args(api=True))

        mock_prompt.assert_not_called()
        mock_save.assert_called_once_with("sk-from-env", data_dir / "config.json")

    def test_api_mode_no_env_var_logs_warning(self, tmp_path):
        """In API mode with no SENTINEL_API_KEY, a warning is logged and no save."""
        import main as main_mod
        import os

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        profile = _make_fake_profile(tmp_path, secrets_redacted=True)

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=data_dir), \
             patch("core.profile.detect_profile", return_value=profile), \
             patch("core.profile.adopt_profile"), \
             patch("core.profile.needs_api_key", return_value=True), \
             patch.dict(os.environ, {}, clear=True), \
             patch.object(main_mod, "_save_api_key") as mock_save:
            from main import _portable_startup

            _portable_startup(_make_args(api=True))

        mock_save.assert_not_called()

    def test_no_prompt_when_key_already_saved(self, tmp_path):
        """No prompt occurs when config already has an api_key."""
        import main as main_mod

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cfg = data_dir / "config.json"
        cfg.write_text(json.dumps({"api_key": "sk-existing"}))
        profile = _make_fake_profile(tmp_path, secrets_redacted=True)

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=data_dir), \
             patch("core.profile.detect_profile", return_value=profile), \
             patch("core.profile.adopt_profile"), \
             patch("core.profile.needs_api_key", return_value=False), \
             patch.object(main_mod, "_prompt_api_key") as mock_prompt:
            from main import _portable_startup

            _portable_startup(_make_args())

        mock_prompt.assert_not_called()

    def test_skips_save_when_prompt_returns_none(self, tmp_path):
        """When the user skips the prompt, _save_api_key is NOT called."""
        import main as main_mod

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        profile = _make_fake_profile(tmp_path, secrets_redacted=True)

        with patch("core.paths.is_portable", return_value=True), \
             patch("core.paths.data_dir", return_value=data_dir), \
             patch("core.profile.detect_profile", return_value=profile), \
             patch("core.profile.adopt_profile"), \
             patch("core.profile.needs_api_key", return_value=True), \
             patch.object(main_mod, "_prompt_api_key", return_value=None), \
             patch.object(main_mod, "_save_api_key") as mock_save:
            from main import _portable_startup

            _portable_startup(_make_args())

        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# parse_args: --profile flag
# ---------------------------------------------------------------------------


class TestParseArgsProfile:
    def test_profile_arg_defaults_to_none(self):
        from main import parse_args

        with patch.object(sys, "argv", ["sentinel-desktop"]):
            args = parse_args()
        assert args.profile is None

    def test_profile_arg_parsed(self):
        from main import parse_args

        with patch.object(sys, "argv", ["sentinel-desktop", "--profile", "/path/to/profile"]):
            args = parse_args()
        assert args.profile == "/path/to/profile"
