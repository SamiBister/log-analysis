"""Tests for logscope.update — no real network calls."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from logscope import update as update_module
from logscope._meta import __commit__, __version__
from logscope.update import check_for_update

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(sha: str, status: int = 200) -> MagicMock:
    """Build a fake urllib response context manager."""
    body = json.dumps({"sha": sha}).encode()
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckForUpdate:
    def test_returns_update_available_when_sha_differs(self):
        different_sha = "0" * 40
        assert different_sha != __commit__

        mock_resp = _make_response(different_sha)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = check_for_update()

        assert "new version is available" in result
        assert "git pull" in result

    def test_returns_up_to_date_when_sha_matches(self):
        mock_resp = _make_response(__commit__)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = check_for_update()

        assert "latest version" in result
        assert __version__ in result

    def test_returns_empty_string_on_url_error(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = check_for_update()

        assert result == ""

    def test_returns_empty_string_on_timeout(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            result = check_for_update()

        assert result == ""

    def test_returns_empty_string_on_non_200_status(self):
        mock_resp = _make_response("anysha", status=404)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = check_for_update()

        assert result == ""

    def test_returns_empty_string_on_bad_json(self):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"not-json{{{"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp):
            result = check_for_update()

        assert result == ""

    def test_returns_empty_string_on_missing_sha_key(self):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({"no_sha_here": True}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp):
            result = check_for_update()

        assert result == ""

    def test_github_api_url_is_module_constant(self):
        assert hasattr(update_module, "GITHUB_API_URL")
        assert "logscope" in update_module.GITHUB_API_URL

    def test_update_available_message_format(self):
        different_sha = "a" * 40
        mock_resp = _make_response(different_sha)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = check_for_update()

        assert result == (
            "[logscope] A new version is available.\n  To update: git pull && uv sync"
        )

    def test_up_to_date_message_format(self):
        mock_resp = _make_response(__commit__)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = check_for_update()

        assert result == f"[logscope] You are on the latest version ({__version__})."
