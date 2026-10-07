"""RBAC policy unit tests."""

from __future__ import annotations

from pathlib import Path

from app.rbac import RbacPolicy


def test_authorize_route_task(tmp_path: Path) -> None:
    p = tmp_path / "rbac.yaml"
    p.write_text(
        """
users:
  1: { name: "dev", roles: [developer], projects: ["frontend-app"] }
  2: { name: "admin", roles: [admin], projects: ["*"] }
commands:
  route-task: { roles: [developer, admin] }
  pause: { roles: [admin] }
""",
        encoding="utf-8",
    )
    policy = RbacPolicy.from_yaml(p)
    assert policy.authorize(1, "route-task", "frontend-app") == (True, "ok")
    assert policy.authorize(1, "route-task", "backend-api")[0] is False
    assert policy.authorize(1, "pause")[0] is False
    assert policy.authorize(2, "pause") == (True, "ok")


def test_approver_developer_conflict() -> None:
    policy = RbacPolicy.model_validate(
        {
            "users": {
                "9": {"name": "both", "roles": ["approver", "developer"], "projects": ["*"]},
                "1": {
                    "name": "admin",
                    "roles": ["admin", "approver", "developer"],
                    "projects": ["*"],
                },
            }
        }
    )
    assert policy.is_approver_conflict(9, "frontend-app") is True
    assert policy.is_approver_conflict(1, "frontend-app") is False  # admin bootstrap
