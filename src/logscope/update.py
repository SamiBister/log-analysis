"""Update checker for logscope."""

import json
import urllib.error
import urllib.request

from logscope._meta import __commit__, __version__

GITHUB_API_URL = "https://api.github.com/repos/logscope-project/logscope/commits/main"

_TIMEOUT = 2
_MAX_RESPONSE_BYTES = 65_536  # 64 KiB — far more than the GitHub commits API returns

# Sentinel values that indicate the build did not inject a real commit SHA
_UNSET_COMMIT_SENTINELS = {"", "unknown", "dev"}


def check_for_update() -> str:
    """Check whether a newer version of logscope is available on GitHub.

    Fetches the latest commit SHA from the GitHub API and compares it against
    the commit SHA baked into this installation at build time.

    Returns:
        A human-readable message string:

        - If a different (newer) commit exists upstream:
          ``"[logscope] A new version is available.\\n  To update: git pull && uv sync"``
        - If the local commit already matches the upstream HEAD:
          ``"[logscope] You are on the latest version (<version>)."``
        - On **any** network or HTTP error (timeout, connection refused,
          non-200 status, malformed JSON, missing key): returns ``""`` so that
          the caller can silently skip printing anything.
        - If ``__commit__`` is a placeholder/unset sentinel: returns ``""``
          to avoid spurious "update available" messages on dev installs.
    """
    # Guard: skip update check if the build didn't inject a real commit SHA
    if __commit__ in _UNSET_COMMIT_SENTINELS:
        return ""

    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            # urlopen raises HTTPError for 4xx/5xx; this guard handles edge cases
            # (e.g. 201/204) that wouldn't raise but are also not success 200.
            if resp.status != 200:
                return ""
            data = json.loads(resp.read(_MAX_RESPONSE_BYTES))
        latest_sha: str = data["sha"]
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        KeyError,
    ):
        return ""

    if latest_sha != __commit__:
        return "[logscope] A new version is available.\n  To update: git pull && uv sync"
    return f"[logscope] You are on the latest version ({__version__})."
