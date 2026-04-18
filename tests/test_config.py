"""Tests for logscope.config — all file I/O is mocked."""

from __future__ import annotations

from logscope.config import (
    LogscopeConfig,
    load_config,
    merge_config,
    resolve_config_path,
)


# ---------------------------------------------------------------------------
# resolve_config_path
# ---------------------------------------------------------------------------
class TestResolveConfigPath:
    def test_path_is_xdg_config(self):
        p = resolve_config_path()
        assert str(p).endswith("/.config/logscope/config.toml")


# ---------------------------------------------------------------------------
# load_config — no file (auto-creates)
# ---------------------------------------------------------------------------
class TestLoadConfigNoFile:
    def test_returns_defaults_when_no_file(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg = load_config(cfg_path)
        assert cfg.model == "claude-sonnet-4-6"
        assert cfg.redact is True
        assert cfg.max_bytes == 200_000
        assert cfg.quiet is False
        assert cfg.translate is True

    def test_creates_config_file_with_defaults(self, tmp_path):
        cfg_path = tmp_path / "subdir" / "config.toml"
        load_config(cfg_path)
        assert cfg_path.exists()
        content = cfg_path.read_text()
        assert "claude-sonnet-4-6" in content

    def test_auto_creates_config_dir(self, tmp_path):
        cfg_path = tmp_path / "new" / "nested" / "config.toml"
        load_config(cfg_path)
        assert cfg_path.parent.is_dir()


# ---------------------------------------------------------------------------
# load_config — existing valid file
# ---------------------------------------------------------------------------
class TestLoadConfigFromFile:
    def test_loads_and_merges_toml_values(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text(
            "[redaction]\nenabled = true\npii = true\n\n[input]\nmax_bytes = 100000\n"
        )
        cfg = load_config(cfg_path)
        assert cfg.redact_pii is True
        assert cfg.max_bytes == 100_000

    def test_model_override(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text('model = "gpt-4o"\n')
        cfg = load_config(cfg_path)
        assert cfg.model == "gpt-4o"

    def test_unknown_keys_ignored(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text('model = "gpt-4o"\nunknown_key = "surprise"\n')
        cfg = load_config(cfg_path)
        assert cfg.model == "gpt-4o"

    def test_partial_file_keeps_defaults_for_missing(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text('model = "gpt-4o"\n')
        cfg = load_config(cfg_path)
        assert cfg.max_bytes == 200_000
        assert cfg.quiet is False

    def test_hosts_flag_loaded(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[redaction]\nhosts = true\n")
        cfg = load_config(cfg_path)
        assert cfg.redact_hosts is True

    def test_output_section(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[output]\nquiet = true\ntranslate = false\n")
        cfg = load_config(cfg_path)
        assert cfg.quiet is True
        assert cfg.translate is False

    def test_context_section(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text('[context]\nfile = "/tmp/ops.md"\nmax_bytes = 10000\n')
        cfg = load_config(cfg_path)
        assert cfg.context_file == "/tmp/ops.md"
        assert cfg.max_context_bytes == 10_000


# ---------------------------------------------------------------------------
# load_config — malformed TOML
# ---------------------------------------------------------------------------
class TestLoadConfigMalformed:
    def test_malformed_toml_falls_back_to_defaults(self, tmp_path, capsys):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("this is not valid = toml [\n")
        cfg = load_config(cfg_path)
        # Should return defaults
        assert cfg.model == "claude-sonnet-4-6"
        assert cfg.max_bytes == 200_000

    def test_malformed_toml_prints_warning(self, tmp_path, capsys):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[[broken\n")
        load_config(cfg_path)
        captured = capsys.readouterr()
        assert "malformed" in captured.err.lower() or "warning" in captured.err.lower()

    def test_no_crash_on_malformed(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("not valid toml !!!###\n")
        cfg = load_config(cfg_path)
        assert isinstance(cfg, LogscopeConfig)


# ---------------------------------------------------------------------------
# merge_config — CLI flag overrides
# ---------------------------------------------------------------------------
class TestMergeConfig:
    def _base(self) -> LogscopeConfig:
        return LogscopeConfig()

    def test_model_override(self):
        cfg = merge_config(self._base(), {"model": "gpt-4o"})
        assert cfg.model == "gpt-4o"

    def test_none_does_not_override(self):
        base = LogscopeConfig(model="gpt-4o")
        cfg = merge_config(base, {"model": None})
        assert cfg.model == "gpt-4o"

    def test_no_redact_sets_redact_false(self):
        base = LogscopeConfig(redact=True)
        cfg = merge_config(base, {"no_redact": True})
        assert cfg.redact is False

    def test_no_redact_false_does_not_disable(self):
        base = LogscopeConfig(redact=True)
        cfg = merge_config(base, {"no_redact": False})
        assert cfg.redact is True

    def test_redact_pii_flag(self):
        cfg = merge_config(self._base(), {"redact_pii": True})
        assert cfg.redact_pii is True

    def test_redact_hosts_flag(self):
        cfg = merge_config(self._base(), {"redact_hosts": True})
        assert cfg.redact_hosts is True

    def test_redact_ips_flag(self):
        cfg = merge_config(self._base(), {"redact_ips": True})
        assert cfg.redact_ips is True

    def test_max_bytes_override(self):
        cfg = merge_config(self._base(), {"max_bytes": 50_000})
        assert cfg.max_bytes == 50_000

    def test_quiet_override(self):
        cfg = merge_config(self._base(), {"quiet": True})
        assert cfg.quiet is True

    def test_unset_flag_preserves_config(self):
        base = LogscopeConfig(model="gpt-4o", quiet=True)
        cfg = merge_config(base, {"model": None, "quiet": None})
        assert cfg.model == "gpt-4o"
        assert cfg.quiet is True

    def test_translate_false_override(self):
        cfg = merge_config(self._base(), {"translate": False})
        assert cfg.translate is False

    def test_context_file_override(self):
        cfg = merge_config(self._base(), {"context_file": "/ops/runbook.md"})
        assert cfg.context_file == "/ops/runbook.md"

    def test_max_context_bytes_override(self):
        cfg = merge_config(self._base(), {"max_context_bytes": 10_000})
        assert cfg.max_context_bytes == 10_000

    def test_empty_args_returns_unchanged_config(self):
        base = LogscopeConfig(model="gpt-4.1")
        cfg = merge_config(base, {})
        assert cfg.model == "gpt-4.1"


# ---------------------------------------------------------------------------
# Validation — clamping and model name guard
# ---------------------------------------------------------------------------
class TestValidation:
    def test_invalid_max_bytes_clamped_to_default(self, tmp_path, capsys):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[input]\nmax_bytes = 0\n")
        cfg = load_config(cfg_path)
        assert cfg.max_bytes == 200_000
        assert "max_bytes" in capsys.readouterr().err

    def test_negative_last_clamped_to_zero(self, tmp_path, capsys):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[input]\nlast = -3\n")
        cfg = load_config(cfg_path)
        assert cfg.last == 0

    def test_zero_min_value_length_clamped(self, tmp_path, capsys):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[redaction]\nmin_value_length = 0\n")
        cfg = load_config(cfg_path)
        assert cfg.min_value_length == 8

    def test_invalid_model_name_falls_back_to_default(self, tmp_path, capsys):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text('model = "../../evil"\n')
        cfg = load_config(cfg_path)
        assert cfg.model == "claude-sonnet-4-6"
        assert "invalid model" in capsys.readouterr().err

    def test_valid_model_name_accepted(self, tmp_path):
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text('model = "gpt-4o"\n')
        cfg = load_config(cfg_path)
        assert cfg.model == "gpt-4o"

    def test_oserror_on_create_prints_warning(self, tmp_path, capsys):
        """If directory creation fails, a warning is printed and defaults returned."""
        import unittest.mock as mock

        cfg_path = tmp_path / "noperm" / "config.toml"
        with mock.patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")):
            cfg = load_config(cfg_path)
        assert cfg.model == "claude-sonnet-4-6"
        assert "warning" in capsys.readouterr().err.lower()

    def test_default_toml_derives_from_dataclass(self):
        """_default_toml() output should be parseable and match LogscopeConfig defaults."""
        import tomllib

        from logscope.config import _default_toml

        parsed = tomllib.loads(_default_toml())
        assert parsed["model"] == "claude-sonnet-4-6"
        assert parsed["input"]["max_bytes"] == 200_000
