"""Context file loading and truncation for logscope.

Loads an optional runbook or operations manual that is injected into the
first Copilot prompt as additional background context.
"""

from __future__ import annotations

import sys
from pathlib import Path


def load_context(path: str, max_bytes: int, quiet: bool) -> str:
    """Load a context file and truncate it to *max_bytes* if necessary.

    Args:
        path: Filesystem path to the context file.
        max_bytes: Maximum number of bytes to read.  If the file is larger
            the first *max_bytes* bytes are kept and a warning is printed
            to stderr (suppressed by ``quiet=True``).
        quiet: When True, suppress the truncation warning.

    Returns:
        Text content of the context file, possibly truncated.

    Raises:
        FileNotFoundError: If *path* does not exist.
        OSError: If the file cannot be read for any other I/O reason.
    """
    file_path = Path(path).resolve()  # resolve symlinks and .. for auditability
    if not file_path.exists():
        raise FileNotFoundError(f"Context file not found: {path}")

    raw = file_path.read_bytes()
    if len(raw) > max_bytes:
        if not quiet:
            sys.stderr.write(f"[logscope] Warning: context file truncated to {max_bytes} bytes\n")
        raw = raw[:max_bytes]

    return raw.decode("utf-8", errors="replace")
