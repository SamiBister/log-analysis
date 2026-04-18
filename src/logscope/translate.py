"""Reverse translation of redacted labels back to original values.

After the model streams its response, host-A/host-B labels and indexed
IP placeholders are replaced with the original values so the engineer
reads a natural, recognisable answer.

Secrets and PII are **never** translated back.
"""

from __future__ import annotations

import re


def build_translation_map(
    host_map: dict[str, str],
    ip_map: dict[str, str],
) -> dict[str, str]:
    """Build a label → original lookup for reverse translation.

    Args:
        host_map: Mapping of ``{original_hostname: label}`` from
            ``RedactSummary.host_map``.
        ip_map: Mapping of ``{original_ip: placeholder}`` from
            ``RedactSummary.ip_map``.

    Returns:
        Dict mapping each label/placeholder back to its original value.
        Returns an empty dict if both inputs are empty.
    """
    reverse: dict[str, str] = {}
    for original, label in host_map.items():
        reverse[label] = original
    for original, placeholder in ip_map.items():
        reverse[placeholder] = original
    return reverse


def translate(text: str, translation_map: dict[str, str]) -> str:
    """Replace all label and placeholder occurrences in *text* with originals.

    Replaces the longest matching keys first to avoid partial substitution
    conflicts (e.g. ``host-AA`` being partially replaced by a ``host-A``
    match before ``host-AA`` is handled).

    Args:
        text: Model output text to translate.
        translation_map: Label/placeholder → original value mapping as
            returned by :func:`build_translation_map`.

    Returns:
        Text with all known labels and placeholders restored to their
        original values.  Secrets and PII placeholders are left unchanged.
    """
    if not translation_map:
        return text

    # Sort by length descending so host-AA is replaced before host-A
    sorted_keys = sorted(translation_map.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in sorted_keys))
    return pattern.sub(lambda m: translation_map[m.group(0)], text)
