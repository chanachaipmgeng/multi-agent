"""Webhook authentication helpers."""

from __future__ import annotations

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
