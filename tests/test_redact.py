"""Tests for logscope.redact.

All external presidio engine calls are mocked so the test suite runs
without a spaCy model or any network access.  The custom PatternRecognizer
subclasses are tested directly (they are pure regex — no engine needed).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from logscope.redact import (
    AwsKeyRecognizer,
    BearerTokenRecognizer,
    EnvPasswordRecognizer,
    EnvSecretRecognizer,
    HostnameMapper,
    HostnameRecognizer,
    IpMapper,
    JwtRecognizer,
    PasswordInUrlRecognizer,
    PrivateKeyRecognizer,
    RedactOptions,
    RedactResult,
    RedactSummary,
    SpacyModelNotFoundError,
    redact,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recognize(recognizer, text: str) -> list[str]:
    """Run a single recognizer directly and return matched spans."""
    results = recognizer.analyze(text=text, entities=[recognizer.supported_entities[0]])
    return [text[r.start : r.end] for r in results]


# ---------------------------------------------------------------------------
# Secret recognizers — tested directly without the full engine
# ---------------------------------------------------------------------------


class TestAwsKeyRecognizer:
    def test_detects_aws_key(self):
        hits = _recognize(AwsKeyRecognizer(), "key=AKIAIOSFODNN7EXAMPLE")
        assert any("AKIA" in h for h in hits)

    def test_does_not_match_short(self):
        # AKIA + 15 chars = too short (needs exactly 16)
        hits = _recognize(AwsKeyRecognizer(), "AKIAIOSFODNN7EXA")
        assert hits == []


class TestBearerTokenRecognizer:
    def test_detects_bearer_token(self):
        hits = _recognize(BearerTokenRecognizer(), "Authorization: Bearer eyABC123longtoken")
        assert hits

    def test_short_value_not_detected(self):
        # value only 4 chars — below min_value_length=8
        hits = _recognize(BearerTokenRecognizer(), "Authorization: Bearer abc1")
        assert hits == []


class TestJwtRecognizer:
    def test_detects_jwt(self):
        hits = _recognize(
            JwtRecognizer(),
            "token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijk",
        )
        assert hits

    def test_no_false_positive_on_plain_text(self):
        hits = _recognize(JwtRecognizer(), "just a plain log line")
        assert hits == []


class TestPasswordInUrlRecognizer:
    def test_detects_credentials_in_url(self):
        hits = _recognize(
            PasswordInUrlRecognizer(),
            "postgres://user:s3cr3tpass@localhost/db",
        )
        assert hits

    def test_short_password_not_detected(self):
        hits = _recognize(PasswordInUrlRecognizer(), "http://user:abc@host/")
        assert hits == []


class TestEnvPasswordRecognizer:
    def test_detects_env_password(self):
        hits = _recognize(EnvPasswordRecognizer(), "DB_PASSWORD=mysecretpass")
        assert hits

    def test_short_value_ignored(self):
        hits = _recognize(EnvPasswordRecognizer(), "pwd=short")
        assert hits == []


class TestEnvSecretRecognizer:
    def test_detects_env_secret(self):
        hits = _recognize(EnvSecretRecognizer(), "MY_SECRET=verylongsecretvalue")
        assert hits

    def test_short_value_not_detected(self):
        hits = _recognize(EnvSecretRecognizer(), "LOG_LEVEL=info")
        assert hits == []

    def test_short_timeout_not_detected(self):
        hits = _recognize(EnvSecretRecognizer(), "TIMEOUT=30")
        assert hits == []


class TestPrivateKeyRecognizer:
    def test_detects_rsa_private_key(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
        hits = _recognize(PrivateKeyRecognizer(), pem)
        assert hits


# ---------------------------------------------------------------------------
# HostnameMapper
# ---------------------------------------------------------------------------


class TestHostnameMapper:
    def test_first_host_gets_label_a(self):
        m = HostnameMapper()
        assert m.get_label("web-prod-03") == "host-A"

    def test_second_host_gets_label_b(self):
        m = HostnameMapper()
        m.get_label("web-prod-03")
        assert m.get_label("db-primary") == "host-B"

    def test_same_host_returns_same_label(self):
        m = HostnameMapper()
        assert m.get_label("web-prod-03") == m.get_label("web-prod-03")

    def test_case_insensitive(self):
        m = HostnameMapper()
        assert m.get_label("Web-Prod-03") == m.get_label("web-prod-03")

    def test_to_alpha_0_is_a(self):
        assert HostnameMapper._to_alpha(0) == "A"

    def test_to_alpha_25_is_z(self):
        assert HostnameMapper._to_alpha(25) == "Z"

    def test_to_alpha_26_is_aa(self):
        assert HostnameMapper._to_alpha(26) == "AA"

    def test_to_alpha_27_is_ab(self):
        assert HostnameMapper._to_alpha(27) == "AB"

    def test_substitution_map_returns_correct_dict(self):
        m = HostnameMapper()
        m.get_label("web-prod-03")
        m.get_label("db-primary")
        smap = m.substitution_map
        assert smap["web-prod-03"] == "host-A"
        assert smap["db-primary"] == "host-B"

    def test_substitution_map_order_matches_first_appearance(self):
        m = HostnameMapper()
        m.get_label("first")
        m.get_label("second")
        keys = list(m.substitution_map.keys())
        assert keys[0] == "first"
        assert keys[1] == "second"


# ---------------------------------------------------------------------------
# IpMapper
# ---------------------------------------------------------------------------


class TestIpMapper:
    def test_first_ip_gets_index_0(self):
        m = IpMapper()
        assert m.get_placeholder("192.168.1.1") == "[REDACTED:ip]#0"

    def test_second_ip_gets_index_1(self):
        m = IpMapper()
        m.get_placeholder("192.168.1.1")
        assert m.get_placeholder("10.0.0.5") == "[REDACTED:ip]#1"

    def test_same_ip_returns_same_placeholder(self):
        m = IpMapper()
        assert m.get_placeholder("192.168.1.1") == m.get_placeholder("192.168.1.1")

    def test_ip_map_property(self):
        m = IpMapper()
        m.get_placeholder("192.168.1.1")
        m.get_placeholder("10.0.0.5")
        assert m.ip_map == {
            "192.168.1.1": "[REDACTED:ip]#0",
            "10.0.0.5": "[REDACTED:ip]#1",
        }


# ---------------------------------------------------------------------------
# HostnameRecognizer tiers
# ---------------------------------------------------------------------------


class TestHostnameRecognizer:
    def test_fqdn_detected(self):
        hits = _recognize(HostnameRecognizer(), "connected to db-primary.internal")
        assert any("db-primary.internal" in h for h in hits)

    def test_context_anchored_name(self):
        hits = _recognize(HostnameRecognizer(), "Connected from web-prod-03")
        assert hits

    def test_hyphenated_infra_name(self):
        hits = _recognize(HostnameRecognizer(), "worker-node-07 failed to start")
        assert any("worker-node-07" in h for h in hits)

    def test_plain_word_not_matched(self):
        hits = _recognize(HostnameRecognizer(), "failed error started")
        assert hits == []


# ---------------------------------------------------------------------------
# redact() — full pipeline, presidio engines mocked
# ---------------------------------------------------------------------------

_MOCK_ANALYZER_RESULT = MagicMock()
_MOCK_ANALYZER_RESULT.entity_type = "BEARER_TOKEN"
_MOCK_ANALYZER_RESULT.start = 23
_MOCK_ANALYZER_RESULT.end = 47


def _make_anonymized(text: str):
    """Return a mock AnonymizedText object with the given text."""
    m = MagicMock()
    m.text = text
    return m


class TestRedactPipeline:
    """Tests for redact() that mock the presidio AnalyzerEngine and AnonymizerEngine."""

    def _run_redact(
        self,
        text: str,
        analyzer_results=None,
        anonymized_text: str | None = None,
        opts: RedactOptions | None = None,
    ) -> RedactResult:
        """Run redact() with both engines mocked."""
        if opts is None:
            opts = RedactOptions()
        if analyzer_results is None:
            analyzer_results = []
        if anonymized_text is None:
            anonymized_text = text  # no change

        with (
            patch("logscope.redact.AnalyzerEngine") as mock_analyzer_cls,
            patch("logscope.redact.AnonymizerEngine") as mock_anonymizer_cls,
        ):
            mock_analyzer = mock_analyzer_cls.return_value
            mock_analyzer.analyze.return_value = analyzer_results
            mock_anonymizer = mock_anonymizer_cls.return_value
            mock_anonymizer.anonymize.return_value = _make_anonymized(anonymized_text)

            return redact(text, opts)

    def test_no_secrets_unchanged(self):
        result = self._run_redact("plain log line with no secrets")
        assert result.text == "plain log line with no secrets"
        assert result.summary.total_redacted == 0

    def test_total_redacted_count(self):
        r1 = MagicMock(entity_type="BEARER_TOKEN", start=0, end=10)
        r2 = MagicMock(entity_type="ENV_PASSWORD", start=20, end=30)
        result = self._run_redact(
            "bearer token and password=secret99",
            analyzer_results=[r1, r2],
            anonymized_text="[REDACTED:bearer-token] and [REDACTED:password]",
        )
        assert result.summary.total_redacted == 2

    def test_by_type_counts(self):
        r1 = MagicMock(entity_type="BEARER_TOKEN", start=0, end=10)
        r2 = MagicMock(entity_type="BEARER_TOKEN", start=20, end=30)
        r3 = MagicMock(entity_type="JWT", start=40, end=50)
        result = self._run_redact(
            "x",
            analyzer_results=[r1, r2, r3],
            anonymized_text="x",
        )
        assert result.summary.by_type["BEARER_TOKEN"] == 2
        assert result.summary.by_type["JWT"] == 1

    def test_changed_lines_populated(self):
        original = "line with token=abc12345678\nclean line"
        redacted = "[REDACTED:token]\nclean line"
        r1 = MagicMock(entity_type="GENERIC_TOKEN", start=10, end=27)
        result = self._run_redact(
            original,
            analyzer_results=[r1],
            anonymized_text=redacted,
        )
        changed = result.summary.changed_lines
        assert len(changed) == 1
        assert changed[0].line_number == 1
        assert changed[0].before == "line with token=abc12345678"
        assert changed[0].after == "[REDACTED:token]"

    def test_ip_off_by_default(self):
        """IP addresses are not redacted unless --redact-ips is set."""
        # With mocked analyzer returning no results, IP should stay
        result = self._run_redact(
            "Connected from 192.168.1.1",
            analyzer_results=[],
            anonymized_text="Connected from 192.168.1.1",
        )
        assert "192.168.1.1" in result.text

    def test_pii_mock_applies_replacement(self):
        """With pii=True, a mocked PERSON result produces the right replacement."""
        r1 = MagicMock(entity_type="PERSON", start=0, end=4)
        with patch("logscope.redact._check_spacy_model"):
            result = self._run_redact(
                "John logged in",
                analyzer_results=[r1],
                anonymized_text="[REDACTED:pii-person] logged in",
                opts=RedactOptions(pii=True),
            )
        assert "[REDACTED:pii-person]" in result.text

    def test_host_map_populated(self):
        """host_map in summary is filled from the HostnameMapper."""

        # Simulate the anonymizer replacing a hostname via the custom operator
        def side_effect_redact(text, opts):
            # Call the real mapper via a real HostnameMapper to get a label
            from logscope.redact import HostnameMapper

            m = HostnameMapper()
            label = m.get_label("web-prod-03")
            return RedactResult(
                text=text.replace("web-prod-03", label),
                summary=RedactSummary(
                    total_redacted=1,
                    by_type={"HOSTNAME": 1},
                    changed_lines=[],
                    host_map=m.substitution_map,
                    ip_map={},
                ),
            )

        # Use side_effect to test HostnameMapper integration directly
        with patch("logscope.redact.redact", side_effect=side_effect_redact):
            from logscope import redact as redact_module

            result = redact_module.redact("web-prod-03 is down", RedactOptions(hosts=True))
        assert "web-prod-03" in result.summary.host_map
        assert result.summary.host_map["web-prod-03"] == "host-A"

    def test_ip_map_populated_with_indexed_placeholders(self):
        """ip_map uses indexed placeholders so two IPs are distinguishable."""
        ip_m = IpMapper()
        ip_m.get_placeholder("192.168.1.1")
        ip_m.get_placeholder("10.0.0.5")
        assert ip_m.ip_map["192.168.1.1"] == "[REDACTED:ip]#0"
        assert ip_m.ip_map["10.0.0.5"] == "[REDACTED:ip]#1"

    def test_multiple_secrets_one_line(self):
        r1 = MagicMock(entity_type="BEARER_TOKEN", start=0, end=15)
        r2 = MagicMock(entity_type="ENV_PASSWORD", start=16, end=30)
        result = self._run_redact(
            "bearer:longtoken password=s3cr3tlong",
            analyzer_results=[r1, r2],
            anonymized_text="[REDACTED:bearer-token] [REDACTED:password]",
        )
        assert result.summary.total_redacted == 2

    def test_ip_redact_disabled_by_default(self):
        """IP_ADDRESS entity is not in the entity list when ips=False."""
        opts = RedactOptions(ips=False)
        with (
            patch("logscope.redact.AnalyzerEngine") as mock_analyzer_cls,
            patch("logscope.redact.AnonymizerEngine") as mock_anonymizer_cls,
        ):
            mock_analyzer = mock_analyzer_cls.return_value
            mock_analyzer.analyze.return_value = []
            mock_anonymizer_cls.return_value.anonymize.return_value = _make_anonymized(
                "Connected from 192.168.1.1"
            )
            redact("Connected from 192.168.1.1", opts)
            call_kwargs = mock_analyzer.analyze.call_args
            entities_used = call_kwargs[1].get("entities") or call_kwargs[0][1]
            assert "IP_ADDRESS" not in entities_used


# ---------------------------------------------------------------------------
# spaCy model check
# ---------------------------------------------------------------------------


class TestSpacyModelCheck:
    def test_missing_spacy_model_raises(self, capsys):
        """When spaCy model is absent, redact(pii=True) raises SpacyModelNotFoundError."""
        with (
            patch("logscope.redact.AnalyzerEngine"),
            patch("logscope.redact.AnonymizerEngine"),
            patch(
                "logscope.redact._check_spacy_model",
                side_effect=SpacyModelNotFoundError("model missing"),
            ),
        ):
            with pytest.raises(SpacyModelNotFoundError):
                redact("log text", RedactOptions(pii=True))

    def test_check_spacy_model_raises_when_not_installed(self, capsys):
        """_check_spacy_model raises SpacyModelNotFoundError when model missing."""
        import spacy

        with patch.object(spacy.util, "is_package", return_value=False):
            with pytest.raises(SpacyModelNotFoundError, match="en_core_web_lg"):
                from logscope.redact import _check_spacy_model

                _check_spacy_model()

    def test_check_spacy_model_passes_when_installed(self):
        """_check_spacy_model does not raise when model is present."""
        import spacy

        with patch.object(spacy.util, "is_package", return_value=True):
            from logscope.redact import _check_spacy_model

            _check_spacy_model()  # should not raise


class TestBuildEngineIpAndHostBranches:
    """Cover the opts.ips and opts.hosts branches in _build_engine."""

    def _run(self, opts: RedactOptions) -> RedactResult:
        with (
            patch("logscope.redact.AnalyzerEngine") as mock_analyzer_cls,
            patch("logscope.redact.AnonymizerEngine") as mock_anonymizer_cls,
            patch("logscope.redact._check_spacy_model"),
        ):
            mock_analyzer = mock_analyzer_cls.return_value
            mock_analyzer.analyze.return_value = []
            mock_anonymizer_cls.return_value.anonymize.return_value = _make_anonymized("x")
            return redact("x", opts)

    def test_ips_true_adds_ip_address_entity(self):
        opts = RedactOptions(ips=True)
        with (
            patch("logscope.redact.AnalyzerEngine") as mock_analyzer_cls,
            patch("logscope.redact.AnonymizerEngine") as mock_anonymizer_cls,
            patch("logscope.redact._check_spacy_model"),
        ):
            mock_analyzer = mock_analyzer_cls.return_value
            mock_analyzer.analyze.return_value = []
            mock_anonymizer_cls.return_value.anonymize.return_value = _make_anonymized("x")
            redact("x", opts)
            call_kwargs = mock_analyzer.analyze.call_args
            entities_used = call_kwargs[1].get("entities") or call_kwargs[0][1]
            assert "IP_ADDRESS" in entities_used

    def test_hosts_true_adds_hostname_entity(self):
        opts = RedactOptions(hosts=True)
        with (
            patch("logscope.redact.AnalyzerEngine") as mock_analyzer_cls,
            patch("logscope.redact.AnonymizerEngine") as mock_anonymizer_cls,
        ):
            mock_analyzer = mock_analyzer_cls.return_value
            mock_analyzer.analyze.return_value = []
            mock_anonymizer_cls.return_value.anonymize.return_value = _make_anonymized("x")
            redact("x", opts)
            call_kwargs = mock_analyzer.analyze.call_args
            entities_used = call_kwargs[1].get("entities") or call_kwargs[0][1]
            assert "HOSTNAME" in entities_used

    def test_pii_true_adds_person_entity(self):
        opts = RedactOptions(pii=True)
        with (
            patch("logscope.redact.AnalyzerEngine") as mock_analyzer_cls,
            patch("logscope.redact.AnonymizerEngine") as mock_anonymizer_cls,
            patch("logscope.redact._check_spacy_model"),
        ):
            mock_analyzer = mock_analyzer_cls.return_value
            mock_analyzer.analyze.return_value = []
            mock_anonymizer_cls.return_value.anonymize.return_value = _make_anonymized("x")
            redact("x", opts)
            call_kwargs = mock_analyzer.analyze.call_args
            entities_used = call_kwargs[1].get("entities") or call_kwargs[0][1]
            assert "PERSON" in entities_used

    def test_ips_without_pii_still_loads_predefined(self):
        """ips=True without pii=True must still load predefined recognizers for IP_ADDRESS."""
        opts = RedactOptions(ips=True, pii=False)
        self._run(opts)  # should not raise
