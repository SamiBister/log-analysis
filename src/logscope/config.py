"""Configuration loading and merging for logscope.

Handles reading ~/.config/logscope/config.toml, falling back to hardcoded
defaults, and merging CLI flags (CLI flags always win).
"""

from __future__ import annotations

import dataclasses
import re
import sys
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

# ---------------------------------------------------------------------------
# Default values — single source of truth
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_BYTES = 200_000
_DEFAULT_MAX_CONTEXT_BYTES = 50_000
_DEFAULT_MIN_VALUE_LENGTH = 8
_VALID_MODEL_RE = re.compile(r"^[a-zA-Z0-9._:\-]{1,128}$")


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class LogscopeConfig:
    """All resolved configuration for a logscope invocation.

    Attributes:
        model: Copilot model identifier.
        redact: Whether redaction is enabled.
        redact_pii: Whether PII redaction via presidio/spaCy is enabled.
        redact_hosts: Whether hostname pseudonymisation is enabled.
        redact_ips: Whether IP address redaction is enabled.
        min_value_length: Minimum secret value length to trigger redaction.
        max_bytes: Maximum input log bytes to keep (last N bytes). Must be > 0.
        last: Keep last N lines (0 = disabled, takes priority over max_bytes).
        quiet: Suppress [logscope] stderr messages.
        show_redacted: Print full redacted log to stderr.
        translate: Reverse-translate host labels and IP placeholders in output.
        context_file: Default context file path (empty string = disabled).
        max_context_bytes: Truncate context file to this many bytes. Must be > 0.
    """

    model: str = _DEFAULT_MODEL
    redact: bool = True
    redact_pii: bool = False
    redact_hosts: bool = False
    redact_ips: bool = False
    min_value_length: int = _DEFAULT_MIN_VALUE_LENGTH
    max_bytes: int = _DEFAULT_MAX_BYTES
    last: int = 0
    quiet: bool = False
    show_redacted: bool = False
    translate: bool = True
    context_file: str = ""
    max_context_bytes: int = _DEFAULT_MAX_CONTEXT_BYTES


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def resolve_config_path() -> Path:
    """Return the config file path: ``~/.config/logscope/config.toml``.

    Returns:
        Absolute Path to the config file.
    """
    return Path.home() / ".config" / "logscope" / "config.toml"


# ---------------------------------------------------------------------------
# Defaults helper — derived from LogscopeConfig to avoid duplication
# ---------------------------------------------------------------------------
def _default_toml() -> str:
    """Generate the default config TOML string from LogscopeConfig defaults.

    Returns:
        TOML-formatted string with all default values.
    """
    d = LogscopeConfig()
    return f"""\
model = "{d.model}"

[redaction]
enabled = {str(d.redact).lower()}
pii = {str(d.redact_pii).lower()}
hosts = {str(d.redact_hosts).lower()}
ips = {str(d.redact_ips).lower()}
min_value_length = {d.min_value_length}

[input]
max_bytes = {d.max_bytes}
last = {d.last}

[output]
quiet = {str(d.quiet).lower()}
show_redacted = {str(d.show_redacted).lower()}
translate = {str(d.translate).lower()}

[context]
file = "{d.context_file}"
max_bytes = {d.max_context_bytes}
"""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _clamp_positive(value: int, default: int, field: str) -> int:
    """Clamp *value* to be at least 1, warning on stderr if clamped.

    Args:
        value: The parsed integer value.
        default: Fallback default when value is invalid.
        field: Field name used in the warning message.

    Returns:
        The clamped value (>= 1).
    """
    if value < 1:
        sys.stderr.write(
            f"[logscope] Warning: {field}={value} must be >= 1 — using default {default}.\n"
        )
        return default
    return value


