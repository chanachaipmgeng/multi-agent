"""Token verification and transport guards (design §5.3, checklist E2)."""

from __future__ import annotations

import json

import pytest

from app.security import verify_gitlab_token
from app.settings import Settings

from .conftest import WEBHOOK_SECRET, gitlab_headers


def test_verify_token_constant_time_semantics() -> None:
    assert verify_gitlab_token("abc", "abc") is True
    assert verify_gitlab_token("abd", "abc") is False
    assert verify_gitlab_token("abc-longer", "abc") is False
    assert verify_gitlab_token(None, "abc") is False
    assert verify_gitlab_token("", "abc") is False
    assert verify_gitlab_token("", "") is False, (
        "an empty configured secret must never authenticate"
    )


def test_settings_refuse_to_start_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GITLAB_WEBHOOK_SECRET_FILE", raising=False)
    with pytest.raises(ValueError, match="GITLAB_WEBHOOK_SECRET"):
        Settings()


def test_settings_read_secret_from_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_WEBHOOK_SECRET", raising=False)
    secret_file = tmp_path / "gitlab_webhook_secret"
    secret_file.write_text("from-docker-secret\n")
    s = Settings(GITLAB_WEBHOOK_SECRET_FILE=str(secret_file))
    assert s.gitlab_webhook_secret == "from-docker-secret"


async def test_missing_token_is_401(client, issue_payload, fake_redis) -> None:
    r = await client.post("/webhook/gitlab", json=issue_payload, headers=gitlab_headers(token=None))
    assert r.status_code == 401
    assert r.json() == {"status": "rejected", "reason": "invalid_token"}
    assert await fake_redis.xlen("stream:tasks") == 0, "nothing may be enqueued on auth failure"


async def test_wrong_token_is_401_and_counted(client, issue_payload) -> None:
    r = await client.post(
        "/webhook/gitlab",
        json=issue_payload,
        headers=gitlab_headers(token="wrong-" + WEBHOOK_SECRET),
    )
    assert r.status_code == 401
    metrics = (await client.get("/metrics")).text
    assert "webhook_auth_fail_total" in metrics
    assert 'status="auth_fail"' in metrics


async def test_wrong_token_does_not_consume_idempotency_key(
    client, issue_payload, fake_redis
) -> None:
    uuid = "aaaaaaaa-0000-0000-0000-000000000001"
    r1 = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(token="bad", event_uuid=uuid)
    )
    assert r1.status_code == 401
    r2 = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid=uuid)
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "queued", (
        "an unauthenticated attempt must not poison the real event"
    )


async def test_valid_token_is_accepted(client, issue_payload) -> None:
    r = await client.post("/webhook/gitlab", json=issue_payload, headers=gitlab_headers())
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


async def test_non_json_content_type_is_415(client, issue_payload) -> None:
    r = await client.post(
        "/webhook/gitlab",
        content=json.dumps(issue_payload),
        headers=gitlab_headers(content_type="text/plain"),
    )
    assert r.status_code == 415


async def test_oversized_payload_is_413(client, issue_payload, settings) -> None:
    issue_payload["object_attributes"]["description"] = "x" * (settings.max_body_bytes + 10)
    r = await client.post("/webhook/gitlab", json=issue_payload, headers=gitlab_headers())
    assert r.status_code == 413


async def test_invalid_json_is_400(client) -> None:
    r = await client.post("/webhook/gitlab", content=b"{not json", headers=gitlab_headers())
    assert r.status_code == 400


async def test_unknown_event_is_ignored_not_rejected(client, issue_payload) -> None:
    r = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event="Merge Request Hook")
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"
    assert r.json()["reason"] == "event_not_allowed"


async def test_unknown_project_is_403(client, issue_payload, fake_redis) -> None:
    issue_payload["project"]["id"] = 424242
    issue_payload["project"]["path_with_namespace"] = "evil/not-ours"
    r = await client.post("/webhook/gitlab", json=issue_payload, headers=gitlab_headers())
    assert r.status_code == 403
    assert r.json()["reason"] == "project_not_allowed"
    assert await fake_redis.xlen("stream:tasks") == 0


async def test_probes(client) -> None:
    assert (await client.get("/healthz")).status_code == 200
    ready = await client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"redis": True, "task_store": True}
