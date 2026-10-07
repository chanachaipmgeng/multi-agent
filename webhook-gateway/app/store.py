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
    async def get_task(self, task_id: str) -> dict[str, Any] | None: ...
    async def list_tasks(
        self, *, project: str | None = None, state: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]: ...
    async def set_state(self, task_id: str, state: str) -> None: ...
    async def create_approval(
        self,
        *,
        task_id: str,
        action: str,
        payload_hash: str,
        nonce: str,
        requested_by: str,
        required_role: str,
        timeout_at: datetime,
    ) -> None: ...
    async def get_approval(self, nonce: str) -> dict[str, Any] | None: ...
    async def decide_approval(
        self, nonce: str, *, decision: str, decided_by: int
    ) -> None: ...
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

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        return None

    async def list_tasks(self, *, project=None, state=None, limit=50) -> list[dict[str, Any]]:
        return []

    async def set_state(self, task_id: str, state: str) -> None:
        return None

    async def create_approval(self, **_: Any) -> None:
        return None

    async def get_approval(self, nonce: str) -> dict[str, Any] | None:
        return None

    async def decide_approval(self, nonce: str, *, decision: str, decided_by: int) -> None:
        return None

    async def audit(self, **_: Any) -> None:
        return None


# ------------------------------------------------------------------- memory
@dataclass
class MemoryTaskStore:
    """In-memory implementation with the same uniqueness semantics as PostgreSQL."""

    enabled: bool = True
    tasks: dict[str, Task] = field(default_factory=dict)
    approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
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

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        t = self.tasks.get(task_id)
        if t is None:
            return None
        return {
            "task_id": t.task_id,
            "trace_id": t.trace_id,
            "type": t.type,
            "project_key": t.project,
            "project": t.project,
            "state": t.state.value if isinstance(t.state, TaskState) else t.state,
            "assigned_to": t.assigned_to,
            "skill": t.skill,
        }

    async def list_tasks(self, *, project=None, state=None, limit=50) -> list[dict[str, Any]]:
        rows = []
        for t in self.tasks.values():
            if project and t.project != project:
                continue
            st = t.state.value if isinstance(t.state, TaskState) else t.state
            if state and st != state:
                continue
            rows.append(await self.get_task(t.task_id))
            if len(rows) >= limit:
                break
        return [r for r in rows if r]

    async def set_state(self, task_id: str, state: str) -> None:
        t = self.tasks.get(task_id)
        if t is not None:
            t.state = TaskState(state)

    async def create_approval(
        self,
        *,
        task_id: str,
        action: str,
        payload_hash: str,
        nonce: str,
        requested_by: str,
        required_role: str,
        timeout_at: datetime,
    ) -> None:
        self.approvals[nonce] = {
            "task_id": task_id,
            "action": action,
            "payload_hash": payload_hash,
            "nonce": nonce,
            "requested_by": requested_by,
            "required_role": required_role,
            "timeout_at": timeout_at,
            "decision": None,
            "decided_by": None,
        }

    async def get_approval(self, nonce: str) -> dict[str, Any] | None:
        return self.approvals.get(nonce)

    async def decide_approval(self, nonce: str, *, decision: str, decided_by: int) -> None:
        row = self.approvals.get(nonce)
        if row is not None:
            row["decision"] = decision
            row["decided_by"] = decided_by
            row["decided_at"] = datetime.now(UTC)

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

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT task_id, trace_id, type, project_key, state, assigned_to, skill, "
                "result, created_at, updated_at FROM tasks WHERE task_id = $1",
                task_id,
            )
        if row is None:
            return None
        data = dict(row)
        data["project"] = data.get("project_key")
        for k in ("created_at", "updated_at"):
            if data.get(k) is not None:
                data[k] = data[k].isoformat()
        return data

    async def list_tasks(self, *, project=None, state=None, limit=50) -> list[dict[str, Any]]:
        assert self._pool is not None, "store not connected"
        clauses: list[str] = []
        args: list[Any] = []
        if project:
            args.append(project)
            clauses.append(f"project_key = ${len(args)}")
        if state:
            args.append(state)
            clauses.append(f"state = ${len(args)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(limit)
        sql = (
            f"SELECT task_id, trace_id, type, project_key, state, assigned_to, skill, "
            f"created_at FROM tasks {where} ORDER BY created_at DESC LIMIT ${len(args)}"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        out = []
        for row in rows:
            data = dict(row)
            data["project"] = data.get("project_key")
            if data.get("created_at") is not None:
                data["created_at"] = data["created_at"].isoformat()
            out.append(data)
        return out

    async def set_state(self, task_id: str, state: str) -> None:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET state = $2 WHERE task_id = $1", task_id, state
            )

    async def create_approval(
        self,
        *,
        task_id: str,
        action: str,
        payload_hash: str,
        nonce: str,
        requested_by: str,
        required_role: str,
        timeout_at: datetime,
    ) -> None:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO approvals
                  (task_id, action, payload_hash, nonce, requested_by, required_role, timeout_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                """,
                task_id,
                action,
                payload_hash,
                nonce,
                requested_by,
                required_role,
                timeout_at,
            )

    async def get_approval(self, nonce: str) -> dict[str, Any] | None:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT task_id, action, payload_hash, nonce, requested_by, required_role, "
                "timeout_at, decision, decided_by, decided_at FROM approvals WHERE nonce = $1",
                nonce,
            )
        if row is None:
            return None
        data = dict(row)
        for k in ("timeout_at", "decided_at"):
            if data.get(k) is not None:
                data[k] = data[k]
        return data

    async def decide_approval(self, nonce: str, *, decision: str, decided_by: int) -> None:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE approvals
                   SET decision = $2, decided_by = $3, decided_at = now()
                 WHERE nonce = $1
                """,
                nonce,
                decision,
                decided_by,
            )

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
