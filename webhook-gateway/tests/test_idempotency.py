"""Replay / duplicate protection (design §5.3 — X-Gitlab-Event-UUID, TTL 24h)."""

from __future__ import annotations

from app.idempotency import IdempotencyStore

from .conftest import gitlab_headers


async def test_claim_is_first_wins(fake_redis) -> None:
    store = IdempotencyStore(fake_redis, prefix="t:", ttl_seconds=60)
    assert await store.claim("evt-1") is True
    assert await store.claim("evt-1") is False
    assert await store.claim("evt-2") is True
    ttl = await fake_redis.ttl("t:evt-1")
    assert 0 < ttl <= 60


async def test_release_allows_reclaim(fake_redis) -> None:
    store = IdempotencyStore(fake_redis, prefix="t:", ttl_seconds=60)
    assert await store.claim("evt-1") is True
    await store.release("evt-1")
    assert await store.claim("evt-1") is True


async def test_duplicate_event_uuid_is_acked_but_not_enqueued(
    client, issue_payload, fake_redis
) -> None:
    uuid = "dedupe-0000-0000-0000-000000000001"
    first = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid=uuid)
    )
    second = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid=uuid)
    )

    assert first.status_code == 200 and first.json()["status"] == "queued"
    assert second.status_code == 200, "GitLab must get a 2xx so it does not retry a duplicate"
    assert second.json() == {"status": "duplicate", "event_uuid": uuid}
    assert await fake_redis.xlen("stream:tasks") == 1


async def test_distinct_event_uuids_for_different_issues_both_enqueue(
    client, issue_payload, fake_redis
) -> None:
    r1 = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid="u-1")
    )
    issue_payload["object_attributes"]["iid"] = 90
    r2 = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid="u-2")
    )
    assert r1.json()["status"] == "queued"
    assert r2.json()["status"] == "queued"
    assert await fake_redis.xlen("stream:tasks") == 2


async def test_missing_uuid_falls_back_to_body_hash(client, issue_payload, fake_redis) -> None:
    r1 = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid=None)
    )
    r2 = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid=None)
    )
    assert r1.json()["status"] == "queued"
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["event_uuid"].startswith("sha256:")
    assert await fake_redis.xlen("stream:tasks") == 1


async def test_second_event_for_same_active_issue_attaches_instead_of_new_task(
    client, issue_payload, fake_redis, store
) -> None:
    """1 Issue = 1 active task (design §4.5) even when GitLab sends a *different* event UUID."""
    r1 = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid="u-1")
    )
    issue_payload["object_attributes"]["action"] = "reopen"
    r2 = await client.post(
        "/webhook/gitlab", json=issue_payload, headers=gitlab_headers(event_uuid="u-2")
    )

    assert r1.json()["status"] == "queued"
    assert r2.status_code == 200
    assert r2.json()["status"] == "attached"
    assert r2.json()["task_id"] == r1.json()["task_id"]
    assert await fake_redis.xlen("stream:tasks") == 1
    assert [e["event"] for e in store.audit_events] == [
        "task.received",
        "task.queued",
        "task.duplicate_issue",
    ]
