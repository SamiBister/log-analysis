"""Log input sizing for logscope.

Provides ``size_input`` which trims the raw log text to fit within the
configured line/byte budget before it is sent to the redaction engine.
"""

from __future__ import annotations

import sys

_LARGE_WARN_THRESHOLD = 150_000  # bytes — warn if result is still this big


def size_input(text: str, last: int, max_bytes: int, quiet: bool) -> str:
    """Trim *text* to fit the configured line or byte budget.

    Priority:
    1. If ``last > 0`` — keep the last *last* lines (``\\n``-split).
       A byte cap of *max_bytes* is still applied afterwards so a very
       large number of long lines cannot bypass the budget.
    2. Otherwise — keep the last *max_bytes* bytes, stripping any
       incomplete leading line that results from the byte slice.

    After sizing, if the result is still larger than 150 000 bytes a
    warning is printed to stderr (suppressed when ``quiet=True``).

    Args:
        text: Raw log text to trim.
        last: Number of lines to keep from the tail. 0 = use byte mode.
        max_bytes: Maximum number of bytes to keep. Must be > 0.
        quiet: When True, suppress the large-log warning.

    Returns:
        The trimmed log text.

    Raises:
        ValueError: If *max_bytes* is not positive.
    """
    if max_bytes <= 0:
        raise ValueError(f"max_bytes must be positive, got {max_bytes}")
    if last < 0:
        raise ValueError(f"last must be non-negative, got {last}")

    if last > 0:
        result = _keep_last_lines(text, last)
        # Still honour the byte budget after line selection
        result = _keep_last_bytes(result, max_bytes)
    else:
        result = _keep_last_bytes(text, max_bytes)

    encoded_result = result.encode()
    if not quiet and len(encoded_result) > _LARGE_WARN_THRESHOLD:
        kb = len(encoded_result) // 1024
        sys.stderr.write(f"[logscope] Warning: log is large ({kb} KB), truncating\n")

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _keep_last_lines(text: str, n: int) -> str:
    """Return the last *n* lines of *text*.

    Args:
        text: Input string.
        n: Number of lines to keep.

    Returns:
        String containing only the last *n* lines, joined with ``\\n``.
    """
    lines = text.split("\n")
    return "\n".join(lines[-n:])


def _keep_last_bytes(text: str, max_bytes: int) -> str:
    """Return the last *max_bytes* bytes of *text*, stripping any partial leading line.

    After slicing to *max_bytes* bytes the first (potentially incomplete)
    line is discarded so the consumer always receives whole lines.  If
    stripping the partial line would discard all content, the full slice
    is returned unchanged.

    Args:
        text: Input string.
        max_bytes: Maximum byte length of the returned string.

    Returns:
        Trimmed string with no partial leading line.
    """
    encoded = text.encode()
    if len(encoded) <= max_bytes:
        return text

    sliced = encoded[-max_bytes:]
    decoded = sliced.decode(errors="replace")

    # Strip incomplete leading line, but never discard everything
    newline_pos = decoded.find("\n")
    if newline_pos != -1:
        trimmed = decoded[newline_pos + 1 :]
        decoded = trimmed if trimmed else decoded

    return decoded
