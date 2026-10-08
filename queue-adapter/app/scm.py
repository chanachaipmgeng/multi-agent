"""SCM client protocol and factory (GitLab + GitHub enrichment)."""

from __future__ import annotations

from typing import Any, Protocol

from .github import GitHubClient
from .gitlab import GitLabClient
from .projects import Project, ProjectRegistry
from .settings import Settings


class ScmClient(Protocol):
    async def enrich(self, task: dict[str, Any]) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


class ScmRouter:
    """Pick GitLabClient or GitHubClient per task; default GitLab for legacy envelopes."""

    def __init__(
        self,
        gitlab: GitLabClient,
        github: GitHubClient,
        *,
        registry: ProjectRegistry | None = None,
    ) -> None:
        self.gitlab = gitlab
        self.github = github
        self.registry = registry

    def client_for(self, task: dict[str, Any]) -> ScmClient:
        scm = self._detect_scm(task)
        if scm == "github":
            return self.github
        return self.gitlab

    def _detect_scm(self, task: dict[str, Any]) -> str:
        inputs = task.get("inputs") or {}
        if inputs.get("scm") in {"gitlab", "github"}:
            return str(inputs["scm"])

        source = task.get("source") or {}
        kind = source.get("kind") or ""
        if kind.startswith("github"):
            return "github"
        if kind.startswith("gitlab"):
            return "gitlab"

        if self.registry is not None:
            project: Project | None = self.registry.by_key(task.get("project"))
            if project is not None:
                return project.scm

        # Legacy tasks: prefer GitLab so old envelopes keep working.
        return "gitlab"

    async def enrich(self, task: dict[str, Any]) -> dict[str, Any]:
        return await self.client_for(task).enrich(task)

    async def aclose(self) -> None:
        await self.gitlab.aclose()
        await self.github.aclose()


def build_scm_router(settings: Settings, *, registry: ProjectRegistry | None = None) -> ScmRouter:
    gitlab = GitLabClient(
        settings.gitlab_base_url,
        settings.gitlab_token,
        trace_max_bytes=settings.trace_max_bytes,
    )
    github = GitHubClient(
        settings.github_base_url,
        settings.github_token,
        trace_max_bytes=settings.trace_max_bytes,
    )
    return ScmRouter(gitlab, github, registry=registry)
