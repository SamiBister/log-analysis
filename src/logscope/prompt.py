"""First-turn prompt builder for logscope.

Assembles the system message, optional context document, redacted log,
and the user's first question into a single prompt string for the Copilot
session's first turn.
"""

from __future__ import annotations

_SYSTEM = (
    "You are a log analysis expert. Be concise. "
    "Call out errors, warnings, root causes, and anomalies. "
    "Redacted values appear as [REDACTED:<type>] — do not ask for them. "
    "Pseudonymised hosts appear as host-A, host-B etc."
)

_SYSTEM_WITH_CONTEXT = _SYSTEM + (
    " A context document is provided — use it to understand normal behaviour."
)


def build_first_prompt(
    log: str,
    question: str,
    context: str | None,
    host_map: dict[str, str],
) -> str:
    """Build the first-turn prompt for a logscope Copilot session.

    The prompt structure is:

    1. System instruction (always present).
    2. Hostname substitution note (only when *host_map* is non-empty).
    3. ``<context>`` block (only when *context* is non-empty).
    4. ``<log>`` block with the redacted log.
    5. ``Question:`` line with the user's first question.

    Follow-up turns send only the question — this function is called once
    per session.

    Args:
        log: Redacted log text to send to the model.
        question: The user's first question about the log.
        context: Optional context document text (e.g. runbook contents).
            Pass ``None`` or an empty string to omit the context block.
        host_map: Mapping of ``{original_hostname: label}`` from
            ``RedactSummary.host_map``.  Pass an empty dict when
            ``--redact-hosts`` is not active.

    Returns:
        Fully assembled prompt string for the first Copilot turn.
    """
    effective_context = context if context else None

    parts: list[str] = []

    # System instruction — include context hint when context is present
    if effective_context:
        parts.append(_SYSTEM_WITH_CONTEXT)
    else:
        parts.append(_SYSTEM)

    # Hostname substitution note
    if host_map:
        substitutions = ", ".join(f"{label}={original}" for original, label in host_map.items())
        parts.append(f"Hostname substitutions: {substitutions}")

    # Context block
    if effective_context:
        parts.append(f"<context>\n{effective_context}\n</context>")

    # Log block
    parts.append(f"<log>\n{log}\n</log>")

    # Question
    parts.append(f"Question: {question}")

    return "\n\n".join(parts)
