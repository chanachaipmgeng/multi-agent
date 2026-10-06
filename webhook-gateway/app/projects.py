"""Project allowlist and deterministic routing rules (design §4.4, §5.3).

``projects.yaml`` is the single source of truth for which GitLab projects the
workspace is allowed to act on, which worker owns each repo, and the opt-in label.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

KNOWN_WORKERS: frozenset[str] = frozenset(
    {"coordinator", "dev-frontend", "dev-backend", "reviewer", "devops", "qa"}
)


class Project(BaseModel):
    key: str
    gitlab_project_id: int
    path_with_namespace: str
    workspace_path: str
    default_worker: str
    allowed_workers: list[str] = Field(default_factory=list)
    test_command: str = ""
    e2e_port: int | None = None
    opt_in_label: str = "agent-ready"
    auto_push_branches: list[str] = Field(default_factory=list)  # DECISION-8: empty = always ask
    data_classification: str = "internal"  # internal | confidential | restricted (DECISION-3)
    llm_backend: str = "cloud"  # cloud | ollama (hybrid policy, DECISION-3)


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

    # ------------------------------------------------------------------ load
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
        if self.routing.pipeline_failed_worker not in KNOWN_WORKERS:
            raise ValueError("routing.pipeline_failed_worker must be a known worker")

    # ---------------------------------------------------------------- lookup
    def by_gitlab_id(self, project_id: int | None) -> Project | None:
        if project_id is None:
            return None
        return next((p for p in self.projects if p.gitlab_project_id == project_id), None)

    def by_path(self, path_with_namespace: str | None) -> Project | None:
        if not path_with_namespace:
            return None
        return next(
            (p for p in self.projects if p.path_with_namespace == path_with_namespace), None
        )

    def resolve(self, project_id: int | None, path_with_namespace: str | None) -> Project | None:
        """Allowlist check: the project must match by id (preferred) or by path."""
        return self.by_gitlab_id(project_id) or self.by_path(path_with_namespace)

    # --------------------------------------------------------------- routing
    def route(self, project: Project, task_type: str, labels: list[str]) -> str:
        """Deterministic routing per design §4.4 (rules 1, 2 and 4).

        Rule 3 (Telegram tags) and rule 5 (LLM + ask user) belong to the
        coordinator, not the gateway.
        """
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
