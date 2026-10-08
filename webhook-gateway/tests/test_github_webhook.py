"""GitHub webhook path: HMAC auth, allowlist, opt-in, idempotency."""

from __future__ import annotations

import json

import pytest

from app.security import verify_github_signature
from app.settings import Settings

from .conftest import GITHUB_WEBHOOK_SECRET, WEBHOOK_SECRET, github_headers, github_sign


def test_verify_github_signature() -> None:
    body = b'{"ok":true}'
    sig = github_sign(body)
    assert verify_github_signature(sig, body, GITHUB_WEBHOOK_SECRET) is True
    assert verify_github_signature(sig, b'{"ok":false}', GITHUB_WEBHOOK_SECRET) is False
    assert verify_github_signature("sha256=deadbeef", body, GITHUB_WEBHOOK_SECRET) is False
    assert verify_github_signature(None, body, GITHUB_WEBHOOK_SECRET) is False
    assert verify_github_signature(sig, body, "") is False
    assert verify_github_signature("md5=abc", body, GITHUB_WEBHOOK_SECRET) is False


def test_settings_boot_without_github_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET_FILE", raising=False)
    s = Settings(GITLAB_WEBHOOK_SECRET=WEBHOOK_SECRET)
    assert s.github_webhook_secret is None


async def test_github_secret_unset_is_503(fake_redis, store, registry) -> None:
    from pathlib import Path

    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    projects_file = Path(__file__).resolve().parents[2] / "config" / "projects.yaml"
    settings = Settings(
        GITLAB_WEBHOOK_SECRET=WEBHOOK_SECRET,
        PROJECTS_FILE=str(projects_file),
        REDIS_URL="redis://unused:6379/0",
    )
    assert settings.github_webhook_secret is None
    app = create_app(settings, redis=fake_redis, store=store, registry_override=registry)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway.test") as c:
            r = await c.post(
                "/webhook/github",
                content=b"{}",
                headers={"Content-Type": "application/json", "X-GitHub-Event": "issues"},
            )
            assert r.status_code == 503
            assert r.json()["reason"] == "github_webhook_secret_unset"


async def test_github_wrong_hmac_is_401(client, github_issues_payload) -> None:
    body = json.dumps(github_issues_payload).encode()
    r = await client.post(
        "/webhook/github",
        content=body,
        headers=github_headers(body=body, signature="sha256=" + "0" * 64),
    )
    assert r.status_code == 401
    assert r.json()["reason"] == "invalid_signature"


async def test_github_unknown_project_is_403(client, github_issues_payload) -> None:
    github_issues_payload["repository"]["id"] = 424242
    github_issues_payload["repository"]["full_name"] = "evil/not-ours"
    body = json.dumps(github_issues_payload).encode()
    r = await client.post(
        "/webhook/github",
        content=body,
        headers=github_headers(body=body),
    )
    assert r.status_code == 403
    assert r.json()["reason"] == "project_not_allowed"


async def test_github_issue_with_opt_in_is_queued(client, github_issues_payload, fake_redis) -> None:
    body = json.dumps(github_issues_payload).encode()
    r = await client.post(
        "/webhook/github",
        content=body,
        headers=github_headers(body=body),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "queued"
    assert data["type"] == "issue"
    assert data["assigned_to"] == "dev-frontend"
    assert await fake_redis.xlen("stream:tasks") == 1


async def test_github_issue_without_opt_in_is_recorded(client, github_issues_payload, fake_redis) -> None:
    github_issues_payload["issue"]["labels"] = [{"id": 2, "name": "area:frontend"}]
    body = json.dumps(github_issues_payload).encode()
    r = await client.post(
        "/webhook/github",
        content=body,
        headers=github_headers(body=body, delivery="no-opt-in-delivery"),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "recorded"
    assert data["reason"] == "opt_in_label_missing"
    assert await fake_redis.xlen("stream:tasks") == 0


async def test_github_duplicate_delivery_is_duplicate(client, github_issues_payload) -> None:
    body = json.dumps(github_issues_payload).encode()
    delivery = "dup-delivery-0001"
    headers = github_headers(body=body, delivery=delivery)
    r1 = await client.post("/webhook/github", content=body, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["status"] == "queued"
    r2 = await client.post("/webhook/github", content=body, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"


async def test_github_workflow_run_failure_queued(client, github_workflow_run_payload) -> None:
    body = json.dumps(github_workflow_run_payload).encode()
    r = await client.post(
        "/webhook/github",
        content=body,
        headers=github_headers(event="workflow_run", body=body, delivery="run-fail-1"),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "queued"
    assert data["type"] == "pipeline_failed"
    assert data["assigned_to"] == "devops"


async def test_github_workflow_job_failure_queued(client, github_workflow_job_payload) -> None:
    body = json.dumps(github_workflow_job_payload).encode()
    r = await client.post(
        "/webhook/github",
        content=body,
        headers=github_headers(event="workflow_job", body=body, delivery="job-fail-1"),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "queued"
    assert data["type"] == "job_failed"
    assert data["assigned_to"] == "devops"


async def test_github_unknown_event_ignored(client, github_issues_payload) -> None:
    body = json.dumps(github_issues_payload).encode()
    r = await client.post(
        "/webhook/github",
        content=body,
        headers=github_headers(event="push", body=body, delivery="push-1"),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"
    assert r.json()["reason"] == "event_not_allowed"
