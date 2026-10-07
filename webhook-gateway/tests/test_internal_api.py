"""Internal control-plane API tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fakeredis import aioredis as fakeredis_aio
from httpx import ASGITransport, AsyncClient

from app.envelope import Task, TaskConstraints, TaskRequester, TaskSource, TaskState
from app.main import create_app
from app.projects import ProjectRegistry
from app.settings import Settings
from app.store import MemoryTaskStore


@pytest.fixture
def projects_file(tmp_path: Path) -> Path:
    p = tmp_path / "projects.yaml"
    p.write_text(
        """
projects:
  - key: frontend-app
    gitlab_project_id: 1
    path_with_namespace: acme/frontend-app
    workspace_path: /workspace/frontend-app
    default_worker: dev-frontend
    allowed_workers: [dev-frontend, reviewer, qa]
    test_command: "npm test"
routing:
  label_to_worker: { frontend: dev-frontend, backend: dev-backend, ci: devops, qa: qa }
  pipeline_failed_worker: devops
""",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def rbac_file(tmp_path: Path) -> Path:
    p = tmp_path / "rbac.yaml"
    p.write_text(
        """
users:
  987654321: { name: zeeme, roles: [admin, approver, developer], projects: ["*"] }
  111: { name: viewer, roles: [viewer], projects: ["*"] }
commands:
  route-task: { roles: [developer, admin] }
  status-report: { roles: [viewer, developer, admin] }
  pause: { roles: [admin] }
  resume: { roles: [admin] }
  safe-mode: { roles: [admin] }
  approve-push: { roles: [developer, admin] }
  approve-migration: { roles: [approver, admin] }
  deploy-prod: { roles: [approver, admin] }
""",
        encoding="utf-8",
    )
    return p


@pytest.fixture
async def client(projects_file, rbac_file):
    settings = Settings(
        GITLAB_WEBHOOK_SECRET="test-secret",
        HERMES_API_KEY="test-api-key",
        PROJECTS_FILE=str(projects_file),
        RBAC_FILE=str(rbac_file),
        REDIS_URL="redis://unused",
    )
    store = MemoryTaskStore()
    redis = fakeredis_aio.FakeRedis(decode_responses=False)
    app = create_app(
        settings,
        redis=redis,
        store=store,
        registry_override=ProjectRegistry.from_yaml(projects_file),
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, store, redis
    close = getattr(redis, "aclose", None) or getattr(redis, "close", None)
    if close:
        result = close()
        if hasattr(result, "__await__"):
            await result


def _headers(user_id: int = 987654321) -> dict[str, str]:
    return {
        "Authorization": "Bearer test-api-key",
        "X-EMAW-User-Id": str(user_id),
        "Content-Type": "application/json",
    }


async def test_create_task_and_list(client) -> None:
    ac, store, _redis = client
    r = await ac.post(
        "/internal/tasks",
        headers=_headers(),
        json={
            "type": "feature",
            "project": "frontend-app",
            "assigned_to": "dev-frontend",
            "instruction": "add button",
            "labels": ["area:frontend"],
            "idempotency_key": "test-1",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["assigned_to"] == "dev-frontend"
    assert body["task_id"] in store.tasks

    listed = await ac.get("/internal/tasks", headers=_headers(111))
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1


async def test_viewer_cannot_route(client) -> None:
    ac, _store, _redis = client
    r = await ac.post(
        "/internal/tasks",
        headers=_headers(111),
        json={
            "type": "feature",
            "project": "frontend-app",
            "instruction": "x",
            "idempotency_key": "v1",
        },
    )
    assert r.status_code == 403


async def test_pause_and_safe_mode(client) -> None:
    ac, _store, redis = client
    r = await ac.post("/internal/control/pause", headers=_headers(), json={"agent": "all"})
    assert r.status_code == 200
    paused = await redis.get(b"emaw:control:pause:all")
    if paused is None:
        paused = await redis.get("emaw:control:pause:all")
    assert paused

    r = await ac.post("/internal/control/safe-mode", headers=_headers(), json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["safe_mode"] is True

    r = await ac.post("/internal/control/resume", headers=_headers(), json={"agent": "all"})
    assert r.status_code == 200


async def test_approval_flow(client) -> None:
    ac, store, _redis = client
    task = Task(
        task_id="t-test-1",
        trace_id="abc",
        type="feature",
        project="frontend-app",
        source=TaskSource(kind="telegram"),
        requester=TaskRequester(channel="telegram", user_id=1),
        assigned_to="dev-frontend",
        skill="dev-flow",
        constraints=TaskConstraints(token_budget=1, self_heal_limit=0, deadline_min=1),
        state=TaskState.IN_PROGRESS,
        created_at=datetime.now(UTC),
    )
    await store.create_task(task)

    r = await ac.post(
        "/internal/approvals",
        headers=_headers(),
        json={
            "task_id": "t-test-1",
            "action": "push_work_branch_and_open_mr",
            "payload": {"branch": "fix/x"},
            "required_role": "developer",
        },
    )
    assert r.status_code == 200, r.text
    nonce = r.json()["nonce"]
    decide = await ac.post(
        f"/internal/approvals/{nonce}/decide",
        headers=_headers(),
        json={"decision": "approved"},
    )
    assert decide.status_code == 200
    assert decide.json()["status"] == "approved"

    from prometheus_client import generate_latest

    from app.metrics import registry

    scraped = generate_latest(registry).decode()
    assert "approval_latency_seconds_count" in scraped
    assert "approval_latency_seconds_sum" in scraped


async def test_metrics_task_state_gauge(client) -> None:
    ac, store, _redis = client
    task = Task(
        task_id="t-metrics-1",
        trace_id="abc",
        type="feature",
        project="frontend-app",
        source=TaskSource(kind="telegram"),
        requester=TaskRequester(channel="telegram", user_id=1),
        assigned_to="dev-frontend",
        skill="dev-flow",
        constraints=TaskConstraints(token_budget=1, self_heal_limit=0, deadline_min=1),
        state=TaskState.QUEUED,
        created_at=datetime.now(UTC),
    )
    await store.create_task(task)
    r = await ac.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert 'task_state_total{state="QUEUED"}' in body
