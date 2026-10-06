from __future__ import annotations

import copy
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fakeredis import aioredis as fakeredis_aio
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.projects import ProjectRegistry
from app.settings import Settings
from app.store import MemoryTaskStore

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_FILE = REPO_ROOT / "config" / "projects.yaml"

WEBHOOK_SECRET = "test-webhook-secret-not-real"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def issue_payload() -> dict[str, Any]:
    return copy.deepcopy(load_fixture("issue_hook.json"))


@pytest.fixture
def pipeline_payload() -> dict[str, Any]:
    return copy.deepcopy(load_fixture("pipeline_hook.json"))


@pytest.fixture
def job_payload() -> dict[str, Any]:
    return copy.deepcopy(load_fixture("job_hook.json"))


@pytest.fixture
def registry() -> ProjectRegistry:
    return ProjectRegistry.from_yaml(PROJECTS_FILE)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        GITLAB_WEBHOOK_SECRET=WEBHOOK_SECRET,
        PROJECTS_FILE=str(PROJECTS_FILE),
        REDIS_URL="redis://unused:6379/0",
        IDEMPOTENCY_TTL_SECONDS=60,
    )


@pytest.fixture
async def fake_redis() -> AsyncIterator[fakeredis_aio.FakeRedis]:
    client = fakeredis_aio.FakeRedis(decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def store() -> MemoryTaskStore:
    return MemoryTaskStore()


@pytest.fixture
async def client(settings, fake_redis, store, registry) -> AsyncIterator[AsyncClient]:
    app = create_app(settings, redis=fake_redis, store=store, registry_override=registry)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c


def gitlab_headers(
    event: str = "Issue Hook",
    *,
    token: str | None = WEBHOOK_SECRET,
    event_uuid: str | None = "11111111-2222-3333-4444-555555555555",
    content_type: str = "application/json",
) -> dict[str, str]:
    headers = {"Content-Type": content_type, "X-Gitlab-Event": event}
    if token is not None:
        headers["X-Gitlab-Token"] = token
    if event_uuid is not None:
        headers["X-Gitlab-Event-UUID"] = event_uuid
    return headers
