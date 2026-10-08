"""Project allowlist and deterministic routing (mirrored from webhook-gateway, design §4.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

KNOWN_WORKERS: frozenset[str] = frozenset(
    {"coordinator", "dev-frontend", "dev-backend", "reviewer", "devops", "qa"}
)

DEV_WORKERS: frozenset[str] = frozenset({"dev-frontend", "dev-backend"})

ScmKind = Literal["gitlab", "github"]


class Project(BaseModel):
    key: str
    scm: ScmKind = "gitlab"
    gitlab_project_id: int | None = None
    path_with_namespace: str = ""
    repo: str | None = None
    repo_id: int | None = None
    workspace_path: str
    default_worker: str
    allowed_workers: list[str] = Field(default_factory=list)
    test_command: str = ""
    e2e_port: int | None = None
    opt_in_label: str = "agent-ready"
    auto_push_branches: list[str] = Field(default_factory=list)
    data_classification: str = "internal"
    llm_backend: str = "cloud"

    @model_validator(mode="after")
    def _require_scm_ids(self) -> Project:
        if self.scm == "gitlab":
            if self.gitlab_project_id is None and not self.path_with_namespace:
                raise ValueError(
                    f"project {self.key!r} (scm=gitlab) needs gitlab_project_id or path_with_namespace"
                )
        elif self.scm == "github":
            if self.repo_id is None and not (self.repo or self.path_with_namespace):
                raise ValueError(
                    f"project {self.key!r} (scm=github) needs repo_id or repo/path_with_namespace"
                )
            if not self.repo and self.path_with_namespace:
                self.repo = self.path_with_namespace
            if not self.path_with_namespace and self.repo:
                self.path_with_namespace = self.repo
        return self


class RoutingRules(BaseModel):
    label_prefix: str = "area:"
    pipeline_failed_worker: str = "devops"
    unknown_intent: str = "ask_user"
    label_to_worker: dict[str, str] = Field(
        default_factory=lambda: {
            "frontend": "dev-frontend",
            "backend": "dev-backend",
            "ci": "devops",
            "qa": "qa",
        }
    )


class ProjectRegistry(BaseModel):
    projects: list[Project]
    routing: RoutingRules = Field(default_factory=RoutingRules)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ProjectRegistry:
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        registry = cls.model_validate(data)
        registry.validate_workers()
        return registry

    def validate_workers(self) -> None:
        for p in self.projects:
            unknown = {p.default_worker, *p.allowed_workers} - KNOWN_WORKERS
            if unknown:
                raise ValueError(f"project {p.key!r} references unknown workers: {sorted(unknown)}")
            if p.default_worker not in p.allowed_workers:
                raise ValueError(
                    f"project {p.key!r}: default_worker {p.default_worker!r} "
                    "must be listed in allowed_workers"
                )

    def by_key(self, key: str | None) -> Project | None:
        if not key:
            return None
        return next((p for p in self.projects if p.key == key), None)

    def route(self, project: Project, task_type: str, labels: list[str]) -> str:
        if task_type in {"pipeline_failed", "job_failed"}:
            return self.routing.pipeline_failed_worker
        prefix = self.routing.label_prefix
        for label in labels:
            if label.startswith(prefix):
                area = label[len(prefix) :]
                worker = self.routing.label_to_worker.get(area)
                if worker and worker in project.allowed_workers:
                    return worker
        return project.default_worker

    def resolve_worker(self, task: dict[str, Any]) -> str:
        """Confirm or correct ``assigned_to`` against projects.yaml rules 1/2/4."""
        project = self.by_key(task.get("project"))
        proposed = task.get("assigned_to") or ""
        if project is None:
            return proposed or "dev-backend"
        if proposed and proposed in project.allowed_workers:
            return proposed
        labels = list((task.get("inputs") or {}).get("labels") or [])
        return self.route(project, str(task.get("type") or ""), labels)
