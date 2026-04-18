"""Tests for logscope.translate — no external I/O, all pure functions."""

from __future__ import annotations

from logscope.translate import build_translation_map, translate


class TestTranslate:
    def test_single_host_label_translated(self):
        tmap = {"host-A": "web-prod-03"}
        assert translate("check host-A for errors", tmap) == "check web-prod-03 for errors"

    def test_multiple_host_labels_translated(self):
        tmap = {"host-A": "web-prod-03", "host-B": "db-primary"}
        result = translate("host-A connects to host-B", tmap)
        assert "web-prod-03" in result
        assert "db-primary" in result

    def test_overlapping_labels_aa_before_a(self):
        """host-AA must not be partially matched by a host-A replacement."""
        tmap = {"host-A": "web-01", "host-AA": "db-primary"}
        result = translate("host-AA is up and host-A is down", tmap)
        assert "db-primary is up" in result
        assert "web-01 is down" in result
        # Ensure host-AA was not partially replaced to 'web-01A'
        assert "web-01A" not in result

    def test_ip_placeholder_translated(self):
        tmap = {"[REDACTED:ip]#0": "192.168.1.1"}
        result = translate("connecting to [REDACTED:ip]#0", tmap)
        assert "192.168.1.1" in result

    def test_multiple_ips_translated(self):
        tmap = {
            "[REDACTED:ip]#0": "192.168.1.1",
            "[REDACTED:ip]#1": "10.0.0.5",
        }
        result = translate("[REDACTED:ip]#0 and [REDACTED:ip]#1", tmap)
        assert "192.168.1.1" in result
        assert "10.0.0.5" in result

    def test_empty_translation_map_returns_text_unchanged(self):
        text = "some log output"
        assert translate(text, {}) == text

    def test_no_labels_in_text_returns_unchanged(self):
        tmap = {"host-A": "web-prod-03"}
        text = "no labels here at all"
        assert translate(text, tmap) == text

    def test_secrets_not_translated(self):
        """[REDACTED:bearer-token] must remain as-is — secrets are never reversed."""
        tmap = {"host-A": "web-prod-03"}
        text = "token=[REDACTED:bearer-token] on host-A"
        result = translate(text, tmap)
        assert "[REDACTED:bearer-token]" in result
        assert "web-prod-03" in result


class TestBuildTranslationMap:
    def test_host_only(self):
        host_map = {"web-prod-03": "host-A"}
        result = build_translation_map(host_map, {})
        assert result == {"host-A": "web-prod-03"}

    def test_ip_only(self):
        ip_map = {"192.168.1.1": "[REDACTED:ip]#0"}
        result = build_translation_map({}, ip_map)
        assert result == {"[REDACTED:ip]#0": "192.168.1.1"}

    def test_combined(self):
        host_map = {"web-prod-03": "host-A"}
        ip_map = {"192.168.1.1": "[REDACTED:ip]#0"}
        result = build_translation_map(host_map, ip_map)
        assert result["host-A"] == "web-prod-03"
        assert result["[REDACTED:ip]#0"] == "192.168.1.1"

    def test_empty_both(self):
        assert build_translation_map({}, {}) == {}
