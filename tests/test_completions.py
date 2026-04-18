"""Tests for logscope.completions."""

from __future__ import annotations

import pytest

from logscope.completions import emit


class TestEmitBash:
    def test_returns_non_empty_string(self):
        result = emit("bash")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_logscope(self):
        assert "logscope" in emit("bash")

    def test_contains_model_flag(self):
        assert "--model" in emit("bash")

    def test_contains_all_static_model_values(self):
        script = emit("bash")
        for model in ("claude-sonnet-4-6", "claude-opus-4-6", "gpt-4o", "gpt-4.1"):
            assert model in script, f"model {model!r} not found in bash completion"

    def test_contains_complete_directive(self):
        assert "complete -F _logscope_complete logscope" in emit("bash")

    def test_contains_subcommands(self):
        script = emit("bash")
        for sub in ("config", "update", "completions"):
            assert sub in script

    def test_contains_global_flags(self):
        script = emit("bash")
        for flag in ("--file", "--redact-pii", "--no-redact", "--quiet", "--version"):
            assert flag in script


class TestEmitZsh:
    def test_returns_non_empty_string(self):
        result = emit("zsh")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_logscope(self):
        assert "logscope" in emit("zsh")

    def test_contains_model_flag(self):
        assert "--model" in emit("zsh")

    def test_contains_all_static_model_values(self):
        script = emit("zsh")
        for model in ("claude-sonnet-4-6", "claude-opus-4-6", "gpt-4o", "gpt-4.1"):
            assert model in script, f"model {model!r} not found in zsh completion"

    def test_contains_compdef_directive(self):
        assert "compdef _logscope logscope" in emit("zsh")

    def test_contains_config_subcommands(self):
        script = emit("zsh")
        # config sub-subcommands present
        for sub in ("show", "edit", "path"):
            assert sub in script

    def test_contains_config_show_description(self):
        # "config show" implied by 'show' appearing alongside config context
        script = emit("zsh")
        assert "show" in script
        assert "config" in script

    def test_contains_global_flags(self):
        script = emit("zsh")
        for flag in ("--file", "--redact-pii", "--no-redact", "--quiet", "--version"):
            assert flag in script


class TestEmitInvalidShell:
    def test_raises_value_error_for_unknown_shell(self):
        with pytest.raises(ValueError, match="fish"):
            emit("fish")

    def test_raises_value_error_for_empty_string(self):
        with pytest.raises(ValueError):
            emit("")

    def test_bash_and_zsh_do_not_raise(self):
        # Smoke test — must not raise
        emit("bash")
        emit("zsh")
