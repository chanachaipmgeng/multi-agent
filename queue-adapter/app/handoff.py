"""Parse the ``HANDOFF:`` YAML block agents emit at the end of a run (design §4.5)."""

from __future__ import annotations

import re
from typing import Any

import yaml

# Matches a trailing HANDOFF: block (YAML) — either fenced or bare.
_HANDOFF_RE = re.compile(
    r"(?:^|\n)HANDOFF:\s*\n((?:[ \t]+.+\n?)+)",
    re.MULTILINE,
)

_HANDOFF_FIELDS = (
    "to_agent",
    "branch",
    "worktree_path",
    "summary",
    "artifacts",
    "open_questions",
    "token_spent",
    "reason",
)


def parse_handoff(text: str | None) -> dict[str, Any] | None:
    """Extract the first ``HANDOFF:`` YAML block from agent output.

    Returns a dict with known fields, or ``None`` if absent / unparseable.
    """
    if not text:
        return None
    match = _HANDOFF_RE.search(text)
    if not match:
        # Also accept a fenced ```yaml HANDOFF: … ``` block
        fenced = re.search(
            r"```(?:ya?ml)?\s*\nHANDOFF:\s*\n((?:.+\n?)+?)```",
            text,
            re.IGNORECASE,
        )
        if not fenced:
            return None
        body = fenced.group(1)
    else:
        body = match.group(1)

    try:
        data = yaml.safe_load(body) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None

    result: dict[str, Any] = {}
    for key in _HANDOFF_FIELDS:
        if key in data and data[key] is not None:
            result[key] = data[key]
    if "to_agent" not in result and "to" in data:
        result["to_agent"] = data["to"]
    return result or None


def format_handoff_reminder() -> str:
    return (
        "เมื่อจบงาน ให้ปิดท้ายด้วยบล็อก HANDOFF (YAML) เสมอ:\n"
        "HANDOFF:\n"
        "  to_agent: <role หรือ empty ถ้า DONE>\n"
        "  branch: <branch>\n"
        "  worktree_path: <path หรือ empty>\n"
        "  summary: |\n"
        "    <สรุปสั้น ๆ>\n"
        "  artifacts: []\n"
        "  open_questions: |\n"
        "    <คำถามที่ต้องให้มนุษย์ตัดสิน ถ้ามี>\n"
        "  token_spent: 0\n"
        "  reason: done | review | needs_human | awaiting_approval\n"
    )
