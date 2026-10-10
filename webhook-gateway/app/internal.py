"""Internal control-plane API for the coordinator (Phase 3 / DECISION-16).

Authenticated with ``Authorization: Bearer <hermes_api_key>`` and
``X-EMAW-User-Id: <telegram_user_id>``. Reachable only on the ``control`` network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .envelope import (
    DEFAULT_SKILL_FOR_TYPE,
    WORKER_CONSTRAINTS,
    Task,
    TaskConstraints,
    TaskRequester,
    TaskSource,
    TaskState,
    TaskType,
    new_task_id,
    new_trace_id,
)
from .rbac import RbacPolicy
from .store import KNOWN_PAUSE_AGENTS, safe_payload_summary

log = logging.getLogger("emaw.gateway.internal")

router = APIRouter(prefix="/internal", tags=["internal"])

ACTOR = "coordinator"


def _require_auth(request: Request, authorization: str | None) -> None:
    expected = request.app.state.settings.hermes_api_key
    if not expected:
        raise HTTPException(503, detail="internal API key not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(token, expected):
        raise HTTPException(401, detail="invalid bearer token")


def _user_id(x_emaw_user_id: str | None) -> int:
    if not x_emaw_user_id or not x_emaw_user_id.strip().isdigit():
        raise HTTPException(400, detail="X-EMAW-User-Id required (telegram user id)")
    return int(x_emaw_user_id.strip())


def _rbac(request: Request) -> RbacPolicy:
    return request.app.state.rbac


# ------------------------------------------------------------------- models
class CreateTaskBody(BaseModel):
    type: TaskType = "feature"
    project: str
    skill: str | None = None
    assigned_to: str | None = None
    instruction: str = ""
    labels: list[str] = Field(default_factory=list)
    branch: str | None = None
    idempotency_key: str | None = None


class ApprovalBody(BaseModel):
    task_id: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    required_role: str = "developer"
    timeout_min: int = 30
    requested_by: str = "coordinator"


class DecideBody(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = None


class ControlBody(BaseModel):
    agent: str = "all"  # role name or "all"
    enabled: bool | None = None  # for safe-mode


# --------------------------------------------------------------------- tasks
@router.post("/tasks")
async def create_task(
    body: CreateTaskBody,
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "route-task", body.project)
    if not ok:
        raise HTTPException(403, detail=reason)

    projects = request.app.state.projects
    project = projects.by_key(body.project) if hasattr(projects, "by_key") else None
    if project is None:
        # ProjectRegistry uses list lookup
        project = next((p for p in projects.projects if p.key == body.project), None)
    if project is None:
        raise HTTPException(404, detail=f"unknown project: {body.project}")

    worker = body.assigned_to
    if not worker:
        worker = projects.route(project, body.type, body.labels)
    if worker not in project.allowed_workers:
        raise HTTPException(400, detail=f"worker {worker} not allowed on {body.project}")

    skill = body.skill or DEFAULT_SKILL_FOR_TYPE.get(body.type) or "dev-flow"
    constraints = WORKER_CONSTRAINTS.get(worker, WORKER_CONSTRAINTS["dev-backend"])
    now = datetime.now(UTC)
    task = Task(
        task_id=new_task_id(now),
        trace_id=new_trace_id(),
        type=body.type,
        project=body.project,
        source=TaskSource(kind="telegram", event="telegram_command"),
        requester=TaskRequester(
            channel="telegram", user_id=user_id, username="", role="telegram_user"
        ),
        assigned_to=worker,
        skill=skill,
        inputs={
            "instruction": body.instruction,
            "labels": body.labels,
            "branch": body.branch,
            "workspace_path": project.workspace_path,
            "test_command": project.test_command,
        },
        constraints=TaskConstraints(**constraints),
        state=TaskState.QUEUED,
        created_at=now,
    )

    # Idempotency for telegram-originated tasks
    idem = request.app.state.idempotency
    key = body.idempotency_key or f"tg:{user_id}:{body.project}:{hashlib.sha256(body.instruction.encode()).hexdigest()[:12]}"
    if not await idem.claim(key):
        return {"status": "duplicate", "idempotency_key": key}

    store = request.app.state.store
    result = await store.create_task(task)
    if not result.created:
        return {"status": "exists", "task_id": result.task_id, "trace_id": task.trace_id}

    await store.audit(
        actor=ACTOR,
        event="task.queued",
        trace_id=task.trace_id,
        task_id=task.task_id,
        attrs={"source": "telegram", "worker": worker, "user_id": user_id},
    )
    msg_id = await request.app.state.publisher.publish(task)
    log.info(
        "queued task_id=%s type=%s project=%s worker=%s scm=internal "
        "trace_id=%s event_uuid=- user_id=%s",
        task.task_id,
        task.type,
        task.project,
        worker,
        task.trace_id,
        user_id,
    )
    return {
        "status": "queued",
        "task_id": task.task_id,
        "trace_id": task.trace_id,
        "assigned_to": worker,
        "skill": skill,
        "stream_id": msg_id,
    }


@router.get("/tasks")
async def list_tasks(
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
    project: str | None = None,
    state: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "status-report", project)
    if not ok:
        raise HTTPException(403, detail=reason)
    store = request.app.state.store
    rows = await store.list_tasks(project=project, state=state, limit=min(limit, 200))
    return {"tasks": rows, "count": len(rows)}


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "status-report")
    if not ok:
        raise HTTPException(403, detail=reason)
    row = await request.app.state.store.get_task(task_id, detail=True)
    if row is None:
        raise HTTPException(404, detail="task not found")
    return row


# ---------------------------------------------------------------- approvals
@router.post("/approvals")
async def request_approval(
    body: ApprovalBody,
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    # Creating an approval request is allowed for coordinator / developers
    ok, reason = _rbac(request).authorize(user_id, "approve-push")
    # Also allow admin
    if not ok:
        ok2, _ = _rbac(request).authorize(user_id, "pause")  # admin-only command as proxy
        if not ok2:
            raise HTTPException(403, detail=reason)

    nonce = secrets.token_urlsafe(16)
    payload_hash = hashlib.sha256(
        json.dumps(body.payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    summary = safe_payload_summary(body.payload)
    timeout_at = datetime.now(UTC) + timedelta(minutes=body.timeout_min)
    await request.app.state.store.create_approval(
        task_id=body.task_id,
        action=body.action,
        payload_hash=payload_hash,
        nonce=nonce,
        requested_by=body.requested_by,
        required_role=body.required_role,
        timeout_at=timeout_at,
        payload_summary=summary,
    )
    await request.app.state.store.set_state(body.task_id, "AWAITING_APPROVAL")
    await request.app.state.store.audit(
        actor=ACTOR,
        event="approval.requested",
        trace_id=None,
        task_id=body.task_id,
        attrs={"action": body.action, "nonce": nonce, "required_role": body.required_role},
    )
    return {
        "nonce": nonce,
        "timeout_at": timeout_at.isoformat(),
        "payload_hash": payload_hash,
        "payload_summary": summary,
    }


@router.get("/approvals")
async def list_approvals(
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
    status: str | None = "pending",
    task_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "status-report")
    if not ok:
        raise HTTPException(403, detail=reason)
    rows = await request.app.state.store.list_approvals(
        status=status, task_id=task_id, limit=min(limit, 200)
    )
    return {"approvals": rows, "count": len(rows)}


@router.get("/approvals/{nonce}")
async def get_approval(
    nonce: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "status-report")
    if not ok:
        raise HTTPException(403, detail=reason)
    row = await request.app.state.store.get_approval(nonce)
    if row is None:
        raise HTTPException(404, detail="unknown nonce")
    return row


@router.post("/approvals/{nonce}/decide")
async def decide_approval(
    nonce: str,
    body: DecideBody,
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    store = request.app.state.store
    row = await store.get_approval(nonce)
    if row is None:
        raise HTTPException(404, detail="unknown nonce")
    if row.get("decision"):
        raise HTTPException(409, detail="already decided")
    timeout_at = row.get("timeout_at")
    if isinstance(timeout_at, str):
        timeout_at = datetime.fromisoformat(timeout_at)
    if timeout_at and getattr(timeout_at, "tzinfo", None) is None:
        timeout_at = timeout_at.replace(tzinfo=UTC)
    if timeout_at and datetime.now(UTC) > timeout_at:
        await store.decide_approval(nonce, decision="expired", decided_by=user_id)
        await store.set_state(row["task_id"], "EXPIRED")
        await store.audit(
            actor=f"human:{user_id}",
            event="approval.expired",
            trace_id=None,
            task_id=row["task_id"],
            attrs={"nonce": nonce},
        )
        raise HTTPException(410, detail="approval expired")

    required = row.get("required_role") or "developer"
    cmd = "approve-migration" if required == "approver" else "approve-push"
    if required == "approver":
        cmd = "deploy-prod" if "deploy" in (row.get("action") or "") else "approve-migration"
    ok, reason = _rbac(request).authorize(user_id, cmd if cmd in _rbac(request).commands else "approve-push")
    if required == "approver" and not _rbac(request).has_role(user_id, "approver") and not _rbac(request).has_role(user_id, "admin"):
        raise HTTPException(403, detail="approver_role_required")
    if not ok and not _rbac(request).has_role(user_id, "admin"):
        raise HTTPException(403, detail=reason)

    # Separation of duties (DECISION-8)
    task = await store.get_task(row["task_id"])
    project = (task or {}).get("project_key") or (task or {}).get("project")
    if body.decision == "approved" and _rbac(request).is_approver_conflict(user_id, project):
        # Only block when required_role is approver
        if required == "approver":
            raise HTTPException(403, detail="approver_developer_conflict")

    await store.decide_approval(nonce, decision=body.decision, decided_by=user_id)
    new_state = "APPROVED" if body.decision == "approved" else "CANCELLED"
    await store.set_state(row["task_id"], new_state)
    requested_at = row.get("requested_at")
    if requested_at is not None:
        try:
            from .metrics import approval_latency_seconds

            if getattr(requested_at, "tzinfo", None) is None:
                requested_at = requested_at.replace(tzinfo=UTC)
            approval_latency_seconds.observe(
                max(0.0, (datetime.now(UTC) - requested_at).total_seconds())
            )
        except Exception:  # noqa: BLE001
            pass
    audit_attrs: dict[str, Any] = {"nonce": nonce, "action": row.get("action")}
    if body.comment:
        audit_attrs["comment"] = body.comment.strip()[:2000]
    await store.audit(
        actor=f"human:{user_id}",
        event=f"approval.{body.decision}",
        trace_id=None,
        task_id=row["task_id"],
        attrs=audit_attrs,
    )
    return {"status": body.decision, "task_id": row["task_id"], "state": new_state}


# ------------------------------------------------------------------- control
@router.post("/control/pause")
async def control_pause(
    body: ControlBody,
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "pause")
    if not ok:
        raise HTTPException(403, detail=reason)
    agent = body.agent or "all"
    key = f"{request.app.state.settings.control_prefix}:pause:{agent}"
    await request.app.state.redis.set(key, "1")
    await request.app.state.store.audit(
        actor=f"human:{user_id}",
        event="control.pause",
        trace_id=None,
        task_id=None,
        attrs={"agent": agent},
    )
    return {"status": "paused", "agent": agent}


@router.post("/control/resume")
async def control_resume(
    body: ControlBody,
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "resume")
    if not ok:
        # fall back to pause permission (admin)
        ok, reason = _rbac(request).authorize(user_id, "pause")
    if not ok:
        raise HTTPException(403, detail=reason)
    agent = body.agent or "all"
    key = f"{request.app.state.settings.control_prefix}:pause:{agent}"
    await request.app.state.redis.delete(key)
    await request.app.state.store.audit(
        actor=f"human:{user_id}",
        event="control.resume",
        trace_id=None,
        task_id=None,
        attrs={"agent": agent},
    )
    return {"status": "resumed", "agent": agent}


@router.post("/control/safe-mode")
async def control_safe_mode(
    body: ControlBody,
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "safe-mode")
    if not ok:
        raise HTTPException(403, detail=reason)
    key = f"{request.app.state.settings.control_prefix}:safe_mode"
    enabled = True if body.enabled is None else body.enabled
    if enabled:
        await request.app.state.redis.set(key, "1")
    else:
        await request.app.state.redis.delete(key)
    await request.app.state.store.audit(
        actor=f"human:{user_id}",
        event="control.safe_mode",
        trace_id=None,
        task_id=None,
        attrs={"enabled": enabled},
    )
    return {"status": "ok", "safe_mode": enabled}


@router.get("/control/status")
async def control_status(
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    _user_id(x_emaw_user_id)
    prefix = request.app.state.settings.control_prefix
    redis = request.app.state.redis
    paused_agents: list[str] = []
    for agent in KNOWN_PAUSE_AGENTS:
        if await redis.get(f"{prefix}:pause:{agent}"):
            paused_agents.append(agent)
    return {
        "safe_mode": bool(await redis.get(f"{prefix}:safe_mode")),
        "pause_all": bool(await redis.get(f"{prefix}:pause:all")),
        "paused_agents": paused_agents,
    }


@router.get("/projects")
async def list_projects(
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "status-report")
    if not ok:
        raise HTTPException(403, detail=reason)
    projects = request.app.state.projects
    rows = []
    for p in projects.projects:
        rows.append(
            {
                "key": p.key,
                "scm": getattr(p, "scm", "gitlab"),
                "gitlab_project_id": p.gitlab_project_id,
                "repo": getattr(p, "repo", None),
                "repo_id": getattr(p, "repo_id", None),
                "path_with_namespace": p.path_with_namespace,
                "workspace_path": p.workspace_path,
                "default_worker": p.default_worker,
                "allowed_workers": p.allowed_workers,
                "opt_in_label": p.opt_in_label,
                "data_classification": p.data_classification,
                "llm_backend": p.llm_backend,
            }
        )
    return {"projects": rows, "count": len(rows)}


@router.get("/audit")
async def list_audit(
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
    task_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "status-report")
    if not ok:
        raise HTTPException(403, detail=reason)
    if not task_id and not trace_id:
        raise HTTPException(400, detail="task_id or trace_id required")
    rows = await request.app.state.store.list_audit(
        task_id=task_id, trace_id=trace_id, limit=min(limit, 500)
    )
    return {"events": rows, "count": len(rows)}


@router.get("/rbac/users")
async def list_rbac_users(
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
) -> dict[str, Any]:
    """Dev helper for the console user picker (ids + names + roles only)."""
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "status-report")
    if not ok:
        raise HTTPException(403, detail=reason)
    policy = _rbac(request)
    users = [
        {
            "user_id": int(uid) if str(uid).isdigit() else uid,
            "name": u.name,
            "roles": list(u.roles),
        }
        for uid, u in policy.users.items()
    ]
    return {"users": users, "count": len(users)}


@router.get("/ops/summary")
async def ops_summary(
    request: Request,
    authorization: str | None = Header(default=None),
    x_emaw_user_id: str | None = Header(default=None, alias="X-EMAW-User-Id"),
    recent_limit: int = 12,
) -> dict[str, Any]:
    """Aggregated Home strip for Operator Console (viewer+ via status-report)."""
    _require_auth(request, authorization)
    user_id = _user_id(x_emaw_user_id)
    ok, reason = _rbac(request).authorize(user_id, "status-report")
    if not ok:
        raise HTTPException(403, detail=reason)

    store = request.app.state.store
    prefix = request.app.state.settings.control_prefix
    redis = request.app.state.redis

    redis_ok = False
    try:
        pong = await redis.ping()
        redis_ok = bool(pong)
    except Exception:  # noqa: BLE001 — summary must stay partial on redis blip
        redis_ok = False

    paused_agents: list[str] = []
    safe_mode = False
    pause_all = False
    if redis_ok:
        for agent in KNOWN_PAUSE_AGENTS:
            if await redis.get(f"{prefix}:pause:{agent}"):
                paused_agents.append(agent)
        safe_mode = bool(await redis.get(f"{prefix}:safe_mode"))
        pause_all = bool(await redis.get(f"{prefix}:pause:all"))

    pending = await store.list_approvals(status="pending", task_id=None, limit=200)
    recent = await store.list_tasks(project=None, state=None, limit=min(max(recent_limit, 1), 50))
    by_state = await store.count_by_state()

    return {
        "gateway": {"status": "ok", "version": "0.1.0"},
        "redis_ok": redis_ok,
        "store_enabled": bool(getattr(store, "enabled", True)),
        "control": {
            "safe_mode": safe_mode,
            "pause_all": pause_all,
            "paused_agents": paused_agents,
        },
        "approvals_pending": len(pending),
        "tasks_by_state": by_state,
        "tasks_recent": [
            {
                "task_id": t.get("task_id"),
                "trace_id": t.get("trace_id"),
                "type": t.get("type"),
                "project": t.get("project") or t.get("project_key"),
                "state": t.get("state"),
                "assigned_to": t.get("assigned_to"),
                "skill": t.get("skill"),
                "created_at": t.get("created_at"),
            }
            for t in recent
        ],
    }
