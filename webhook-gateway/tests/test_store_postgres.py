"""Integration tests for the PostgreSQL task store and migrations.

Run with::

    TEST_DATABASE_URL=postgresql://emaw:emaw@localhost:5432/emaw_test pytest -m integration

The database must be empty; the test applies ``db/migrations/*.sql`` itself.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.envelope import normalize
from app.store import PostgresTaskStore

from .conftest import load_fixture

pytestmark = pytest.mark.integration

DSN = os.environ.get("TEST_DATABASE_URL")
MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


@pytest.fixture
async def pg_store():
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    asyncpg = pytest.importorskip("asyncpg")
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute(
            "DROP TABLE IF EXISTS audit_events, approvals, handoffs, tasks, "
            "schema_migrations CASCADE"
        )
        for sql_file in sorted(MIGRATIONS.glob("*.sql")):
            await conn.execute(sql_file.read_text(encoding="utf-8"))
    finally:
        await conn.close()

    store = PostgresTaskStore(DSN)
    await store.connect()
    try:
        yield store
    finally:
        await store.close()


def _issue_task(registry, iid: int = 89):
    payload = load_fixture("issue_hook.json")
    payload["object_attributes"]["iid"] = iid
    project = next(p for p in registry.projects if p.key == "frontend-app")
    result = normalize(
        event="Issue Hook",
        event_uuid=f"evt-{iid}",
        payload=payload,
        project=project,
        registry=registry,
        now=datetime.now(UTC),
    )
    assert result.task is not None
    return result.task


async def test_migrations_apply_and_record_versions(pg_store) -> None:
    import asyncpg

    conn = await asyncpg.connect(DSN)
    try:
        versions = [
            r["version"]
            for r in await conn.fetch("SELECT version FROM schema_migrations ORDER BY 1")
        ]
        assert versions == ["0001_task_store", "0002_roles"]
        roles = {
            r["rolname"]
            for r in await conn.fetch("SELECT rolname FROM pg_roles WHERE rolname LIKE 'emaw_%'")
        }
        assert {"emaw_gateway_rw", "emaw_coordinator", "emaw_worker_rw", "emaw_readonly"} <= roles
    finally:
        await conn.close()


async def test_create_task_and_one_active_task_per_issue(pg_store, registry) -> None:
    import asyncpg

    t1 = _issue_task(registry, iid=89)
    r1 = await pg_store.create_task(t1)
    assert r1.created and r1.task_id == t1.task_id

    t2 = _issue_task(registry, iid=89)  # same issue, new event → attach to existing
    r2 = await pg_store.create_task(t2)
    assert not r2.created and r2.task_id == t1.task_id

    t3 = _issue_task(registry, iid=90)
    assert (await pg_store.create_task(t3)).created

    # Once the first task is terminal, a new task for the same issue is allowed again.
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("UPDATE tasks SET state='DONE' WHERE task_id=$1", t1.task_id)
        row = await conn.fetchrow(
            "SELECT updated_at > created_at AS bumped FROM tasks WHERE task_id=$1", t1.task_id
        )
        assert row["bumped"] is True
    finally:
        await conn.close()
    t4 = _issue_task(registry, iid=89)
    assert (await pg_store.create_task(t4)).created


async def test_audit_events_are_append_only(pg_store, registry) -> None:
    import asyncpg

    task = _issue_task(registry, iid=91)
    await pg_store.create_task(task)
    await pg_store.audit(
        actor="webhook-gateway",
        event="task.received",
        trace_id=task.trace_id,
        task_id=task.task_id,
        attrs={"event_uuid": "evt-91"},
    )
    conn = await asyncpg.connect(DSN)
    try:
        rows = await conn.fetch("SELECT * FROM audit_events WHERE task_id=$1", task.task_id)
        assert len(rows) == 1 and rows[0]["event"] == "task.received"
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await conn.execute(
                "UPDATE audit_events SET event='tampered' WHERE task_id=$1", task.task_id
            )
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await conn.execute("DELETE FROM audit_events WHERE task_id=$1", task.task_id)
    finally:
        await conn.close()
    assert await pg_store.ping() is True
