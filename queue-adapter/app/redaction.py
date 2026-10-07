"""Redact credentials before CI logs reach a prompt or the audit log (design §6.3)."""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"glpat-[0-9A-Za-z_\-]{20,}"), "glpat-[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "sk-[REDACTED]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"AGE-SECRET-KEY-1[0-9A-Z]{58}"), "AGE-SECRET-KEY-1[REDACTED]"),
    (re.compile(r"\b[0-9]{8,10}:[A-Za-z0-9_-]{35}\b"), "[REDACTED-TELEGRAM-TOKEN]"),
    (re.compile(r"eyJhIjoi[A-Za-z0-9+/=]{80,}"), "[REDACTED-TUNNEL-TOKEN]"),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED-PRIVATE-KEY]",
    ),
    # KEY=value style assignments commonly echoed by CI
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|APIKEY|PRIVATE_KEY)[A-Z0-9_]*)"
            r"\s*[=:]\s*['\"]?([^\s'\"]{6,})"
        ),
        r"\1=[REDACTED]",
    ),
    # basic-auth credentials inside URLs
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1[REDACTED]@"),
)


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def tail(text: str, max_bytes: int) -> str:
    """Keep the *end* of a log (where the failure is), bounded by ``max_bytes``."""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= max_bytes:
        return text
    cut = data[-max_bytes:].decode("utf-8", errors="ignore")
    return f"…[truncated {len(data) - max_bytes} bytes]…\n{cut}"
