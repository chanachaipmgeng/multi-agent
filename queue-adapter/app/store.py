"""Task-state updates and audit events written by the adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


class StateStore(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def set_state(
        self,
        task_id: str,
        state: str,
        *,
        assigned_to: str | None = None,
        result: dict[str, Any] | None = None,
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


class NullStateStore:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def set_state(self, task_id, state, *, assigned_to=None, result=None) -> None:
        return None

    async def audit(self, **_: Any) -> None:
        return None


@dataclass
class MemoryStateStore:
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def set_state(self, task_id, state, *, assigned_to=None, result=None) -> None:
        row = self.states.setdefault(task_id, {})
        row["state"] = state
        if assigned_to is not None:
            row["assigned_to"] = assigned_to
        if result is not None:
            row["result"] = result

    async def audit(self, *, actor, event, trace_id, task_id, attrs=None) -> None:
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


class PostgresStateStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None

    async def connect(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def set_state(self, task_id, state, *, assigned_to=None, result=None) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks
                   SET state = $2,
                       assigned_to = COALESCE($3, assigned_to),
                       result = COALESCE($4::jsonb, result)
                 WHERE task_id = $1
                """,
                task_id,
                state,
                assigned_to,
                json.dumps(result, default=str) if result else None,
            )

    async def audit(self, *, actor, event, trace_id, task_id, attrs=None) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO audit_events (trace_id, task_id, actor, event, attrs) "
                "VALUES ($1,$2,$3,$4,$5::jsonb)",
                trace_id,
                task_id,
                actor,
                event,
                json.dumps(attrs or {}, default=str),
            )


def build_store(database_url: str | None) -> StateStore:
    return PostgresStateStore(database_url) if database_url else NullStateStore()
