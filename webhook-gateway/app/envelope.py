"""Task envelope — the shared contract between gateway, coordinator and workers.

See design §4.3. Every GitLab webhook that passes auth + allowlist is turned into
one :class:`Task`. Payloads that are not actionable (e.g. a successful pipeline,
an issue without the opt-in label) produce a :class:`NormalizeResult` with
``task=None`` and a machine-readable ``reason``.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from .projects import Project, ProjectRegistry

TaskType = Literal["issue", "feature", "pipeline_failed", "job_failed", "review", "deploy_request"]


class TaskState(StrEnum):
    RECEIVED = "RECEIVED"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED, TaskState.EXPIRED, TaskState.REJECTED}
)

# Default per-task budgets per worker (design §4.2).
WORKER_CONSTRAINTS: dict[str, dict[str, int]] = {
    "coordinator": {"token_budget": 50_000, "self_heal_limit": 0, "deadline_min": 15},
    "dev-frontend": {"token_budget": 400_000, "self_heal_limit": 3, "deadline_min": 60},
    "dev-backend": {"token_budget": 400_000, "self_heal_limit": 3, "deadline_min": 60},
    "reviewer": {"token_budget": 300_000, "self_heal_limit": 0, "deadline_min": 30},
    "devops": {"token_budget": 300_000, "self_heal_limit": 2, "deadline_min": 45},
    "qa": {"token_budget": 200_000, "self_heal_limit": 3, "deadline_min": 45},
}

DEFAULT_SKILL_FOR_TYPE: dict[str, str] = {
    "issue": "resolve-issue",
    "pipeline_failed": "incident-triage",
    "job_failed": "incident-triage",
}


class TaskSource(BaseModel):
    kind: Literal["gitlab_webhook", "github_webhook", "telegram", "manual"] = "gitlab_webhook"
    event: str | None = None
    event_uuid: str | None = None
    gitlab_project_id: int | None = None
    path_with_namespace: str | None = None
    repo: str | None = None  # owner/name (GitHub)
    repo_id: int | None = None  # GitHub numeric repository id
    issue_iid: int | None = None
    pipeline_id: int | None = None
    job_id: int | None = None
    url: str | None = None


class TaskRequester(BaseModel):
    channel: Literal["gitlab", "github", "telegram", "manual"] = "gitlab"
    user_id: int | None = None
    username: str | None = None
    role: str = "unknown"


class TaskConstraints(BaseModel):
    token_budget: int
    self_heal_limit: int
    deadline_min: int


class Task(BaseModel):
    task_id: str
    trace_id: str
    type: TaskType
    project: str
    source: TaskSource
    requester: TaskRequester
    assigned_to: str | None = None
    skill: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    constraints: TaskConstraints
    handoffs: list[dict[str, Any]] = Field(default_factory=list)
    state: TaskState = TaskState.QUEUED
    created_at: datetime


class NormalizeResult(BaseModel):
    task: Task | None
    status: Literal["queued", "recorded", "ignored"]
    reason: str | None = None


# --------------------------------------------------------------------------- ids
def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_task_id(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"t-{now:%Y%m%d}-{secrets.token_hex(3)}"


def fallback_event_uuid(body: bytes) -> str:
    """GitLab always sends ``X-Gitlab-Event-UUID``; if a proxy strips it, hash the body instead."""
    return "sha256:" + hashlib.sha256(body).hexdigest()


# -------------------------------------------------------------------- helpers
def _labels(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("labels") or payload.get("object_attributes", {}).get("labels") or []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get("title"):
            out.append(str(item["title"]))
        elif isinstance(item, str):
            out.append(item)
    return out


def _requester(payload: dict[str, Any]) -> TaskRequester:
    user = payload.get("user") or {}
    return TaskRequester(
        channel="gitlab",
        user_id=user.get("id"),
        username=user.get("username"),
        role="gitlab_user",
    )


def _constraints(worker: str) -> TaskConstraints:
    return TaskConstraints(**WORKER_CONSTRAINTS.get(worker, WORKER_CONSTRAINTS["dev-backend"]))


# ------------------------------------------------------------------ normalize
def normalize(
    *,
    event: str,
    event_uuid: str,
    payload: dict[str, Any],
    project: Project,
    registry: ProjectRegistry,
    now: datetime | None = None,
    scm: Literal["gitlab", "github"] = "gitlab",
) -> NormalizeResult:
    """Turn a verified SCM payload into a Task envelope (or an explicit non-action)."""
    now = now or datetime.now(UTC)
    if scm == "github":
        return normalize_github(
            event=event,
            event_uuid=event_uuid,
            payload=payload,
            project=project,
            registry=registry,
            now=now,
        )
    if event == "Issue Hook":
        return _normalize_issue(event, event_uuid, payload, project, registry, now)
    if event == "Pipeline Hook":
        return _normalize_pipeline(event, event_uuid, payload, project, registry, now)
    if event == "Job Hook":
        return _normalize_job(event, event_uuid, payload, project, registry, now)
    return NormalizeResult(task=None, status="ignored", reason="event_not_supported")


def normalize_github(
    *,
    event: str,
    event_uuid: str,
    payload: dict[str, Any],
    project: Project,
    registry: ProjectRegistry,
    now: datetime | None = None,
) -> NormalizeResult:
    """Turn a verified GitHub webhook payload into a Task envelope."""
    now = now or datetime.now(UTC)
    if event == "issues":
        return _normalize_github_issues(event, event_uuid, payload, project, registry, now)
    if event == "workflow_run":
        return _normalize_github_workflow_run(event, event_uuid, payload, project, registry, now)
    if event == "workflow_job":
        return _normalize_github_workflow_job(event, event_uuid, payload, project, registry, now)
    return NormalizeResult(task=None, status="ignored", reason="event_not_supported")


def _base_source(event: str, event_uuid: str, payload: dict[str, Any]) -> TaskSource:
    proj = payload.get("project") or {}
    return TaskSource(
        kind="gitlab_webhook",
        event=event,
        event_uuid=event_uuid,
        gitlab_project_id=proj.get("id"),
        path_with_namespace=proj.get("path_with_namespace"),
    )


def _normalize_issue(
    event: str,
    event_uuid: str,
    payload: dict[str, Any],
    project: Project,
    registry: ProjectRegistry,
    now: datetime,
) -> NormalizeResult:
    attrs = payload.get("object_attributes") or {}
    action = attrs.get("action")
    labels = _labels(payload)
    source = _base_source(event, event_uuid, payload)
    source.issue_iid = attrs.get("iid")
    source.url = attrs.get("url")

    if attrs.get("state") == "closed" or action == "close":
        return NormalizeResult(task=None, status="ignored", reason="issue_closed")
    if action not in {"open", "reopen", "update"}:
        return NormalizeResult(task=None, status="ignored", reason=f"issue_action_{action}")

    worker = registry.route(project, "issue", labels)
    task = Task(
        task_id=new_task_id(now),
        trace_id=new_trace_id(),
        type="issue",
        project=project.key,
        source=source,
        requester=_requester(payload),
        assigned_to=worker,
        skill=DEFAULT_SKILL_FOR_TYPE["issue"],
        inputs={
            "issue_iid": attrs.get("iid"),
            "issue_title": attrs.get("title"),
            "issue_body": attrs.get("description") or "",
            "labels": labels,
            "action": action,
            "workspace_path": project.workspace_path,
            "test_command": project.test_command,
            "branch": f"fix/issue-{attrs.get('iid')}",
            "data_classification": project.data_classification,
            "llm_backend": project.llm_backend,
        },
        constraints=_constraints(worker),
        created_at=now,
    )

    # Opt-in policy (DECISION-13): record but never start work without the label.
    if project.opt_in_label not in labels:
        task.state = TaskState.RECEIVED
        task.assigned_to = None
        return NormalizeResult(task=task, status="recorded", reason="opt_in_label_missing")

    # On "update" only react when the opt-in label was just added, otherwise every
    # edit of an already-tracked issue would spawn a duplicate task.
    if action == "update":
        added = {
            lbl.get("title")
            for lbl in (payload.get("changes", {}).get("labels", {}).get("current") or [])
            if isinstance(lbl, dict)
        }
        previous = {
            lbl.get("title")
            for lbl in (payload.get("changes", {}).get("labels", {}).get("previous") or [])
            if isinstance(lbl, dict)
        }
        if project.opt_in_label not in (added - previous):
            return NormalizeResult(task=None, status="ignored", reason="issue_update_not_opt_in")

    task.state = TaskState.QUEUED
    return NormalizeResult(task=task, status="queued")


def _normalize_pipeline(
    event: str,
    event_uuid: str,
    payload: dict[str, Any],
    project: Project,
    registry: ProjectRegistry,
    now: datetime,
) -> NormalizeResult:
    attrs = payload.get("object_attributes") or {}
    status = attrs.get("status")
    if status != "failed":
        return NormalizeResult(task=None, status="ignored", reason=f"pipeline_status_{status}")

    failed_jobs = [
        {"id": b.get("id"), "name": b.get("name"), "stage": b.get("stage")}
        for b in payload.get("builds", [])
        if b.get("status") == "failed"
    ]
    source = _base_source(event, event_uuid, payload)
    source.pipeline_id = attrs.get("id")
    source.url = attrs.get("url")
    worker = registry.route(project, "pipeline_failed", [])
    task = Task(
        task_id=new_task_id(now),
        trace_id=new_trace_id(),
        type="pipeline_failed",
        project=project.key,
        source=source,
        requester=_requester(payload),
        assigned_to=worker,
        skill=DEFAULT_SKILL_FOR_TYPE["pipeline_failed"],
        inputs={
            "pipeline_id": attrs.get("id"),
            "ref": attrs.get("ref"),
            "sha": attrs.get("sha"),
            "status": status,
            "failed_jobs": failed_jobs,
            "workspace_path": project.workspace_path,
            "branch": f"hotfix/ci-{attrs.get('id')}",
            "data_classification": project.data_classification,
            "llm_backend": project.llm_backend,
        },
        constraints=_constraints(worker),
        state=TaskState.QUEUED,
        created_at=now,
    )
    return NormalizeResult(task=task, status="queued")


def _normalize_job(
    event: str,
    event_uuid: str,
    payload: dict[str, Any],
    project: Project,
    registry: ProjectRegistry,
    now: datetime,
) -> NormalizeResult:
    status = payload.get("build_status")
    if status != "failed":
        return NormalizeResult(task=None, status="ignored", reason=f"job_status_{status}")
    if payload.get("build_allow_failure"):
        return NormalizeResult(task=None, status="ignored", reason="job_allow_failure")

    source = _base_source(event, event_uuid, payload)
    # Job Hook payloads carry the project under "repository"/"project_id" rather than "project".
    source.gitlab_project_id = source.gitlab_project_id or payload.get("project_id")
    source.job_id = payload.get("build_id")
    source.pipeline_id = payload.get("pipeline_id")
    worker = registry.route(project, "job_failed", [])
    task = Task(
        task_id=new_task_id(now),
        trace_id=new_trace_id(),
        type="job_failed",
        project=project.key,
        source=source,
        requester=_requester(payload),
        assigned_to=worker,
        skill=DEFAULT_SKILL_FOR_TYPE["job_failed"],
        inputs={
            "job_id": payload.get("build_id"),
            "job_name": payload.get("build_name"),
            "stage": payload.get("build_stage"),
            "pipeline_id": payload.get("pipeline_id"),
            "ref": payload.get("ref"),
            "sha": payload.get("sha"),
            "failure_reason": payload.get("build_failure_reason"),
            "workspace_path": project.workspace_path,
            "branch": f"hotfix/ci-{payload.get('pipeline_id')}",
            "data_classification": project.data_classification,
            "llm_backend": project.llm_backend,
        },
        constraints=_constraints(worker),
        state=TaskState.QUEUED,
        created_at=now,
    )
    return NormalizeResult(task=task, status="queued")


# ---------------------------------------------------------- GitHub normalize
def _github_labels(payload: dict[str, Any]) -> list[str]:
    issue = payload.get("issue") or {}
    raw = issue.get("labels") or []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get("name"):
            out.append(str(item["name"]))
        elif isinstance(item, str):
            out.append(item)
    return out


def _github_requester(payload: dict[str, Any]) -> TaskRequester:
    user = payload.get("sender") or {}
    return TaskRequester(
        channel="github",
        user_id=user.get("id"),
        username=user.get("login"),
        role="github_user",
    )


def _github_base_source(event: str, event_uuid: str, payload: dict[str, Any]) -> TaskSource:
    repo = payload.get("repository") or {}
    full_name = repo.get("full_name")
    return TaskSource(
        kind="github_webhook",
        event=event,
        event_uuid=event_uuid,
        repo=full_name,
        repo_id=repo.get("id"),
        path_with_namespace=full_name,
    )


def _normalize_github_issues(
    event: str,
    event_uuid: str,
    payload: dict[str, Any],
    project: Project,
    registry: ProjectRegistry,
    now: datetime,
) -> NormalizeResult:
    action = payload.get("action")
    issue = payload.get("issue") or {}
    labels = _github_labels(payload)
    source = _github_base_source(event, event_uuid, payload)
    source.issue_iid = issue.get("number")
    source.url = issue.get("html_url")

    if issue.get("state") == "closed" or action == "closed":
        return NormalizeResult(task=None, status="ignored", reason="issue_closed")
    if action not in {"opened", "reopened", "labeled"}:
        return NormalizeResult(task=None, status="ignored", reason=f"issue_action_{action}")

    worker = registry.route(project, "issue", labels)
    task = Task(
        task_id=new_task_id(now),
        trace_id=new_trace_id(),
        type="issue",
        project=project.key,
        source=source,
        requester=_github_requester(payload),
        assigned_to=worker,
        skill=DEFAULT_SKILL_FOR_TYPE["issue"],
        inputs={
            "issue_iid": issue.get("number"),
            "issue_title": issue.get("title"),
            "issue_body": issue.get("body") or "",
            "labels": labels,
            "action": action,
            "workspace_path": project.workspace_path,
            "test_command": project.test_command,
            "branch": f"fix/issue-{issue.get('number')}",
            "data_classification": project.data_classification,
            "llm_backend": project.llm_backend,
            "scm": project.scm,
            "repo": project.repo or project.path_with_namespace,
        },
        constraints=_constraints(worker),
        created_at=now,
    )

    if project.opt_in_label not in labels:
        task.state = TaskState.RECEIVED
        task.assigned_to = None
        return NormalizeResult(task=task, status="recorded", reason="opt_in_label_missing")

    if action == "labeled":
        lbl = payload.get("label") or {}
        if (lbl.get("name") or "") != project.opt_in_label:
            return NormalizeResult(task=None, status="ignored", reason="issue_update_not_opt_in")

    task.state = TaskState.QUEUED
    return NormalizeResult(task=task, status="queued")


def _normalize_github_workflow_run(
    event: str,
    event_uuid: str,
    payload: dict[str, Any],
    project: Project,
    registry: ProjectRegistry,
    now: datetime,
) -> NormalizeResult:
    run = payload.get("workflow_run") or {}
    if run.get("conclusion") != "failure":
        return NormalizeResult(
            task=None,
            status="ignored",
            reason=f"workflow_run_conclusion_{run.get('conclusion')}",
        )

    source = _github_base_source(event, event_uuid, payload)
    source.pipeline_id = run.get("id")
    source.url = run.get("html_url")
    worker = registry.route(project, "pipeline_failed", [])
    task = Task(
        task_id=new_task_id(now),
        trace_id=new_trace_id(),
        type="pipeline_failed",
        project=project.key,
        source=source,
        requester=_github_requester(payload),
        assigned_to=worker,
        skill=DEFAULT_SKILL_FOR_TYPE["pipeline_failed"],
        inputs={
            "pipeline_id": run.get("id"),
            "ref": run.get("head_branch"),
            "sha": run.get("head_sha"),
            "status": run.get("conclusion"),
            "failed_jobs": [],
            "workspace_path": project.workspace_path,
            "branch": f"hotfix/ci-{run.get('id')}",
            "data_classification": project.data_classification,
            "llm_backend": project.llm_backend,
            "scm": project.scm,
            "repo": project.repo or project.path_with_namespace,
        },
        constraints=_constraints(worker),
        state=TaskState.QUEUED,
        created_at=now,
    )
    return NormalizeResult(task=task, status="queued")


def _normalize_github_workflow_job(
    event: str,
    event_uuid: str,
    payload: dict[str, Any],
    project: Project,
    registry: ProjectRegistry,
    now: datetime,
) -> NormalizeResult:
    action = payload.get("action")
    job = payload.get("workflow_job") or {}
    if action not in {"completed"}:
        return NormalizeResult(task=None, status="ignored", reason=f"workflow_job_action_{action}")
    if job.get("conclusion") != "failure":
        return NormalizeResult(
            task=None,
            status="ignored",
            reason=f"job_status_{job.get('conclusion')}",
        )

    source = _github_base_source(event, event_uuid, payload)
    source.job_id = job.get("id")
    source.pipeline_id = job.get("run_id")
    source.url = job.get("html_url")
    worker = registry.route(project, "job_failed", [])
    labels = job.get("labels") if isinstance(job.get("labels"), list) else []
    task = Task(
        task_id=new_task_id(now),
        trace_id=new_trace_id(),
        type="job_failed",
        project=project.key,
        source=source,
        requester=_github_requester(payload),
        assigned_to=worker,
        skill=DEFAULT_SKILL_FOR_TYPE["job_failed"],
        inputs={
            "job_id": job.get("id"),
            "job_name": job.get("name"),
            "stage": labels[0] if labels else None,
            "pipeline_id": job.get("run_id"),
            "ref": job.get("head_branch"),
            "sha": job.get("head_sha"),
            "failure_reason": job.get("conclusion"),
            "workspace_path": project.workspace_path,
            "branch": f"hotfix/ci-{job.get('run_id')}",
            "data_classification": project.data_classification,
            "llm_backend": project.llm_backend,
            "scm": project.scm,
            "repo": project.repo or project.path_with_namespace,
        },
        constraints=_constraints(worker),
        state=TaskState.QUEUED,
        created_at=now,
    )
    return NormalizeResult(task=task, status="queued")
