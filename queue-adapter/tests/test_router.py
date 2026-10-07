"""Router mode: fan-out + results state machine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.breaker import CircuitBreaker
from app.control import ControlPlane
from app.notify import TelegramNotifier
from app.projects import ProjectRegistry
from app.router import Router
from app.settings import Settings
from app.store import MemoryStateStore
from tests.conftest import make_task


@pytest.fixture
def projects_file(tmp_path: Path) -> Path:
    data = {
        "projects": [
            {
                "key": "frontend-app",
                "gitlab_project_id": 12345,
                "path_with_namespace": "acme/frontend-app",
                "workspace_path": "/workspace/frontend-app",
                "default_worker": "dev-frontend",
                "allowed_workers": ["dev-frontend", "reviewer", "qa"],
            },
            {
                "key": "backend-api",
                "gitlab_project_id": 12346,
                "path_with_namespace": "acme/backend-api",
                "workspace_path": "/workspace/backend-api",
                "default_worker": "dev-backend",
                "allowed_workers": ["dev-backend", "reviewer", "qa", "devops"],
            },
        ],
        "routing": {
            "label_prefix": "area:",
            "label_to_worker": {
                "frontend": "dev-frontend",
                "backend": "dev-backend",
                "ci": "devops",
                "qa": "qa",
            },
            "pipeline_failed_worker": "devops",
        },
    }
    path = tmp_path / "projects.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


@pytest.fixture
def router_settings(tmp_path: Path, projects_file: Path) -> Settings:
    return Settings(
        MODE="router",
        REDIS_URL="redis://unused:6379/0",
        CONSUMER_NAME="test-router",
        CONSUMER_GROUP="router",
        TASK_STREAM="stream:tasks",
        RESULTS_STREAM="stream:results",
        PROJECTS_FILE=str(projects_file),
        HEARTBEAT_FILE=str(tmp_path / "heartbeat"),
        CLAIM_MIN_IDLE_MS=0,
        METRICS_PORT=0,
    )


@pytest.fixture
async def router(router_settings, fake_redis, store) -> Router:
    control = ControlPlane(fake_redis)
    breaker = CircuitBreaker(fake_redis, control, fail_threshold=3, fail_window_seconds=900)
    registry = ProjectRegistry.from_yaml(router_settings.projects_file)
    r = Router(
        router_settings,
        redis=fake_redis,
        store=store,
        control=control,
        breaker=breaker,
        notifier=TelegramNotifier(None, None),
        registry=registry,
    )
    await r.ensure_groups()
    return r


async def test_route_task_to_role_stream(router, router_settings, fake_redis, store) -> None:
    task = make_task()
    mid = await fake_redis.xadd(
        "stream:tasks",
        {
            "task_id": task["task_id"],
            "envelope": json.dumps(task),
            "assigned_to": "dev-frontend",
        },
    )
    await router.handle_task(
        mid.decode() if isinstance(mid, bytes) else mid,
        {"envelope": json.dumps(task).encode()},
    )
    entries = await fake_redis.xrange("stream:dev-frontend")
    assert len(entries) == 1
    fields = entries[0][1]
    assert (fields.get(b"assigned_to") or fields.get("assigned_to")) in {
        b"dev-frontend",
        "dev-frontend",
    }
    assert store.states[task["task_id"]]["state"] == "ASSIGNED"
    assert any(e["event"] == "task.routed" for e in store.audit_events)


async def test_pause_defers_routing(router, fake_redis, store) -> None:
    await router.control.pause("dev-frontend")
    task = make_task()
    await router.handle_task("1-0", {"envelope": json.dumps(task).encode()})
    entries = await fake_redis.xrange("stream:dev-frontend")
    assert entries == []
    assert task["task_id"] not in store.states


async def test_pause_then_resume_via_pending_read(router, router_settings, fake_redis, store) -> None:
    """Paused work stays in the PEL; after resume, id=0 pending read fans it out."""
    await router.ensure_groups()
    await router.control.pause("dev-frontend")
    task = make_task(task_id="t-pause-resume-1")
    await fake_redis.xadd(
        "stream:tasks",
        {"task_id": task["task_id"], "envelope": json.dumps(task)},
    )
    # New message while paused → deferred (unacked).
    assert await router.run_once(block_ms=1) >= 0
    assert await fake_redis.xlen("stream:dev-frontend") == 0

    await router.control.resume("dev-frontend")
    # Pending (id=0) drain should route without waiting claim_min_idle.
    await router.run_once(block_ms=1)
    entries = await fake_redis.xrange("stream:dev-frontend")
    assert len(entries) == 1
    assert store.states[task["task_id"]]["state"] == "ASSIGNED"


async def test_result_auto_handoff_to_reviewer(router, fake_redis, store) -> None:
    task = make_task()
    store.states[task["task_id"]] = {
        "task_id": task["task_id"],
        "project_key": "frontend-app",
        "state": "IN_PROGRESS",
        "assigned_to": "dev-frontend",
    }
    fields = {
        b"task_id": task["task_id"].encode(),
        b"trace_id": task["trace_id"].encode(),
        b"status": b"completed",
        b"from_agent": b"dev-frontend",
        b"project": b"frontend-app",
        b"detail": b"tests passed",
        b"envelope": json.dumps(task).encode(),
        b"handoff": b"",
    }
    await router.ensure_groups()
    # seed results group membership by writing then reading would ack; call handle directly
    await router.handle_result("1-0", fields)
    entries = await fake_redis.xrange("stream:reviewer")
    assert len(entries) == 1
    assert store.states[task["task_id"]]["state"] == "REVIEW"
    assert len(store.handoffs) == 1
    assert store.handoffs[0]["to_agent"] == "reviewer"


async def test_result_done_without_handoff_target(router, fake_redis, store) -> None:
    task = make_task(assigned_to="reviewer", skill="review-with-socraticode")
    store.states[task["task_id"]] = {
        "task_id": task["task_id"],
        "project_key": "frontend-app",
        "state": "REVIEW",
        "assigned_to": "reviewer",
    }
    handoff = {"to_agent": "", "reason": "done", "summary": "no blockers"}
    fields = {
        b"task_id": task["task_id"].encode(),
        b"status": b"completed",
        b"from_agent": b"reviewer",
        b"project": b"frontend-app",
        b"detail": b"ok",
        b"envelope": json.dumps(task).encode(),
        b"handoff": json.dumps(handoff).encode(),
    }
    await router.handle_result("2-0", fields)
    assert store.states[task["task_id"]]["state"] == "DONE"
    assert await fake_redis.xlen("stream:reviewer") == 0


async def test_safe_mode_sets_require_approval(router, fake_redis) -> None:
    await router.control.set_safe_mode(True)
    task = make_task()
    await router.handle_task("3-0", {"envelope": json.dumps(task).encode()})
    entries = await fake_redis.xrange("stream:dev-frontend")
    env = json.loads(
        (entries[0][1].get(b"envelope") or entries[0][1]["envelope"]).decode()
        if isinstance(entries[0][1].get(b"envelope") or entries[0][1].get("envelope"), bytes)
        else (entries[0][1].get(b"envelope") or entries[0][1]["envelope"])
    )
    assert env["constraints"]["require_approval"] is True
