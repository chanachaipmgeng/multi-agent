"""FastAPI application: the single canonical webhook path is ``POST /webhook/gitlab``.

Request pipeline (design §5.3):

1. content-type + payload-size guard            → 415 / 413
2. constant-time ``X-Gitlab-Token`` check        → 401
3. event allowlist                               → 200 ``ignored``
4. project allowlist (``projects.yaml``)         → 403
5. idempotency (``X-Gitlab-Event-UUID`` in Redis)→ 200 ``duplicate``
6. normalize → Task envelope (opt-in label etc.) → 200 ``recorded`` / ``ignored``
7. task store (if configured) + XADD to stream   → 200 ``queued``

The gateway acknowledges within the GitLab 10 s timeout; everything heavy happens
downstream in the coordinator/workers.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis

from . import __version__
from .envelope import TaskState, fallback_event_uuid, normalize
from .idempotency import IdempotencyStore
from .internal import router as internal_router
from .metrics import (
    registry,
    tasks_enqueued_total,
    webhook_auth_fail_total,
    webhook_processing_seconds,
    webhook_received_total,
)
from .projects import ProjectRegistry
from .queue import TaskPublisher
from .rbac import RbacPolicy
from .security import verify_gitlab_token
from .settings import Settings
from .store import TaskStore, build_store

log = logging.getLogger("emaw.gateway")

GATEWAY_ACTOR = "webhook-gateway"


def create_app(
    settings: Settings | None = None,
    *,
    redis: Redis | None = None,
    store: TaskStore | None = None,
    registry_override: ProjectRegistry | None = None,
) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level.upper())

    projects = registry_override or ProjectRegistry.from_yaml(settings.projects_file)
    task_store: TaskStore = store if store is not None else build_store(settings.database_url)
    rbac = RbacPolicy.from_yaml(settings.rbac_file)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.redis = redis or Redis.from_url(settings.redis_url, decode_responses=False)
        app.state.idempotency = IdempotencyStore(
            app.state.redis,
            prefix=settings.idempotency_prefix,
            ttl_seconds=settings.idempotency_ttl_seconds,
        )
        app.state.publisher = TaskPublisher(
            app.state.redis, stream=settings.task_stream, maxlen=settings.task_stream_maxlen
        )
        app.state.store = task_store
        app.state.rbac = rbac
        await task_store.connect()
        log.info(
            "gateway ready: stream=%s projects=%d task_store=%s rbac_users=%d",
            settings.task_stream,
            len(projects.projects),
            type(task_store).__name__,
            len(rbac.users),
        )
        try:
            yield
        finally:
            await task_store.close()
            if redis is None:
                await app.state.redis.aclose()

    app = FastAPI(
        title="EMAW Webhook Gateway",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.projects = projects
    app.state.rbac = rbac
    app.include_router(internal_router)

    # ---------------------------------------------------------------- probes
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        checks: dict[str, bool] = {}
        try:
            checks["redis"] = bool(await request.app.state.redis.ping())
        except Exception:  # noqa: BLE001
            checks["redis"] = False
        checks["task_store"] = await request.app.state.store.ping()
        ok = all(checks.values())
        return JSONResponse(
            {"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503
        )

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    # --------------------------------------------------------------- webhook
    @app.post("/webhook/gitlab")
    async def gitlab_webhook(request: Request) -> JSONResponse:
        started = time.perf_counter()
        st: Settings = request.app.state.settings
        event = request.headers.get("X-Gitlab-Event", "")

        def done(status_code: int, body: dict[str, Any], *, metric_status: str, project: str = "-"):
            webhook_received_total.labels(
                event=event or "-", project=project, status=metric_status
            ).inc()
            webhook_processing_seconds.observe(time.perf_counter() - started)
            return JSONResponse(body, status_code=status_code)

        # 1. transport guards -------------------------------------------------
        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            return done(
                415,
                {"status": "rejected", "reason": "content_type_not_json"},
                metric_status="rejected_content_type",
            )
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > st.max_body_bytes:
            return done(
                413,
                {"status": "rejected", "reason": "payload_too_large"},
                metric_status="rejected_too_large",
            )
        body = await request.body()
        if len(body) > st.max_body_bytes:
            return done(
                413,
                {"status": "rejected", "reason": "payload_too_large"},
                metric_status="rejected_too_large",
            )

        # 2. authentication ---------------------------------------------------
        if not verify_gitlab_token(request.headers.get("X-Gitlab-Token"), st.gitlab_webhook_secret):
            webhook_auth_fail_total.inc()
            log.warning(
                "webhook auth failure from %s", request.client.host if request.client else "?"
            )
            return done(
                401, {"status": "rejected", "reason": "invalid_token"}, metric_status="auth_fail"
            )

        # 3. event allowlist --------------------------------------------------
        if event not in st.allowed_events:
            return done(
                200,
                {"status": "ignored", "reason": "event_not_allowed", "event": event},
                metric_status="ignored_event",
            )

        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
        except ValueError:
            return done(
                400,
                {"status": "rejected", "reason": "invalid_json"},
                metric_status="rejected_invalid_json",
            )

        # 4. project allowlist ------------------------------------------------
        proj_obj = payload.get("project") or {}
        project = request.app.state.projects.resolve(
            proj_obj.get("id") or payload.get("project_id"),
            proj_obj.get("path_with_namespace"),
        )
        if project is None:
            log.warning(
                "webhook for unknown project id=%s path=%s",
                proj_obj.get("id") or payload.get("project_id"),
                proj_obj.get("path_with_namespace"),
            )
            return done(
                403,
                {"status": "rejected", "reason": "project_not_allowed"},
                metric_status="rejected_project",
            )

        # 5. idempotency ------------------------------------------------------
        event_uuid = request.headers.get("X-Gitlab-Event-UUID") or fallback_event_uuid(body)
        idem: IdempotencyStore = request.app.state.idempotency
        if not await idem.claim(event_uuid):
            return done(
                200,
                {"status": "duplicate", "event_uuid": event_uuid},
                metric_status="duplicate",
                project=project.key,
            )

        # 6. normalize --------------------------------------------------------
        result = normalize(
            event=event,
            event_uuid=event_uuid,
            payload=payload,
            project=project,
            registry=request.app.state.projects,
        )
        store: TaskStore = request.app.state.store

        if result.task is None:
            return done(
                200,
                {"status": "ignored", "reason": result.reason},
                metric_status="ignored",
                project=project.key,
            )

        task = result.task
        try:
            created = await store.create_task(task)
            if not created.created:
                await store.audit(
                    actor=GATEWAY_ACTOR,
                    event="task.duplicate_issue",
                    trace_id=task.trace_id,
                    task_id=created.task_id,
                    attrs={"event_uuid": event_uuid, "issue_iid": task.source.issue_iid},
                )
                return done(
                    200,
                    {
                        "status": "attached",
                        "task_id": created.task_id,
                        "reason": "active_task_exists",
                    },
                    metric_status="attached",
                    project=project.key,
                )

            await store.audit(
                actor=GATEWAY_ACTOR,
                event="task.received",
                trace_id=task.trace_id,
                task_id=task.task_id,
                attrs={"event": event, "event_uuid": event_uuid, "type": task.type},
            )

            if result.status == "recorded":
                return done(
                    200,
                    {
                        "status": "recorded",
                        "task_id": task.task_id,
                        "trace_id": task.trace_id,
                        "reason": result.reason,
                    },
                    metric_status="recorded",
                    project=project.key,
                )

            # 7. enqueue ------------------------------------------------------
            publisher: TaskPublisher = request.app.state.publisher
            message_id = await publisher.publish(task)
            await store.audit(
                actor=GATEWAY_ACTOR,
                event="task.queued",
                trace_id=task.trace_id,
                task_id=task.task_id,
                attrs={
                    "stream": publisher.stream,
                    "message_id": message_id,
                    "assigned_to": task.assigned_to,
                },
            )
            tasks_enqueued_total.labels(type=task.type, worker=task.assigned_to or "-").inc()
        except Exception:
            # Let GitLab retry: release the idempotency claim so the retry is not a "duplicate".
            await idem.release(event_uuid)
            log.exception("failed to persist/enqueue task %s", task.task_id)
            return done(
                500,
                {"status": "error", "reason": "enqueue_failed"},
                metric_status="error",
                project=project.key,
            )

        log.info(
            "queued %s type=%s project=%s worker=%s trace=%s",
            task.task_id,
            task.type,
            task.project,
            task.assigned_to,
            task.trace_id,
        )
        return done(
            200,
            {
                "status": "queued",
                "task_id": task.task_id,
                "trace_id": task.trace_id,
                "type": task.type,
                "assigned_to": task.assigned_to,
                "state": TaskState.QUEUED.value,
            },
            metric_status="queued",
            project=project.key,
        )

    return app


def run() -> None:  # pragma: no cover — CLI entry point
    import uvicorn

    settings = Settings()
    uvicorn.run(
        create_app(settings), host=settings.host, port=settings.port, log_level=settings.log_level
    )


if __name__ == "__main__":  # pragma: no cover
    run()