def _clamp_nonneg(value: int, default: int, field: str) -> int:
    """Clamp *value* to be at least 0, warning on stderr if clamped.

    Args:
        value: The parsed integer value.
        default: Fallback default when value is invalid.
        field: Field name used in the warning message.

    Returns:
        The clamped value (>= 0).
    """
    if value < 0:
        sys.stderr.write(
            f"[logscope] Warning: {field}={value} must be >= 0 — using default {default}.\n"
        )
        return default
    return value


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load_config(config_path: Path | None = None) -> LogscopeConfig:
    """Load configuration from disk, creating the file with defaults if absent.

    Falls back to defaults if the file is malformed, printing a warning to
    stderr. If the config directory or file cannot be created, a warning is
    printed but execution continues with defaults.

    Args:
        config_path: Override the default config path (useful in tests).

    Returns:
        Populated LogscopeConfig instance.
    """
    path = config_path if config_path is not None else resolve_config_path()

    # Auto-create with defaults
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_text(_default_toml(), encoding="utf-8")
            path.chmod(0o600)
        except OSError as exc:
            sys.stderr.write(
                f"[logscope] Warning: could not create config file {path}: {exc}"
                " — using defaults.\n"
            )
        return LogscopeConfig()

    # Parse
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        sys.stderr.write(
            f"[logscope] Warning: config file {path} is malformed ({exc}) — using defaults.\n"
        )
        return LogscopeConfig()
    except OSError as exc:
        sys.stderr.write(
            f"[logscope] Warning: could not read config file {path}: {exc} — using defaults.\n"
        )
        return LogscopeConfig()

    return _parse_toml(data)


def _parse_toml(data: dict[str, object]) -> LogscopeConfig:
    """Parse a raw TOML dict into a LogscopeConfig.

    Unknown keys are silently ignored. Numeric fields are validated and
    clamped to sensible ranges.

    Args:
        data: Raw dict from tomllib.

    Returns:
        LogscopeConfig populated from the dict.
    """
    d = LogscopeConfig()  # defaults

    raw_model = str(data.get("model", d.model))
    if not _VALID_MODEL_RE.match(raw_model):
        sys.stderr.write(f"[logscope] Warning: invalid model name '{raw_model}' — using default.\n")
        raw_model = _DEFAULT_MODEL

    red = data.get("redaction", {})
    assert isinstance(red, dict)
    inp = data.get("input", {})
    assert isinstance(inp, dict)
    out = data.get("output", {})
    assert isinstance(out, dict)
    ctx = data.get("context", {})
    assert isinstance(ctx, dict)

    return LogscopeConfig(
        model=raw_model,
        redact=bool(red.get("enabled", d.redact)),
        redact_pii=bool(red.get("pii", d.redact_pii)),
        redact_hosts=bool(red.get("hosts", d.redact_hosts)),
        redact_ips=bool(red.get("ips", d.redact_ips)),
        min_value_length=_clamp_positive(
            int(red.get("min_value_length", d.min_value_length)),
            _DEFAULT_MIN_VALUE_LENGTH,
            "min_value_length",
        ),
        max_bytes=_clamp_positive(
            int(inp.get("max_bytes", d.max_bytes)),
            _DEFAULT_MAX_BYTES,
            "input.max_bytes",
        ),
        last=_clamp_nonneg(int(inp.get("last", d.last)), 0, "input.last"),
        quiet=bool(out.get("quiet", d.quiet)),
        show_redacted=bool(out.get("show_redacted", d.show_redacted)),
        translate=bool(out.get("translate", d.translate)),
        context_file=str(ctx.get("file", d.context_file)),
        max_context_bytes=_clamp_positive(
            int(ctx.get("max_bytes", d.max_context_bytes)),
            _DEFAULT_MAX_CONTEXT_BYTES,
            "context.max_bytes",
        ),
    )


# ---------------------------------------------------------------------------
# Merge CLI flags
# ---------------------------------------------------------------------------
def merge_config(config: LogscopeConfig, args: dict[str, object]) -> LogscopeConfig:
    """Overlay CLI flag values onto a config, where CLI always wins.

    Only keys explicitly set in *args* (non-None) override the config.

    Args:
        config: Base configuration (from file or defaults).
        args: Dict of CLI flag values. ``None`` values are ignored.

    Returns:
        New LogscopeConfig with CLI values applied.
    """
    overrides: dict[str, object] = {}

    for field in dataclasses.fields(config):
        _apply(overrides, field.name, args.get(field.name))

    # --no-redact maps to redact=False
    if args.get("no_redact") is True:
        overrides["redact"] = False

    return replace(config, **overrides)


def _apply(overrides: dict[str, object], key: str, value: object) -> None:
    """Add *value* to *overrides* only if it is not None.

    Args:
        overrides: Mutable dict to update.
        key: Config field name.
        value: CLI value; skipped when None.
    """
    if value is not None:
        overrides[key] = value
