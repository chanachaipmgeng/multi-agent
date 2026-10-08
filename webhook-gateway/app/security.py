"""Webhook authentication helpers."""

from __future__ import annotations

import hashlib
import hmac


def verify_gitlab_token(presented: str | None, expected: str) -> bool:
    """Constant-time comparison of the ``X-Gitlab-Token`` header.

    A missing header is always a failure. ``hmac.compare_digest`` is used so a
    wrong token of a different length does not leak timing information about the
    expected value.
    """
    if presented is None or expected == "":
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def verify_github_signature(signature_header: str | None, body: bytes, secret: str) -> bool:
    """Verify GitHub ``X-Hub-Signature-256`` (HMAC-SHA256 of the raw body).

    Header format: ``sha256=<hex digest>``. Missing/malformed header or empty
    secret always fails.
    """
    if not signature_header or not secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    presented = signature_header[len("sha256=") :]
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(presented, expected)
