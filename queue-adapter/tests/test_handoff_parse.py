"""Unit tests for HANDOFF block parsing."""

from __future__ import annotations

from app.handoff import parse_handoff


def test_parse_bare_handoff_block() -> None:
    text = """
สรุป: แก้ layout แล้ว test ผ่าน

HANDOFF:
  to_agent: reviewer
  branch: fix/issue-89
  worktree_path: /workspace/.worktrees/fix-issue-89
  summary: |
    Mobile overflow fixed
  artifacts: []
  open_questions: |
  token_spent: 12000
  reason: review
"""
    h = parse_handoff(text)
    assert h is not None
    assert h["to_agent"] == "reviewer"
    assert h["branch"] == "fix/issue-89"
    assert "Mobile overflow" in h["summary"]
    assert h["token_spent"] == 12000
    assert h["reason"] == "review"


def test_parse_fenced_handoff() -> None:
    text = """
Done.

```yaml
HANDOFF:
  to_agent: qa
  reason: done
  summary: smoke ready
```
"""
    h = parse_handoff(text)
    assert h is not None
    assert h["to_agent"] == "qa"
    assert h["reason"] == "done"


def test_parse_to_alias() -> None:
    text = """
HANDOFF:
  to: reviewer
  reason: review
"""
    h = parse_handoff(text)
    assert h is not None
    assert h["to_agent"] == "reviewer"


def test_parse_missing_returns_none() -> None:
    assert parse_handoff("just a summary, no block") is None
    assert parse_handoff(None) is None
    assert parse_handoff("") is None
