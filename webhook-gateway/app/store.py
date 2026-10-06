"""Task store adapters (PostgreSQL in production, in-memory for tests, no-op when unset).

The gateway only *creates* tasks and writes audit events; state transitions are
owned by the coordinator (Phase 3). Schema lives in ``db/migrations``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from .envelope import TERMINAL_STATES, Task, TaskState


@dataclass(slots=True)
class CreateResult:
    created: bool
    task_id: str  # the new task id, or the existing active task for the same issue


class TaskStore(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def ping(self) -> bool: ...
    async def create_task(self, task: Task) -> CreateResult: ...
    async def audit(
        self,
        *,
        actor: str,
        event: str,
        trace_id: str | None,
        task_id: str | None,
        attrs: dict[str, Any] | None = None,
    ) -> None: ...


# --------------------------------------------------------------------- no-op
class NullTaskStore:
    """Used when ``DATABASE_URL`` is not configured (pure queue mode)."""

    enabled = False

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> bool:
        return True

    async def create_task(self, task: Task) -> CreateResult:
        return CreateResult(created=True, task_id=task.task_id)

    async def audit(self, **_: Any) -> None:
        return None


# ------------------------------------------------------------------- memory
@dataclass
class MemoryTaskStore:
    """In-memory implementation with the same uniqueness semantics as PostgreSQL."""

    enabled: bool = True
    tasks: dict[str, Task] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> bool:
        return True

    def _active_for_issue(self, project: str, issue_iid: int | None) -> Task | None:
        if issue_iid is None:
            return None
        for t in self.tasks.values():
            if (
                t.project == project
                and t.source.issue_iid == issue_iid
                and t.state not in TERMINAL_STATES
            ):
                return t
        return None

    async def create_task(self, task: Task) -> CreateResult:
        existing = self._active_for_issue(task.project, task.source.issue_iid)
        if existing is not None:
            return CreateResult(created=False, task_id=existing.task_id)
        self.tasks[task.task_id] = task
        return CreateResult(created=True, task_id=task.task_id)

    async def audit(
        self,
        *,
        actor: str,
        event: str,
        trace_id: str | None,
        task_id: str | None,
        attrs: dict[str, Any] | None = None,
    ) -> None:
        self.audit_events.append(
            {
                "ts": datetime.now(UTC),
                "actor": actor,
                "event": event,
                "trace_id": trace_id,
                "task_id": task_id,
                "attrs": attrs or {},
            }
        )


# ----------------------------------------------------------------- postgres
class PostgresTaskStore:
    enabled = True

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None

    async def connect(self) -> None:
        import asyncpg  # imported lazily so unit tests do not need the driver

        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> bool:
        if self._pool is None:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 — readiness probe must never raise
            return False

    async def create_task(self, task: Task) -> CreateResult:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn, conn.transaction():
            if task.source.issue_iid is not None:
                row = await conn.fetchrow(
                    """
                    SELECT task_id FROM tasks
                    WHERE project_key = $1 AND issue_iid = $2
                      AND state NOT IN ('DONE','FAILED','CANCELLED','EXPIRED','REJECTED')
                    FOR UPDATE
                    """,
                    task.project,
                    task.source.issue_iid,
                )
                if row is not None:
                    return CreateResult(created=False, task_id=row["task_id"])
            await conn.execute(
                """
                INSERT INTO tasks (
                  task_id, trace_id, type, project_key, issue_iid, state, assigned_to,
                  requester_user_id, skill, source, inputs, constraints, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12::jsonb,$13,$13)
                """,
                task.task_id,
                task.trace_id,
                task.type,
                task.project,
                task.source.issue_iid,
                task.state.value,
                task.assigned_to,
                task.requester.user_id,
                task.skill,
                task.source.model_dump_json(),
                json.dumps(task.inputs, default=str),
                task.constraints.model_dump_json(),
                task.created_at,
            )
        return CreateResult(created=True, task_id=task.task_id)

    async def audit(
        self,
        *,
        actor: str,
        event: str,
        trace_id: str | None,
        task_id: str | None,
        attrs: dict[str, Any] | None = None,
    ) -> None:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_events (trace_id, task_id, actor, event, attrs)
                VALUES ($1,$2,$3,$4,$5::jsonb)
                """,
                trace_id,
                task_id,
                actor,
                event,
                json.dumps(attrs or {}, default=str),
            )


def build_store(database_url: str | None) -> TaskStore:
    if not database_url:
        return NullTaskStore()
    return PostgresTaskStore(database_url)


__all__ = [
    "CreateResult",
    "MemoryTaskStore",
    "NullTaskStore",
    "PostgresTaskStore",
    "TaskState",
    "TaskStore",
    "build_store",
]
