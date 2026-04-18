"""Secrets, PII, hostname, and IP redaction for logscope.

All redaction runs through a single presidio pipeline (one pass over the
text).  Custom ``PatternRecognizer`` subclasses handle secrets; presidio's
built-in recognizers handle PII; a custom recognizer handles hostnames.

This module is pure — no I/O, no side effects.  Every public object is
fully unit-testable without a live network connection or spaCy model.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine, PatternRecognizer, RecognizerRegistry
from presidio_analyzer import Pattern as PresidioPattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class SpacyModelNotFoundError(RuntimeError):
    """Raised when the required spaCy NER model is not installed.

    Callers (e.g. ``cli.py``) should catch this, print the message to
    stderr, and exit with code 1.
    """


@dataclass
class RedactOptions:
    """Options that control which redaction passes are executed.

    Attributes:
        pii: Enable PII detection via presidio built-in recognizers + spaCy.
        hosts: Pseudonymise hostnames consistently within the session.
        ips: Redact IPv4/IPv6 addresses.
        min_value_length: Minimum secret value length in characters.
            Secrets shorter than this are not redacted (false-positive guard).
    """

    pii: bool = False
    hosts: bool = False
    ips: bool = False
    min_value_length: int = 8


@dataclass
class ChangedLine:
    """A single line that was modified by redaction.

    Attributes:
        line_number: 1-based line number in the original text.
        before: Original line content.
        after: Redacted line content.
    """

    line_number: int
    before: str
    after: str


@dataclass
class RedactSummary:
    """Summary of what the redaction pass changed.

    Attributes:
        total_redacted: Total number of redacted items across all types.
        by_type: Count of redacted items per entity type.
        changed_lines: List of lines that were modified.
        host_map: Mapping of original hostname → assigned label (e.g. ``host-A``).
        ip_map: Mapping of original IP → unique indexed placeholder.
    """

    total_redacted: int
    by_type: dict[str, int]
    changed_lines: list[ChangedLine]
    host_map: dict[str, str]
    ip_map: dict[str, str]


@dataclass
class RedactResult:
    """The result of a single ``redact()`` call.

    Attributes:
        text: The redacted text.
        summary: Details about what was changed.
    """

    text: str
    summary: RedactSummary


# ---------------------------------------------------------------------------
# Hostname mapper
# ---------------------------------------------------------------------------


class HostnameMapper:
    """Maps hostnames to stable sequential labels within a session.

    Labels are alphabetic: host-A, host-B, …, host-Z, host-AA, host-AB, …

    Matching is case-insensitive; the original casing is preserved in
    ``substitution_map``.
    """

    def __init__(self) -> None:
        """Initialise with empty map."""
        self._map: dict[str, str] = {}  # lower-key → label
        self._originals: dict[str, str] = {}  # lower-key → first-seen original
        self._counter: int = 0

    def get_label(self, hostname: str) -> str:
        """Return the stable label for *hostname*, creating one if new.

        Args:
            hostname: Raw hostname string (any casing).

        Returns:
            Label such as ``host-A`` or ``host-AA``.
        """
        key = hostname.lower()
        if key not in self._map:
            self._map[key] = f"host-{self._to_alpha(self._counter)}"
            self._originals[key] = hostname
            self._counter += 1
        return self._map[key]

    @staticmethod
    def _to_alpha(n: int) -> str:
        """Convert a zero-based index to an alphabetic label suffix.

        Args:
            n: Zero-based index (0 → ``A``, 25 → ``Z``, 26 → ``AA``).

        Returns:
            Uppercase letter string.
        """
        result = ""
        n += 1
        while n:
            n, r = divmod(n - 1, 26)
            result = chr(65 + r) + result
        return result

    @property
    def substitution_map(self) -> dict[str, str]:
        """Return ``{original_hostname: label}`` for every seen hostname.

        Returns:
            Dict mapping original hostname strings to their labels.
        """
        return {self._originals[k]: v for k, v in self._map.items()}


# ---------------------------------------------------------------------------
# IP mapper
# ---------------------------------------------------------------------------


class IpMapper:
    """Maps IP addresses to unique indexed placeholders within a session.

    Each distinct IP address gets a placeholder like ``[REDACTED:ip]#0``,
    ``[REDACTED:ip]#1``, etc., enabling reverse translation.
    """

    def __init__(self) -> None:
        """Initialise with empty map."""
        self._map: dict[str, str] = {}
        self._counter: int = 0

    def get_placeholder(self, ip: str) -> str:
        """Return the stable placeholder for *ip*, creating one if new.

        Args:
            ip: IP address string.

        Returns:
            Placeholder such as ``[REDACTED:ip]#0``.
        """
        if ip not in self._map:
            self._map[ip] = f"[REDACTED:ip]#{self._counter}"
            self._counter += 1
        return self._map[ip]

    @property
    def ip_map(self) -> dict[str, str]:
        """Return ``{original_ip: placeholder}`` for every seen IP.

        Returns:
            Dict mapping original IP strings to their placeholders.
        """
        return dict(self._map)


# ---------------------------------------------------------------------------
# Custom PatternRecognizer subclasses — secrets
# ---------------------------------------------------------------------------


class AwsKeyRecognizer(PatternRecognizer):
    """Recognises AWS access key IDs (``AKIA…``)."""

    def __init__(self) -> None:
        """Initialise with AWS key pattern."""
        super().__init__(
            supported_entity="AWS_KEY",
            patterns=[PresidioPattern("AWS_KEY", r"\bAKIA[0-9A-Z]{16}\b", 0.9)],
        )


class AwsSecretRecognizer(PatternRecognizer):
    """Recognises ``aws_secret = <value>`` assignments."""

    def __init__(self, min_length: int = 8) -> None:
        """Initialise with pattern.

        Args:
            min_length: Minimum secret value length.
        """
        super().__init__(
            supported_entity="AWS_SECRET",
            patterns=[
                PresidioPattern(
                    "AWS_SECRET",
                    rf"(?i)aws_secret(?:_access_key)?\s*=\s*\S{{{min_length},}}",
                    0.85,
                )
            ],
        )


class BearerTokenRecognizer(PatternRecognizer):
    """Recognises ``Authorization: Bearer <token>`` headers."""

    def __init__(self, min_length: int = 8) -> None:
        """Initialise with pattern.

        Args:
            min_length: Minimum token length.
        """
        super().__init__(
            supported_entity="BEARER_TOKEN",
            patterns=[
                PresidioPattern(
                    "BEARER_TOKEN",
                    rf"(?i)Bearer\s+[A-Za-z0-9\-._~+/]{{{min_length},}}=*",
                    0.85,
                )
            ],
        )


class GenericTokenRecognizer(PatternRecognizer):
    """Recognises ``token=``, ``api_key=``, ``apikey=``, ``secret=`` assignments."""

    def __init__(self, min_length: int = 8) -> None:
        """Initialise with pattern.

        Args:
            min_length: Minimum value length.
        """
        super().__init__(
            supported_entity="GENERIC_TOKEN",
            patterns=[
                PresidioPattern(
                    "GENERIC_TOKEN",
                    rf"(?i)(?:token|api_key|apikey|secret)\s*[=:]\s*\S{{{min_length},}}",
                    0.8,
                )
            ],
        )


class PrivateKeyRecognizer(PatternRecognizer):
    """Recognises PEM private key blocks."""

    def __init__(self) -> None:
        """Initialise with PEM block pattern."""
        super().__init__(
            supported_entity="PRIVATE_KEY",
            patterns=[
                PresidioPattern(
                    "PRIVATE_KEY",
                    r"-----BEGIN .{0,30}PRIVATE KEY-----[\s\S]+?-----END .{0,30}PRIVATE KEY-----",
                    0.95,
                )
            ],
        )


class PasswordInUrlRecognizer(PatternRecognizer):
    """Recognises passwords embedded in URLs (``https://user:pass@host``)."""

    def __init__(self, min_length: int = 8) -> None:
        """Initialise with URL credential pattern.

        Args:
            min_length: Minimum password length.
        """
        super().__init__(
            supported_entity="PASSWORD_URL",
            patterns=[
                PresidioPattern(
                    "PASSWORD_URL",
                    rf"[a-z][a-z0-9+\-.]*://[^:\s]+:[^@\s]{{{min_length},}}@",
                    0.9,
                )
            ],
        )


class EnvPasswordRecognizer(PatternRecognizer):
    """Recognises ``password=``, ``passwd=``, ``pwd=`` env-var assignments."""

    def __init__(self, min_length: int = 8) -> None:
        """Initialise with pattern.

        Args:
            min_length: Minimum value length.
        """
        super().__init__(
            supported_entity="ENV_PASSWORD",
            patterns=[
                PresidioPattern(
                    "ENV_PASSWORD",
                    rf"(?i)(?:password|passwd|pwd)\s*[=:]\s*\S{{{min_length},}}",
                    0.85,
                )
            ],
        )


class JwtRecognizer(PatternRecognizer):
    """Recognises JSON Web Tokens (three base64url segments separated by dots)."""

    def __init__(self) -> None:
        """Initialise with JWT pattern."""
        super().__init__(
            supported_entity="JWT",
            patterns=[
                PresidioPattern(
                    "JWT",
                    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                    0.9,
                )
            ],
        )


class EnvSecretRecognizer(PatternRecognizer):
    """Recognises ``MY_SECRET=value`` style env-var assignments."""

    def __init__(self, min_length: int = 8) -> None:
        """Initialise with pattern.

        Args:
            min_length: Minimum value length.
        """
        super().__init__(
            supported_entity="ENV_SECRET",
            patterns=[
                PresidioPattern(
                    "ENV_SECRET",
                    rf"[A-Z_]*(?:SECRET|KEY|TOKEN|PASSWORD)[A-Z_]*\s*=\s*\S{{{min_length},}}",
                    0.8,
                )
            ],
        )


# ---------------------------------------------------------------------------
# Hostname recognizer
# ---------------------------------------------------------------------------

_HOSTNAME_PATTERNS = [
    # Tier 1 — FQDNs (always match, high confidence), case-insensitive
    PresidioPattern(
        "FQDN",
        r"(?i)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,}|internal|local|corp|lan)",
        0.85,
    ),
    # Tier 2 — Context-anchored bare names; lookbehind avoids consuming the keyword
    PresidioPattern(
        "CONTEXT_HOSTNAME",
        r"(?i)(?<=(?:from|host|node|peer|server|remote|origin)\s)[a-z0-9][a-z0-9\-]{2,61}[a-z0-9]",
        0.75,
    ),
    # Tier 3 — Hyphenated infra names with digit suffix, case-insensitive
    PresidioPattern(
        "INFRA_HOSTNAME",
        r"(?i)(?<!\w)[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d+(?!\w)",
        0.7,
    ),
]


class HostnameRecognizer(PatternRecognizer):
    """Recognises hostnames via three tiers: FQDNs, context-anchored names, infra patterns."""

    def __init__(self) -> None:
        """Initialise with all three hostname tier patterns."""
        super().__init__(
            supported_entity="HOSTNAME",
            patterns=_HOSTNAME_PATTERNS,
        )


# ---------------------------------------------------------------------------
# Operator replacements
# ---------------------------------------------------------------------------

_SECRET_OPERATORS: dict[str, OperatorConfig] = {
    "AWS_KEY": OperatorConfig("replace", {"new_value": "[REDACTED:aws-key]"}),
    "AWS_SECRET": OperatorConfig("replace", {"new_value": "[REDACTED:aws-secret]"}),
    "BEARER_TOKEN": OperatorConfig("replace", {"new_value": "[REDACTED:bearer-token]"}),
    "GENERIC_TOKEN": OperatorConfig("replace", {"new_value": "[REDACTED:token]"}),
    "PRIVATE_KEY": OperatorConfig("replace", {"new_value": "[REDACTED:private-key]"}),
    "PASSWORD_URL": OperatorConfig("replace", {"new_value": "[REDACTED:credentials]"}),
    "ENV_PASSWORD": OperatorConfig("replace", {"new_value": "[REDACTED:password]"}),
    "JWT": OperatorConfig("replace", {"new_value": "[REDACTED:jwt]"}),
    "ENV_SECRET": OperatorConfig("replace", {"new_value": "[REDACTED:env-secret]"}),
}

_PII_OPERATORS: dict[str, OperatorConfig] = {
    "PERSON": OperatorConfig("replace", {"new_value": "[REDACTED:pii-person]"}),
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED:pii-email]"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED:pii-phone]"}),
    "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[REDACTED:pii-cc]"}),
    "US_SSN": OperatorConfig("replace", {"new_value": "[REDACTED:pii-ssn]"}),
    "LOCATION": OperatorConfig("replace", {"new_value": "[REDACTED:pii-location]"}),
    "URL": OperatorConfig("replace", {"new_value": "[REDACTED:pii-url]"}),
}


