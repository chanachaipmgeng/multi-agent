"""projects.yaml validation and lookup."""

from __future__ import annotations

import pytest

from app.projects import ProjectRegistry


def test_repo_projects_yaml_is_valid(registry: ProjectRegistry) -> None:
    keys = {p.key for p in registry.projects}
    assert {"frontend-app", "backend-api", "sandbox-smoke"} <= keys
    for p in registry.projects:
        assert p.opt_in_label == "agent-ready"
        assert p.auto_push_branches == [], "DECISION-8: no auto-push in the first 2 months"
        assert p.default_worker in p.allowed_workers


def test_lookup_by_id_then_path(registry: ProjectRegistry) -> None:
    assert registry.resolve(12345, None).key == "frontend-app"
    assert registry.resolve(None, "acme/backend-api").key == "backend-api"
    assert registry.resolve(1, "acme/backend-api").key == "backend-api"
    assert registry.resolve(1, "nope/nope") is None
    assert registry.resolve(None, None) is None


def test_unknown_worker_rejected(tmp_path) -> None:
    f = tmp_path / "projects.yaml"
    f.write_text(
        """
projects:
  - key: x
    gitlab_project_id: 1
    path_with_namespace: a/x
    workspace_path: /workspace/x
    default_worker: dev-mobile
    allowed_workers: [dev-mobile]
"""
    )
    with pytest.raises(ValueError, match="unknown workers"):
        ProjectRegistry.from_yaml(f)


def test_default_worker_must_be_allowed(tmp_path) -> None:
    f = tmp_path / "projects.yaml"
    f.write_text(
        """
projects:
  - key: x
    gitlab_project_id: 1
    path_with_namespace: a/x
    workspace_path: /workspace/x
    default_worker: dev-backend
    allowed_workers: [reviewer]
"""
    )
    with pytest.raises(ValueError, match="must be listed in allowed_workers"):
        ProjectRegistry.from_yaml(f)
