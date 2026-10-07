"""Coordinator RBAC loader (design §6.2, D3.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RbacUser(BaseModel):
    name: str = ""
    roles: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)  # ["*"] or project keys


class RbacPolicy(BaseModel):
    users: dict[str, RbacUser] = Field(default_factory=dict)  # telegram user id → user
    roles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    commands: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> RbacPolicy:
        p = Path(path)
        if not p.is_file():
            return cls()
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        # Normalise user keys to strings
        users_raw = data.get("users") or {}
        users = {str(k): RbacUser.model_validate(v) for k, v in users_raw.items()}
        return cls(
            users=users,
            roles=data.get("roles") or {},
            commands=data.get("commands") or {},
        )

    def user(self, user_id: int | str | None) -> RbacUser | None:
        if user_id is None:
            return None
        return self.users.get(str(user_id))

    def authorize(
        self,
        user_id: int | str | None,
        command: str,
        project: str | None = None,
    ) -> tuple[bool, str]:
        """Return ``(allowed, reason)``."""
        u = self.user(user_id)
        if u is None:
            return False, "user_not_in_rbac"
        cmd = self.commands.get(command)
        if cmd is None:
            # Unknown command — deny by default
            return False, f"unknown_command:{command}"
        allowed_roles = set(cmd.get("roles") or [])
        if not (set(u.roles) & allowed_roles):
            return False, "role_denied"
        if project and "*" not in u.projects and project not in u.projects:
            return False, "project_denied"
        return True, "ok"

    def has_role(self, user_id: int | str | None, role: str) -> bool:
        u = self.user(user_id)
        return bool(u and role in u.roles)

    def is_approver_conflict(self, user_id: int | str | None, project: str | None) -> bool:
        """DECISION-8: approver must not also be developer on the same repo (except admin bootstrap)."""
        u = self.user(user_id)
        if u is None:
            return True
        if "admin" in u.roles:
            return False  # pilot bootstrap exception
        if "approver" in u.roles and "developer" in u.roles:
            if project is None or "*" in u.projects or (project and project in u.projects):
                return True
        return False
