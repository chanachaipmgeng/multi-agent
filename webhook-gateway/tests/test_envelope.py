"""Normalization of GitLab payloads into the Task envelope (design §4.3, §4.4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.envelope import Task, TaskState, normalize

from .conftest import gitlab_headers

NOW = datetime(2026, 10, 6, 19, 40, tzinfo=UTC)


def _project(registry, key):
    return next(p for p in registry.projects if p.key == key)


# ----------------------------------------------------------------- unit level
def test_issue_hook_becomes_issue_task_routed_by_area_label(registry, issue_payload) -> None:
    result = normalize(
        event="Issue Hook",
        event_uuid="evt",
        payload=issue_payload,
        project=_project(registry, "frontend-app"),
        registry=registry,
        now=NOW,
    )
    assert result.status == "queued"
    task = result.task
    assert task is not None
    assert task.type == "issue"
    assert task.project == "frontend-app"
    assert task.assigned_to == "dev-frontend"
    assert task.skill == "resolve-issue"
    assert task.state is TaskState.QUEUED
    assert task.task_id.startswith("t-20261006-")
    assert len(task.trace_id) == 32
    assert task.source.kind == "gitlab_webhook"
    assert task.source.event_uuid == "evt"
    assert task.source.issue_iid == 89
    assert task.requester.user_id == 987654321
    assert task.inputs["issue_title"] == "Mobile layout overflows on dashboard"
    assert task.inputs["labels"] == ["agent-ready", "area:frontend", "bug"]
    assert task.inputs["branch"] == "fix/issue-89"
    assert task.inputs["workspace_path"] == "/workspace/frontend-app"
    assert task.constraints.model_dump() == {
        "token_budget": 400_000,
        "self_heal_limit": 3,
        "deadline_min": 60,
    }
    assert task.handoffs == []
    assert task.created_at == NOW


def test_area_label_overrides_default_worker_when_allowed(registry, issue_payload) -> None:
    labels = [{"id": 1, "title": "agent-ready"}, {"id": 2, "title": "area:qa"}]
    issue_payload["labels"] = labels
    issue_payload["object_attributes"]["labels"] = labels
    result = normalize(
        event="Issue Hook",
        event_uuid="e",
        payload=issue_payload,
        project=_project(registry, "frontend-app"),
        registry=registry,
    )
    assert result.task is not None and result.task.assigned_to == "qa"
    assert result.task.constraints.token_budget == 200_000


def test_area_label_for_worker_not_allowed_on_project_falls_back_to_default(
    registry, issue_payload
) -> None:
    labels = [
        {"id": 1, "title": "agent-ready"},
        {"id": 2, "title": "area:ci"},
    ]  # devops not allowed on frontend-app
    issue_payload["labels"] = labels
    issue_payload["object_attributes"]["labels"] = labels
    result = normalize(
        event="Issue Hook",
        event_uuid="e",
        payload=issue_payload,
        project=_project(registry, "frontend-app"),
        registry=registry,
    )
    assert result.task is not None and result.task.assigned_to == "dev-frontend"


def test_issue_without_opt_in_label_is_recorded_not_queued(registry, issue_payload) -> None:
    labels = [{"id": 3, "title": "bug"}]
    issue_payload["labels"] = labels
    issue_payload["object_attributes"]["labels"] = labels
    result = normalize(
        event="Issue Hook",
        event_uuid="e",
        payload=issue_payload,
        project=_project(registry, "frontend-app"),
        registry=registry,
    )
    assert result.status == "recorded"
    assert result.reason == "opt_in_label_missing"
    assert result.task is not None
    assert result.task.state is TaskState.RECEIVED
    assert result.task.assigned_to is None


def test_issue_update_only_triggers_when_label_is_added(registry, issue_payload) -> None:
    issue_payload["object_attributes"]["action"] = "update"
    project = _project(registry, "frontend-app")

    # title edit on an already-labelled issue → ignore (would otherwise duplicate work)
    issue_payload["changes"] = {"title": {"previous": "a", "current": "b"}}
    r = normalize(
        event="Issue Hook",
        event_uuid="e1",
        payload=issue_payload,
        project=project,
        registry=registry,
    )
    assert r.status == "ignored" and r.reason == "issue_update_not_opt_in"

    # label `agent-ready` just added → queue
    issue_payload["changes"] = {
        "labels": {
            "previous": [{"title": "bug"}],
            "current": [{"title": "bug"}, {"title": "agent-ready"}],
        }
    }
    r = normalize(
        event="Issue Hook",
        event_uuid="e2",
        payload=issue_payload,
        project=project,
        registry=registry,
    )
    assert r.status == "queued"


def test_closed_issue_is_ignored(registry, issue_payload) -> None:
    issue_payload["object_attributes"]["action"] = "close"
    issue_payload["object_attributes"]["state"] = "closed"
    r = normalize(
        event="Issue Hook",
        event_uuid="e",
        payload=issue_payload,
        project=_project(registry, "frontend-app"),
        registry=registry,
    )
    assert r.status == "ignored" and r.reason == "issue_closed"


def test_failed_pipeline_routes_to_devops(registry, pipeline_payload) -> None:
    r = normalize(
        event="Pipeline Hook",
        event_uuid="e",
        payload=pipeline_payload,
        project=_project(registry, "backend-api"),
        registry=registry,
        now=NOW,
    )
    task = r.task
    assert r.status == "queued" and task is not None
    assert task.type == "pipeline_failed"
    assert task.assigned_to == "devops"
    assert task.skill == "incident-triage"
    assert task.source.pipeline_id == 512
    assert task.inputs["failed_jobs"] == [{"id": 9002, "name": "docker-build", "stage": "build"}]
    assert task.inputs["branch"] == "hotfix/ci-512"
    assert task.constraints.self_heal_limit == 2


def test_successful_pipeline_is_ignored(registry, pipeline_payload) -> None:
    pipeline_payload["object_attributes"]["status"] = "success"
    r = normalize(
        event="Pipeline Hook",
        event_uuid="e",
        payload=pipeline_payload,
        project=_project(registry, "backend-api"),
        registry=registry,
    )
    assert r.status == "ignored" and r.reason == "pipeline_status_success"


def test_failed_job_routes_to_devops(registry, job_payload) -> None:
    r = normalize(
        event="Job Hook",
        event_uuid="e",
        payload=job_payload,
        project=_project(registry, "backend-api"),
        registry=registry,
    )
    task = r.task
    assert r.status == "queued" and task is not None
    assert task.type == "job_failed"
    assert task.assigned_to == "devops"
    assert task.source.job_id == 9002
    assert task.source.gitlab_project_id == 12346
    assert task.inputs["job_name"] == "docker-build"
    assert task.inputs["failure_reason"] == "script_failure"


def test_allow_failure_job_is_ignored(registry, job_payload) -> None:
    job_payload["build_allow_failure"] = True
    r = normalize(
        event="Job Hook",
        event_uuid="e",
        payload=job_payload,
        project=_project(registry, "backend-api"),
        registry=registry,
    )
    assert r.status == "ignored" and r.reason == "job_allow_failure"


def test_envelope_round_trips_through_json(registry, issue_payload) -> None:
    r = normalize(
        event="Issue Hook",
        event_uuid="e",
        payload=issue_payload,
        project=_project(registry, "frontend-app"),
        registry=registry,
    )
    assert r.task is not None
    dumped = r.task.model_dump_json()
    restored = Task.model_validate_json(dumped)
    assert restored == r.task
    # keys promised by the design-doc contract (§4.3)
    assert set(json.loads(dumped)) >= {
        "task_id",
        "trace_id",
        "type",
        "project",
        "source",
        "requester",
        "assigned_to",
        "skill",
        "inputs",
        "constraints",
        "handoffs",
        "state",
        "created_at",
    }


# ------------------------------------------------------------ end-to-end
async def test_http_issue_hook_publishes_envelope_to_stream(
    client, issue_payload, fake_redis, store
) -> None:
    r = await client.post("/webhook/gitlab", json=issue_payload, headers=gitlab_headers())
    body = r.json()
    assert body["status"] == "queued"
    assert body["assigned_to"] == "dev-frontend"

    entries = await fake_redis.xrange("stream:tasks")
    assert len(entries) == 1
    _, fields = entries[0]
    assert fields[b"task_id"].decode() == body["task_id"]
    assert fields[b"type"] == b"issue"
    assert fields[b"project"] == b"frontend-app"
    envelope = Task.model_validate_json(fields[b"envelope"])
    assert envelope.task_id == body["task_id"]
    assert envelope.trace_id == body["trace_id"]
    assert envelope.state is TaskState.QUEUED

    assert body["task_id"] in store.tasks
    assert [e["event"] for e in store.audit_events] == ["task.received", "task.queued"]
    assert all(e["trace_id"] == body["trace_id"] for e in store.audit_events)


async def test_http_issue_without_label_is_recorded_only(
    client, issue_payload, fake_redis, store
) -> None:
    labels = [{"id": 3, "title": "bug"}]
    issue_payload["labels"] = labels
    issue_payload["object_attributes"]["labels"] = labels
    r = await client.post("/webhook/gitlab", json=issue_payload, headers=gitlab_headers())
    assert r.status_code == 200
    assert r.json()["status"] == "recorded"
    assert await fake_redis.xlen("stream:tasks") == 0
    assert store.tasks[r.json()["task_id"]].state is TaskState.RECEIVED


async def test_http_pipeline_and_job_hooks(
    client, pipeline_payload, job_payload, fake_redis
) -> None:
    r1 = await client.post(
        "/webhook/gitlab",
        json=pipeline_payload,
        headers=gitlab_headers("Pipeline Hook", event_uuid="p-1"),
    )
    r2 = await client.post(
        "/webhook/gitlab", json=job_payload, headers=gitlab_headers("Job Hook", event_uuid="j-1")
    )
    assert r1.json()["type"] == "pipeline_failed" and r1.json()["assigned_to"] == "devops"
    assert r2.json()["type"] == "job_failed" and r2.json()["assigned_to"] == "devops"
    assert await fake_redis.xlen("stream:tasks") == 2
    metrics = (await client.get("/metrics")).text
    assert 'tasks_enqueued_total{type="pipeline_failed",worker="devops"} 1.0' in metrics
