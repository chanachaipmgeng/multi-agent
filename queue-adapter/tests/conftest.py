from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fakeredis import aioredis as fakeredis_aio

from app.consumer import Consumer
from app.dispatch import DispatchResult, DryRunDispatcher
from app.gitlab import GitLabClient
from app.notify import TelegramNotifier
from app.settings import Settings
from app.store import MemoryStateStore


def make_task(**overrides: Any) -> dict[str, Any]:
    task = {
        "task_id": "t-20261007-abc123",
        "trace_id": "0123456789abcdef0123456789abcdef",
        "type": "issue",
        "project": "frontend-app",
        "source": {
            "kind": "gitlab_webhook",
            "event": "Issue Hook",
            "event_uuid": "evt-1",
            "gitlab_project_id": 12345,
            "path_with_namespace": "acme/frontend-app",
            "issue_iid": 89,
        },
        "requester": {
            "channel": "gitlab",
            "user_id": 987654321,
            "username": "qa-lead",
            "role": "gitlab_user",
        },
        "assigned_to": "dev-frontend",
        "skill": "resolve-issue",
        "inputs": {
            "issue_iid": 89,
            "issue_title": "Mobile layout overflows",
            "issue_body": "…",
            "labels": ["agent-ready", "area:frontend"],
            "branch": "fix/issue-89",
            "workspace_path": "/workspace/frontend-app",
            "test_command": "npm run check:all",
        },
        "constraints": {"token_budget": 400000, "self_heal_limit": 3, "deadline_min": 60},
        "handoffs": [],
        "state": "QUEUED",
        "created_at": datetime.now(UTC).isoformat(),
    }
    task.update(overrides)
    return task


def make_job_failed_task() -> dict[str, Any]:
    return make_task(
        task_id="t-20261007-job001",
        type="job_failed",
        project="backend-api",
        assigned_to="devops",
        skill="incident-triage",
        source={
            "kind": "gitlab_webhook",
            "event": "Job Hook",
            "event_uuid": "evt-2",
            "gitlab_project_id": 12346,
            "path_with_namespace": "acme/backend-api",
            "job_id": 9002,
            "pipeline_id": 512,
        },
        inputs={
            "job_id": 9002,
            "job_name": "docker-build",
            "stage": "build",
            "pipeline_id": 512,
            "branch": "hotfix/ci-512",
        },
        constraints={"token_budget": 300000, "self_heal_limit": 2, "deadline_min": 45},
    )


class FailingDispatcher:
    name = "failing"

    def __init__(self, *, retryable: bool = True) -> None:
        self.retryable = retryable
        self.calls = 0

    async def dispatch(self, task, prompt) -> DispatchResult:
        self.calls += 1
        return DispatchResult(ok=False, detail="boom", retryable=self.retryable)

    async def aclose(self) -> None:
        return None


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        REDIS_URL="redis://unused:6379/0",
        CONSUMER_NAME="test-consumer",
        OUTBOX_DIR=str(tmp_path / "outbox"),
        HEARTBEAT_FILE=str(tmp_path / "heartbeat"),
        CLAIM_MIN_IDLE_MS=0,
        MAX_DELIVERIES=3,
    )


@pytest.fixture
async def fake_redis() -> AsyncIterator[fakeredis_aio.FakeRedis]:
    client = fakeredis_aio.FakeRedis(decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def store() -> MemoryStateStore:
    return MemoryStateStore()


@pytest.fixture
def gitlab_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jobs/9002/trace"):
            assert request.headers.get("PRIVATE-TOKEN") == "glpat-test-token-aaaaaaaaaaaaaaaaaaaa"
            body = (
                "Step 4/9 : RUN pip install -r requirements.txt\n"
                "export GITLAB_TOKEN=glpat-SuperSecretValue1234567890\n"
                "ERROR: Could not find a version that satisfies the requirement foo==9.9.9\n"
                "ERROR: Job failed: exit code 1\n"
            )
            return httpx.Response(200, text=body)
        if request.url.path.endswith("/pipelines/512/jobs"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 9002,
                        "name": "docker-build",
                        "stage": "build",
                        "failure_reason": "script_failure",
                    }
                ],
            )
        return httpx.Response(404, json={"message": "404 Not Found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def gitlab(settings, gitlab_transport) -> GitLabClient:
    return GitLabClient(
        "https://gitlab.example.com",
        "glpat-test-token-aaaaaaaaaaaaaaaaaaaa",
        trace_max_bytes=settings.trace_max_bytes,
        transport=gitlab_transport,
    )


@pytest.fixture
def telegram_calls() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def notifier(telegram_calls) -> TelegramNotifier:
    def handler(request: httpx.Request) -> httpx.Response:
        telegram_calls.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    return TelegramNotifier(
        "000000000:test-bot-token", "123456", transport=httpx.MockTransport(handler)
    )


@pytest.fixture
def consumer(settings, fake_redis, store, gitlab, notifier) -> Consumer:
    return Consumer(
        settings,
        redis=fake_redis,
        store=store,
        dispatcher=DryRunDispatcher(settings.outbox_dir),
        gitlab=gitlab,
        notifier=notifier,
    )


async def enqueue(redis, settings: Settings, task: dict[str, Any]) -> str:
    message_id = await redis.xadd(
        settings.task_stream,
        {
            "task_id": task["task_id"],
            "trace_id": task["trace_id"],
            "type": task["type"],
            "project": task["project"],
            "assigned_to": task.get("assigned_to") or "",
            "state": task["state"],
            "envelope": json.dumps(task),
        },
    )
    return message_id.decode() if isinstance(message_id, bytes) else message_id