# ---------------------------------------------------------------------------
# Engine builder
# ---------------------------------------------------------------------------


def _build_engine(
    opts: RedactOptions,
    hostname_mapper: HostnameMapper,
    ip_mapper: IpMapper,
) -> tuple[AnalyzerEngine, AnonymizerEngine, dict[str, OperatorConfig], list[str]]:
    """Build a configured presidio pipeline for the given options.

    Args:
        opts: Redaction options controlling which passes are active.
        hostname_mapper: Mapper for stable hostname → label substitution.
        ip_mapper: Mapper for unique IP placeholders.

    Returns:
        Tuple of (analyzer, anonymizer, operators, entities).
    """
    registry = RecognizerRegistry()

    # Secret recognizers (always active)
    registry.add_recognizer(AwsKeyRecognizer())
    registry.add_recognizer(AwsSecretRecognizer(min_length=opts.min_value_length))
    registry.add_recognizer(BearerTokenRecognizer(min_length=opts.min_value_length))
    registry.add_recognizer(GenericTokenRecognizer(min_length=opts.min_value_length))
    registry.add_recognizer(PrivateKeyRecognizer())
    registry.add_recognizer(PasswordInUrlRecognizer(min_length=opts.min_value_length))
    registry.add_recognizer(EnvPasswordRecognizer(min_length=opts.min_value_length))
    registry.add_recognizer(JwtRecognizer())
    registry.add_recognizer(EnvSecretRecognizer(min_length=opts.min_value_length))

    entities = [
        "AWS_KEY",
        "AWS_SECRET",
        "BEARER_TOKEN",
        "GENERIC_TOKEN",
        "PRIVATE_KEY",
        "PASSWORD_URL",
        "ENV_PASSWORD",
        "JWT",
        "ENV_SECRET",
    ]
    operators: dict[str, OperatorConfig] = dict(_SECRET_OPERATORS)

    if opts.pii:
        registry.load_predefined_recognizers()
        entities += [
            "PERSON",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "CREDIT_CARD",
            "US_SSN",
            "LOCATION",
            "URL",
        ]
        operators.update(_PII_OPERATORS)

    if opts.ips:
        # Re-add predefined recognizers if not already done (needed for IP_ADDRESS)
        if not opts.pii:
            registry.load_predefined_recognizers()
        entities.append("IP_ADDRESS")

        def _ip_replace(text: str) -> str:
            return ip_mapper.get_placeholder(text)

        operators["IP_ADDRESS"] = OperatorConfig("custom", {"lambda": _ip_replace})

    if opts.hosts:
        registry.add_recognizer(HostnameRecognizer())
        entities.append("HOSTNAME")

        def _host_replace(text: str) -> str:
            return hostname_mapper.get_label(text)

        operators["HOSTNAME"] = OperatorConfig("custom", {"lambda": _host_replace})

    analyzer = AnalyzerEngine(registry=registry, supported_languages=["en"])
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer, operators, entities


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact(text: str, opts: RedactOptions) -> RedactResult:
    """Run the full redaction pipeline over *text*.

    One presidio pass handles all active redaction types (secrets, PII,
    hostnames, IPs).  The result contains the cleaned text and a summary
    of everything that was changed.

    If ``opts.pii`` is True and the spaCy ``en_core_web_lg`` model is not
    installed, the function prints the download command to stderr and raises
    ``SystemExit(1)``.

    Args:
        text: Raw log text to redact.
        opts: Options controlling which redaction passes are executed.

    Returns:
        RedactResult with redacted text and summary.
    """
    hostname_mapper = HostnameMapper()
    ip_mapper = IpMapper()

    # Validate spaCy model availability before building the engine.
    # Also required when opts.ips=True because load_predefined_recognizers()
    # may initialise NLP-backed recognizers that need the model.
    if opts.pii or opts.ips:
        _check_spacy_model()

    analyzer, anonymizer, operators, entities = _build_engine(opts, hostname_mapper, ip_mapper)

    results = analyzer.analyze(text=text, entities=entities, language="en")
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operators,
    )
    redacted_text: str = anonymized.text

    # Build summary
    by_type: dict[str, int] = {}
    for r in results:
        by_type[r.entity_type] = by_type.get(r.entity_type, 0) + 1

    original_lines = text.splitlines()
    redacted_lines = redacted_text.splitlines()

    # Pad shorter list so zip doesn't drop lines
    max_len = max(len(original_lines), len(redacted_lines))
    original_lines += [""] * (max_len - len(original_lines))
    redacted_lines += [""] * (max_len - len(redacted_lines))

    changed_lines = [
        ChangedLine(line_number=i + 1, before=orig, after=red)
        for i, (orig, red) in enumerate(zip(original_lines, redacted_lines))
        if orig != red
    ]

    summary = RedactSummary(
        total_redacted=len(results),
        by_type=by_type,
        changed_lines=changed_lines,
        host_map=hostname_mapper.substitution_map,
        ip_map=ip_mapper.ip_map,
    )
    return RedactResult(text=redacted_text, summary=summary)


def _check_spacy_model() -> None:
    """Verify that the required spaCy model is available.

    Raises:
        SpacyModelNotFoundError: If the model is not installed or spacy
            is not importable.
    """
    try:
        import spacy

        if not spacy.util.is_package("en_core_web_lg"):
            raise SpacyModelNotFoundError(
                "[logscope] Error: spaCy model 'en_core_web_lg' is not installed.\n"
                "  To install it run:\n"
                "    uv run python -m spacy download en_core_web_lg"
            )
    except ImportError as exc:
        raise SpacyModelNotFoundError("[logscope] Error: spacy is not installed.") from exc


def _missing_spacy_model() -> None:
    """Print spaCy model download instructions and exit.

    Raises:
        SystemExit: Always raises with exit code 1.

    .. deprecated::
        Use :func:`_check_spacy_model` which raises
        :exc:`SpacyModelNotFoundError` instead.
    """
    sys.stderr.write(
        "[logscope] Error: spaCy model 'en_core_web_lg' is not installed.\n"
        "  To install it run:\n"
        "    uv run python -m spacy download en_core_web_lg\n"
    )
    sys.exit(1)
