"""Task store adapters (PostgreSQL in production, in-memory for tests, no-op when unset).

The gateway only *creates* tasks and writes audit events; state transitions are
owned by the coordinator (Phase 3). Schema lives in ``db/migrations``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse

from .envelope import TERMINAL_STATES, Task, TaskState

KNOWN_PAUSE_AGENTS: tuple[str, ...] = (
    "all",
    "coordinator",
    "dev-frontend",
    "dev-backend",
    "reviewer",
    "devops",
    "qa",
)

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


@dataclass(slots=True)
class CreateResult:
    created: bool
    task_id: str


def safe_payload_summary(payload: dict[str, Any] | None, *, max_keys: int = 24) -> dict[str, Any]:
    """Strip likely secrets; keep short scalars for the operator console inbox."""
    if not payload:
        return {}
    deny = ("token", "secret", "password", "authorization", "api_key", "private")
    out: dict[str, Any] = {}
    for i, (key, value) in enumerate(payload.items()):
        if i >= max_keys:
            out["_truncated"] = True
            break
        lk = str(key).lower()
        if any(d in lk for d in deny):
            out[key] = "[REDACTED]"
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value[:500] + "…" if isinstance(value, str) and len(value) > 500 else value
        elif isinstance(value, list):
            out[key] = value[:20]
        elif isinstance(value, dict):
            out[key] = safe_payload_summary(value, max_keys=12)
        else:
            out[key] = str(value)[:200]
    return out


def detect_urls(*blobs: Any) -> list[str]:
    """Collect http(s) URLs from nested task fields for console deep-links."""
    found: list[str] = []
    seen: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, str):
            for m in _URL_RE.findall(obj):
                url = m.rstrip(".,);]")
                if url not in seen:
                    seen.add(url)
                    found.append(url)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for blob in blobs:
        walk(blob)
    return found


def classify_scm_url(url: str) -> str | None:
    host = urlparse(url).hostname or ""
    if "github" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    return None


class TaskStore(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def ping(self) -> bool: ...
    async def create_task(self, task: Task) -> CreateResult: ...
    async def get_task(self, task_id: str, *, detail: bool = False) -> dict[str, Any] | None: ...
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
        payload_summary: dict[str, Any] | None = None,
    ) -> None: ...
    async def get_approval(self, nonce: str) -> dict[str, Any] | None: ...
    async def list_approvals(
        self, *, status: str | None = None, task_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]: ...
    async def decide_approval(self, nonce: str, *, decision: str, decided_by: int) -> None: ...
    async def list_audit(
        self,
        *,
        task_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...
    async def list_handoffs(self, task_id: str, *, limit: int = 50) -> list[dict[str, Any]]: ...
    async def audit(
        self,
        *,
        actor: str,
        event: str,
        trace_id: str | None,
        task_id: str | None,
        attrs: dict[str, Any] | None = None,
    ) -> None: ...
    async def count_by_state(self) -> dict[str, int]: ...


class NullTaskStore:
    enabled = False

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def ping(self) -> bool:
        return True

    async def create_task(self, task: Task) -> CreateResult:
        return CreateResult(created=True, task_id=task.task_id)

    async def get_task(self, task_id: str, *, detail: bool = False) -> dict[str, Any] | None:
        return None

    async def list_tasks(self, *, project=None, state=None, limit=50) -> list[dict[str, Any]]:
        return []

    async def set_state(self, task_id: str, state: str) -> None:
        return None

    async def create_approval(self, **_: Any) -> None:
        return None

    async def get_approval(self, nonce: str) -> dict[str, Any] | None:
        return None

    async def list_approvals(
        self, *, status: str | None = None, task_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return []

    async def decide_approval(self, nonce: str, *, decision: str, decided_by: int) -> None:
        return None

    async def list_audit(
        self,
        *,
        task_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return []

    async def list_handoffs(self, task_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return []

    async def audit(self, **_: Any) -> None:
        return None

    async def count_by_state(self) -> dict[str, int]:
        return {}


def _iso(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


@dataclass
class MemoryTaskStore:
    enabled: bool = True
    tasks: dict[str, Task] = field(default_factory=dict)
    approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)

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

    async def get_task(self, task_id: str, *, detail: bool = False) -> dict[str, Any] | None:
        t = self.tasks.get(task_id)
        if t is None:
            return None
        data: dict[str, Any] = {
            "task_id": t.task_id,
            "trace_id": t.trace_id,
            "type": t.type,
            "project_key": t.project,
            "project": t.project,
            "state": t.state.value if isinstance(t.state, TaskState) else t.state,
            "assigned_to": t.assigned_to,
            "skill": t.skill,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        if detail:
            data["source"] = t.source.model_dump()
            data["inputs"] = t.inputs
            data["constraints"] = t.constraints.model_dump()
            data["requester"] = t.requester.model_dump()
            data["handoffs"] = await self.list_handoffs(task_id)
            data["links"] = detect_urls(data["source"], data["inputs"], data["handoffs"])
        return data

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
        payload_summary: dict[str, Any] | None = None,
    ) -> None:
        self.approvals[nonce] = {
            "task_id": task_id,
            "action": action,
            "payload_hash": payload_hash,
            "payload_summary": payload_summary or {},
            "nonce": nonce,
            "requested_by": requested_by,
            "required_role": required_role,
            "timeout_at": timeout_at,
            "requested_at": datetime.now(UTC),
            "decision": None,
            "decided_by": None,
        }

    async def get_approval(self, nonce: str) -> dict[str, Any] | None:
        row = self.approvals.get(nonce)
        if row is None:
            return None
        out = dict(row)
        for k in ("timeout_at", "requested_at", "decided_at"):
            out[k] = _iso(out.get(k))
        return out

    async def list_approvals(
        self, *, status: str | None = None, task_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for nonce, row in self.approvals.items():
            if task_id and row.get("task_id") != task_id:
                continue
            decision = row.get("decision")
            if status == "pending" and decision is not None:
                continue
            if status and status != "pending" and decision != status:
                continue
            item = await self.get_approval(nonce)
            if item:
                rows.append(item)
            if len(rows) >= limit:
                break
        return rows

    async def decide_approval(self, nonce: str, *, decision: str, decided_by: int) -> None:
        row = self.approvals.get(nonce)
        if row is not None:
            row["decision"] = decision
            row["decided_by"] = decided_by
            row["decided_at"] = datetime.now(UTC)

    async def list_audit(
        self,
        *,
        task_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for ev in reversed(self.audit_events):
            if task_id and ev.get("task_id") != task_id:
                continue
            if trace_id and ev.get("trace_id") != trace_id:
                continue
            item = dict(ev)
            item["ts"] = _iso(item.get("ts"))
            rows.append(item)
            if len(rows) >= limit:
                break
        return rows

    async def list_handoffs(self, task_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return [h for h in self.handoffs if h.get("task_id") == task_id][:limit]

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

    async def count_by_state(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in self.tasks.values():
            st = t.state.value if isinstance(t.state, TaskState) else str(t.state)
            out[st] = out.get(st, 0) + 1
        return out


class PostgresTaskStore:
    enabled = True

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None

    async def connect(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> bool:
        if self._pool is None:
            return False
        async with self._pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True

    async def create_task(self, task: Task) -> CreateResult:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            existing = None
            if task.source.issue_iid is not None:
                existing = await conn.fetchval(
                    """
                    SELECT task_id FROM tasks
                     WHERE project_key = $1 AND issue_iid = $2
                       AND state NOT IN ('DONE','FAILED','CANCELLED','EXPIRED','REJECTED')
                    """,
                    task.project,
                    task.source.issue_iid,
                )
            if existing:
                return CreateResult(created=False, task_id=existing)
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

    async def get_task(self, task_id: str, *, detail: bool = False) -> dict[str, Any] | None:
        assert self._pool is not None, "store not connected"
        cols = (
            "task_id, trace_id, type, project_key, state, assigned_to, skill, "
            "result, created_at, updated_at"
        )
        if detail:
            cols = (
                "task_id, trace_id, type, project_key, state, assigned_to, skill, "
                "source, inputs, constraints, result, created_at, updated_at"
            )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {cols} FROM tasks WHERE task_id = $1", task_id)
        if row is None:
            return None
        data = dict(row)
        data["project"] = data.get("project_key")
        for k in ("created_at", "updated_at"):
            data[k] = _iso(data.get(k))
        for k in ("source", "inputs", "constraints", "result"):
            if k in data:
                data[k] = _maybe_json(data[k])
        if detail:
            data["handoffs"] = await self.list_handoffs(task_id)
            data["links"] = detect_urls(
                data.get("source"), data.get("inputs"), data.get("handoffs")
            )
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
            data["created_at"] = _iso(data.get("created_at"))
            out.append(data)
        return out

    async def set_state(self, task_id: str, state: str) -> None:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            await conn.execute("UPDATE tasks SET state = $2 WHERE task_id = $1", task_id, state)

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
        payload_summary: dict[str, Any] | None = None,
    ) -> None:
        assert self._pool is not None, "store not connected"
        summary = json.dumps(payload_summary or {}, default=str)
        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO approvals
                      (task_id, action, payload_hash, nonce, requested_by, required_role,
                       timeout_at, payload_summary)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)
                    """,
                    task_id,
                    action,
                    payload_hash,
                    nonce,
                    requested_by,
                    required_role,
                    timeout_at,
                    summary,
                )
            except Exception:  # noqa: BLE001 — pre-0003 migration
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

    def _normalize_approval(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for k in ("timeout_at", "requested_at", "decided_at"):
            data[k] = _iso(data.get(k))
        data["payload_summary"] = _maybe_json(data.get("payload_summary")) or {}
        return data

    async def get_approval(self, nonce: str) -> dict[str, Any] | None:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT task_id, action, payload_hash, nonce, requested_by, required_role, "
                    "timeout_at, decision, decided_by, decided_at, requested_at, "
                    "COALESCE(payload_summary, '{}'::jsonb) AS payload_summary "
                    "FROM approvals WHERE nonce = $1",
                    nonce,
                )
            except Exception:  # noqa: BLE001
                row = await conn.fetchrow(
                    "SELECT task_id, action, payload_hash, nonce, requested_by, required_role, "
                    "timeout_at, decision, decided_by, decided_at, requested_at "
                    "FROM approvals WHERE nonce = $1",
                    nonce,
                )
        if row is None:
            return None
        return self._normalize_approval(row)

    async def list_approvals(
        self, *, status: str | None = None, task_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        assert self._pool is not None, "store not connected"
        clauses: list[str] = []
        args: list[Any] = []
        if task_id:
            args.append(task_id)
            clauses.append(f"task_id = ${len(args)}")
        if status == "pending":
            clauses.append("decision IS NULL")
        elif status:
            args.append(status)
            clauses.append(f"decision = ${len(args)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(limit)
        base = (
            "task_id, action, payload_hash, nonce, requested_by, required_role, "
            "timeout_at, decision, decided_by, decided_at, requested_at"
        )
        sql = (
            f"SELECT {base}, COALESCE(payload_summary, '{{}}'::jsonb) AS payload_summary "
            f"FROM approvals {where} ORDER BY requested_at DESC LIMIT ${len(args)}"
        )
        async with self._pool.acquire() as conn:
            try:
                rows = await conn.fetch(sql, *args)
            except Exception:  # noqa: BLE001
                rows = await conn.fetch(
                    f"SELECT {base} FROM approvals {where} "
                    f"ORDER BY requested_at DESC LIMIT ${len(args)}",
                    *args,
                )
        return [self._normalize_approval(r) for r in rows]

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

    async def list_audit(
        self,
        *,
        task_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        assert self._pool is not None, "store not connected"
        clauses: list[str] = []
        args: list[Any] = []
        if task_id:
            args.append(task_id)
            clauses.append(f"task_id = ${len(args)}")
        if trace_id:
            args.append(trace_id)
            clauses.append(f"trace_id = ${len(args)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(limit)
        sql = (
            f"SELECT id, ts, trace_id, task_id, actor, event, attrs "
            f"FROM audit_events {where} ORDER BY ts DESC LIMIT ${len(args)}"
        )
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        out = []
        for row in rows:
            data = dict(row)
            data["ts"] = _iso(data.get("ts"))
            data["attrs"] = _maybe_json(data.get("attrs")) or {}
            out.append(data)
        return out

    async def list_handoffs(self, task_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, task_id, from_agent, to_agent, reason, worktree_path, branch,
                       summary, open_questions, artifacts, token_spent, created_at
                  FROM handoffs WHERE task_id = $1
                 ORDER BY created_at ASC LIMIT $2
                """,
                task_id,
                limit,
            )
        out = []
        for row in rows:
            data = dict(row)
            data["created_at"] = _iso(data.get("created_at"))
            data["artifacts"] = _maybe_json(data.get("artifacts")) or []
            out.append(data)
        return out

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

    async def count_by_state(self) -> dict[str, int]:
        assert self._pool is not None, "store not connected"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT state, count(*)::int AS n FROM tasks GROUP BY state"
            )
        return {str(r["state"]): int(r["n"]) for r in rows}


def build_store(database_url: str | None) -> TaskStore:
    if not database_url:
        return NullTaskStore()
    return PostgresTaskStore(database_url)


__all__ = [
    "KNOWN_PAUSE_AGENTS",
    "CreateResult",
    "MemoryTaskStore",
    "NullTaskStore",
    "PostgresTaskStore",
    "TaskState",
    "TaskStore",
    "build_store",
    "classify_scm_url",
    "detect_urls",
    "safe_payload_summary",
]
