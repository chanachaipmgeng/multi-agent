"""Task-state updates, handoffs, and audit events written by the adapter."""

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
    async def get_task(self, task_id: str) -> dict[str, Any] | None: ...
    async def add_handoff(
        self,
        *,
        task_id: str,
        from_agent: str,
        to_agent: str,
        reason: str | None = None,
        worktree_path: str | None = None,
        branch: str | None = None,
        summary: str | None = None,
        open_questions: str | None = None,
        artifacts: list[Any] | None = None,
        token_spent: int | None = None,
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

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        return None

    async def add_handoff(self, **_: Any) -> None:
        return None

    async def audit(self, **_: Any) -> None:
        return None


@dataclass
class MemoryStateStore:
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
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

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self.states.get(task_id)
        if row is None:
            return None
        return {"task_id": task_id, **row}

    async def add_handoff(
        self,
        *,
        task_id: str,
        from_agent: str,
        to_agent: str,
        reason: str | None = None,
        worktree_path: str | None = None,
        branch: str | None = None,
        summary: str | None = None,
        open_questions: str | None = None,
        artifacts: list[Any] | None = None,
        token_spent: int | None = None,
    ) -> None:
        self.handoffs.append(
            {
                "task_id": task_id,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "reason": reason,
                "worktree_path": worktree_path,
                "branch": branch,
                "summary": summary,
                "open_questions": open_questions,
                "artifacts": artifacts or [],
                "token_spent": token_spent,
                "created_at": datetime.now(UTC),
            }
        )

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

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT task_id, trace_id, type, project_key, state, assigned_to, "
                "skill, result FROM tasks WHERE task_id = $1",
                task_id,
            )
        if row is None:
            return None
        return dict(row)

    async def add_handoff(
        self,
        *,
        task_id: str,
        from_agent: str,
        to_agent: str,
        reason: str | None = None,
        worktree_path: str | None = None,
        branch: str | None = None,
        summary: str | None = None,
        open_questions: str | None = None,
        artifacts: list[Any] | None = None,
        token_spent: int | None = None,
    ) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO handoffs
                  (task_id, from_agent, to_agent, reason, worktree_path, branch,
                   summary, open_questions, artifacts, token_spent)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10)
                """,
                task_id,
                from_agent,
                to_agent,
                reason,
                worktree_path,
                branch,
                summary,
                open_questions,
                json.dumps(artifacts or [], default=str),
                token_spent,
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
