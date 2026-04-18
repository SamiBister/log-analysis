"""Tests for logscope.context."""

from __future__ import annotations

import pytest

from logscope.context import load_context


class TestLoadContext:
    def test_loads_small_file(self, tmp_path):
        f = tmp_path / "ctx.md"
        f.write_text("# Runbook\nDo the thing.\n")
        result = load_context(str(f), max_bytes=10_000, quiet=False)
        assert "Runbook" in result

    def test_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_context(str(tmp_path / "missing.md"), max_bytes=1000, quiet=False)

    def test_truncates_large_file(self, tmp_path):
        f = tmp_path / "big.md"
        content = "x" * 200
        f.write_bytes(content.encode())
        result = load_context(str(f), max_bytes=50, quiet=True)
        assert len(result.encode()) <= 50

    def test_truncation_warning_printed(self, tmp_path, capsys):
        f = tmp_path / "big.md"
        f.write_bytes(b"a" * 500)
        load_context(str(f), max_bytes=10, quiet=False)
        assert "truncated" in capsys.readouterr().err

    def test_truncation_warning_suppressed_when_quiet(self, tmp_path, capsys):
        f = tmp_path / "big.md"
        f.write_bytes(b"a" * 500)
        load_context(str(f), max_bytes=10, quiet=True)
        assert "truncated" not in capsys.readouterr().err

    def test_no_truncation_when_within_limit(self, tmp_path):
        f = tmp_path / "small.md"
        f.write_text("short content")
        result = load_context(str(f), max_bytes=10_000, quiet=False)
        assert result == "short content"

    def test_utf8_decode_with_replace_on_invalid_bytes(self, tmp_path):
        f = tmp_path / "binary.md"
        f.write_bytes(b"valid \xff invalid")
        result = load_context(str(f), max_bytes=10_000, quiet=True)
        assert "valid" in result  # should not raise
