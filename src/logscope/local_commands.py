"""Local command handler for logscope.

Before sending a follow-up question to Copilot, the session loop checks
whether the question can be answered locally from the redaction maps.
This avoids unnecessary Copilot API calls for simple label lookups.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LocalAnswer:
    """Result of a local command check.

    Attributes:
        text: The answer text to print (may be empty when ``handled=False``).
        handled: True if the query was answered locally and must NOT be
            forwarded to Copilot.
    """

    text: str
    handled: bool


def handle_locally(
    query: str,
    host_map: dict[str, str],
    ip_map: dict[str, str],
) -> LocalAnswer:
    """Check whether *query* can be answered locally from the redaction maps.

    Handles label lookups (``what is host-a``), map listing commands
    (``list hosts``, ``show ips``, ``mappings``), and ``help``.

    Matching is case-insensitive.  Trailing ``?``, ``.``, and ``!`` are
    stripped before matching.

    Args:
        query: Raw user input string.
        host_map: Original hostname → assigned label from
            ``RedactSummary.host_map``.
        ip_map: Original IP → placeholder from ``RedactSummary.ip_map``.

    Returns:
        :class:`LocalAnswer` with ``handled=True`` and the answer text if
        resolvable locally, or ``handled=False`` if the query should go to
        Copilot.
    """
    q = query.strip().lower().rstrip("?.!")

    # Build reverse maps: label (lower) → original
    reverse_hosts = {label.lower(): original for original, label in host_map.items()}
    reverse_ips = {ph.lower(): original for original, ph in ip_map.items()}

    # --- single label lookup ---
    # Sort by descending length so "host-ab" is checked before "host-a"
    # preventing a shorter label from matching inside a longer one.
    for label_lower, original in sorted(
        reverse_hosts.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if label_lower in q:
            # Display label preserving the "host-X" capitalisation convention
            label_display = label_lower  # already lowercase e.g. "host-a"
            # Capitalise the suffix part: host-a → host-A
            parts = label_display.split("-", 1)
            if len(parts) == 2:
                label_display = f"{parts[0]}-{parts[1].upper()}"
            return LocalAnswer(text=f"{label_display}  =  {original}", handled=True)

    for placeholder_lower, original in reverse_ips.items():
        if placeholder_lower in q:
            return LocalAnswer(
                text=f"{placeholder_lower}  =  {original}",
                handled=True,
            )

    # --- list / map commands ---
    wants_hosts = any(kw in q for kw in ("host map", "list host", "show host", "all host"))
    wants_ips = any(kw in q for kw in ("ip map", "list ip", "show ip", "all ip"))
    wants_all = any(kw in q for kw in ("list all", "show all", "mapping", "all map"))

    if wants_all:
        wants_hosts = wants_ips = True

    lines: list[str] = []
    if wants_hosts and host_map:
        lines.append("Hosts:")
        for original, label in host_map.items():
            lines.append(f"  {label:<10}  =  {original}")
    if wants_ips and ip_map:
        lines.append("IPs:")
        for original, placeholder in ip_map.items():
            lines.append(f"  {placeholder:<20}  =  {original}")

    if wants_hosts or wants_ips:
        # Even if maps are empty, we handled the command
        return LocalAnswer(text="\n".join(lines), handled=True)

    # --- help ---  (check raw query too so bare "?" survives rstrip)
    if q in ("help", "commands") or query.strip() in ("?", "help", "commands"):
        return LocalAnswer(text=_help_text(), handled=True)

    return LocalAnswer(text="", handled=False)


def _help_text() -> str:
    """Return the help text for local commands.

    Returns:
        Multi-line help string.
    """
    return """Local commands (answered instantly, no Copilot call):
  what is host-a       show original hostname for a label
  list hosts           show all host label → hostname mappings
  list ips             show all IP placeholder → IP mappings
  list all             show both host and IP mappings
  help                 show this message

All other input is sent to Copilot."""
