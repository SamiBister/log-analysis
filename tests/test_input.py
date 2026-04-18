"""Tests for logscope.input — all external I/O is mocked."""

from __future__ import annotations

from logscope.input import size_input


class TestLastLines:
    def test_last_keeps_tail_lines(self):
        text = "\n".join(str(i) for i in range(10))  # lines 0-9
        result = size_input(text, last=3, max_bytes=200_000, quiet=True)
        assert result == "7\n8\n9"

    def test_last_priority_over_max_bytes_when_small(self):
        """When last selects lines that fit within max_bytes, line count is respected."""
        text = "\n".join(["x" * 10] * 20)  # 20 lines × ~11 bytes = ~220 bytes
        result = size_input(text, last=2, max_bytes=200_000, quiet=True)
        lines = result.split("\n")
        assert len(lines) == 2

    def test_last_equal_to_line_count(self):
        text = "a\nb\nc"
        result = size_input(text, last=3, max_bytes=200_000, quiet=True)
        assert result == "a\nb\nc"

    def test_last_larger_than_line_count(self):
        text = "a\nb"
        result = size_input(text, last=100, max_bytes=200_000, quiet=True)
        assert result == "a\nb"

    def test_last_one_line(self):
        text = "a\nb\nc\nd"
        result = size_input(text, last=1, max_bytes=200_000, quiet=True)
        assert result == "d"


class TestMaxBytes:
    def test_short_input_returned_unchanged(self):
        text = "hello world"
        result = size_input(text, last=0, max_bytes=200_000, quiet=True)
        assert result == text

    def test_truncates_to_last_n_bytes(self):
        # 100 lines of 10 chars each = 1100 bytes including newlines
        lines = [f"line{i:04d}  " for i in range(100)]
        text = "\n".join(lines)
        result = size_input(text, last=0, max_bytes=100, quiet=True)
        assert len(result.encode()) <= 100

    def test_strips_incomplete_leading_line(self):
        """Byte slice may land in the middle of a line; that partial line is removed."""
        # Build input where slicing will produce a partial first line
        text = "PARTIAL_LINE\nfull line one\nfull line two\n"
        # Slice big enough to include part of PARTIAL_LINE but not from the start
        max_bytes = len(b"ARTIAL_LINE\nfull line one\nfull line two\n")
        result = size_input(text, last=0, max_bytes=max_bytes, quiet=True)
        assert not result.startswith("P")  # partial line removed
        assert "full line one" in result

    def test_exact_byte_boundary_on_newline(self):
        text = "aaaa\nbbbb\ncccc"
        # Keep exactly the last 9 bytes ("bbb\ncccc" after stripping partial)
        result = size_input(text, last=0, max_bytes=9, quiet=True)
        assert "cccc" in result

    def test_empty_input_unchanged(self):
        result = size_input("", last=0, max_bytes=200_000, quiet=True)
        assert result == ""


class TestLargeWarning:
    def test_warns_when_result_exceeds_threshold(self, capsys):
        big = "x" * 160_000
        size_input(big, last=0, max_bytes=200_000, quiet=False)
        captured = capsys.readouterr()
        assert "large" in captured.err.lower()

    def test_no_warn_when_quiet(self, capsys):
        big = "x" * 160_000
        size_input(big, last=0, max_bytes=200_000, quiet=True)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_no_warn_when_below_threshold(self, capsys):
        small = "x" * 1_000
        size_input(small, last=0, max_bytes=200_000, quiet=False)
        captured = capsys.readouterr()
        assert captured.err == ""


class TestValidation:
    def test_negative_max_bytes_raises(self):
        import pytest

        with pytest.raises(ValueError, match="max_bytes"):
            size_input("hello", last=0, max_bytes=-1, quiet=True)

    def test_zero_max_bytes_raises(self):
        import pytest

        with pytest.raises(ValueError, match="max_bytes"):
            size_input("hello", last=0, max_bytes=0, quiet=True)

    def test_negative_last_raises(self):
        import pytest

        with pytest.raises(ValueError, match="last"):
            size_input("hello", last=-1, max_bytes=200_000, quiet=True)

    def test_last_plus_byte_cap(self):
        """last selects lines, then max_bytes still caps the result."""
        # 5 lines × 100 chars = ~500 bytes; cap at 50 bytes
        lines = ["a" * 99 for _ in range(5)]
        text = "\n".join(lines)
        result = size_input(text, last=5, max_bytes=50, quiet=True)
        assert len(result.encode()) <= 50

    def test_strip_partial_line_preserves_content(self):
        """If stripping partial line would empty the result, keep the full slice."""
        # Single line with no internal newline — stripping should not empty result
        text = "no newline here at all"
        # Force byte truncation into this single line
        result = size_input(text, last=0, max_bytes=10, quiet=True)
        assert result  # must not be empty
