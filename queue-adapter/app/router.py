"""Router mode: fan-out ``stream:tasks`` → ``stream:<role>`` and apply results (DECISION-16)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from .breaker import CircuitBreaker
from .control import ControlPlane
from .handoff import parse_handoff
from . import metrics
from .notify import TelegramNotifier
from .projects import DEV_WORKERS, ProjectRegistry
from .settings import Settings
from .store import StateStore

log = logging.getLogger("emaw.adapter.router")

ACTOR = "router"


def _s(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class Router:
    def __init__(
        self,
        settings: Settings,
        *,
        redis: Redis,
        store: StateStore,
        control: ControlPlane,
        breaker: CircuitBreaker,
        notifier: TelegramNotifier,
        registry: ProjectRegistry | None = None,
    ) -> None:
        self.s = settings
        self.redis = redis
        self.store = store
        self.control = control
        self.breaker = breaker
        self.notifier = notifier
        self.registry = registry
        self.processed = 0
        self.results_group = "router-results"
        self._last_metrics_at = 0.0
        self._metrics_interval_seconds = 15.0

    async def ensure_groups(self) -> None:
        for stream, group in (
            (self.s.task_stream, self.s.consumer_group),
            (self.s.results_stream, self.results_group),
        ):
            try:
                await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
                log.info("created consumer group %s on %s", group, stream)
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    async def heartbeat(self) -> None:
        await self.redis.set(self.s.heartbeat_key, str(int(time.time())), ex=180)
        Path(self.s.heartbeat_file).write_text(str(int(time.time())), encoding="utf-8")

    async def run_once(self, *, block_ms: int | None = None) -> int:
        handled = 0
        handled += await self._claim_stale_tasks()
        # Pending first (id=0): pause-deferred work resumes without waiting claim_min_idle.
        handled += await self._read_tasks(start_id="0")
        # Non-blocking new-message drain: Redis BLOCK 0 means "wait forever", so omit block.
        handled += await self._read_tasks(start_id=">")
        handled += await self._read_results(block_ms=block_ms)
        await self.heartbeat()
        now = time.time()
        if now - self._last_metrics_at >= self._metrics_interval_seconds:
            await self.refresh_gauges()
            self._last_metrics_at = now
        return handled

    async def refresh_gauges(self) -> None:
        """Publish §8.2 queue / heartbeat / task-state gauges (best-effort)."""
        streams = [
            self.s.task_stream,
            self.s.results_stream,
            self.s.dead_letter_stream,
        ]
        for role in ("dev-frontend", "dev-backend", "reviewer", "qa", "devops"):
            streams.append(self.s.role_stream(role))
        now_ms = int(time.time() * 1000)
        for stream in streams:
            try:
                depth = int(await self.redis.xlen(stream))
            except Exception:  # noqa: BLE001
                depth = 0
            metrics.set_gauge("queue_depth", float(depth), {"stream": stream})
            age = 0.0
            if depth > 0:
                try:
                    first = await self.redis.xrange(stream, count=1)
                    if first:
                        mid = _s(first[0][0])
                        ts_ms = int(mid.split("-", 1)[0])
                        age = max(0.0, (now_ms - ts_ms) / 1000.0)
                except Exception:  # noqa: BLE001
                    age = 0.0
            metrics.set_gauge("queue_oldest_age_seconds", age, {"stream": stream})

        try:
            async for key in self.redis.scan_iter(match="emaw:heartbeat:*", count=50):
                k = _s(key)
                agent = k.rsplit(":", 1)[-1]
                raw = await self.redis.get(key)
                if raw is None:
                    continue
                try:
                    ts = float(_s(raw))
                except ValueError:
                    continue
                metrics.set_gauge("agent_heartbeat_timestamp", ts, {"agent": agent})
        except Exception:  # noqa: BLE001
            log.debug("heartbeat gauge scan failed", exc_info=True)

        try:
            counts = await self.store.count_by_state()
            for state, n in counts.items():
                metrics.set_gauge("task_state_total", float(n), {"state": state})
        except Exception:  # noqa: BLE001
            log.debug("task_state_total gauge failed", exc_info=True)

    async def _claim_stale_tasks(self) -> int:
        _next, messages, _deleted = await self.redis.xautoclaim(
            self.s.task_stream,
            self.s.consumer_group,
            self.s.consumer_name,
            min_idle_time=self.s.claim_min_idle_ms,
            start_id="0-0",
            count=10,
        )
        for message_id, fields in messages:
            await self.handle_task(_s(message_id), fields)
        return len(messages)

    async def _read_tasks(self, *, start_id: str = ">") -> int:
        entries = await self.redis.xreadgroup(
            self.s.consumer_group,
            self.s.consumer_name,
            {self.s.task_stream: start_id},
            count=10,
        )
        handled = 0
        for _stream, messages in entries or []:
            for message_id, fields in messages:
                await self.handle_task(_s(message_id), fields)
                handled += 1
        return handled

    async def _read_results(self, *, block_ms: int | None) -> int:
        entries = await self.redis.xreadgroup(
            self.results_group,
            self.s.consumer_name,
            {self.s.results_stream: ">"},
            count=10,
            block=self.s.block_ms if block_ms is None else block_ms,
        )
        handled = 0
        for _stream, messages in entries or []:
            for message_id, fields in messages:
                await self.handle_result(_s(message_id), fields)
                handled += 1
        return handled

    # ----------------------------------------------------------------- tasks
    async def handle_task(self, message_id: str, fields: dict[Any, Any]) -> None:
        raw = fields.get(b"envelope") or fields.get("envelope")
        try:
            task: dict[str, Any] = json.loads(_s(raw))
        except (TypeError, ValueError):
            log.error("task message %s has no valid envelope; acking", message_id)
            await self.redis.xack(self.s.task_stream, self.s.consumer_group, message_id)
            return

        task_id = task.get("task_id", "?")
        trace_id = task.get("trace_id")
        worker = (
            self.registry.resolve_worker(task)
            if self.registry is not None
            else (task.get("assigned_to") or "dev-backend")
        )

        if await self.control.is_paused(worker):
            log.info("paused — deferring %s for %s", task_id, worker)
            # leave un-acked so XAUTOCLAIM re-delivers after idle
            return

        if await self.control.is_safe_mode():
            constraints = dict(task.get("constraints") or {})
            constraints["require_approval"] = True
            task["constraints"] = constraints

        task["assigned_to"] = worker
        role_stream = self.s.role_stream(worker)
        await self.redis.xadd(
            role_stream,
            {
                "task_id": task_id,
                "trace_id": trace_id or "",
                "type": task.get("type") or "",
                "project": task.get("project") or "",
                "assigned_to": worker,
                "state": "ASSIGNED",
                "envelope": json.dumps(task, default=str),
            },
            maxlen=self.s.stream_maxlen,
            approximate=True,
        )
        await self.store.set_state(task_id, "ASSIGNED", assigned_to=worker)
        await self.store.audit(
            actor=ACTOR,
            event="task.routed",
            trace_id=trace_id,
            task_id=task_id,
            attrs={"worker": worker, "stream": role_stream, "safe_mode": await self.control.is_safe_mode()},
        )
        metrics.inc("emaw_tasks_routed_total")
        await self.redis.xack(self.s.task_stream, self.s.consumer_group, message_id)
        self.processed += 1
        log.info(
            "routed task_id=%s worker=%s trace_id=%s",
            task_id,
            worker,
            trace_id or "-",
        )

    # --------------------------------------------------------------- results
    async def handle_result(self, message_id: str, fields: dict[Any, Any]) -> None:
        task_id = _s(fields.get(b"task_id") or fields.get("task_id") or "?")
        trace_id = _s(fields.get(b"trace_id") or fields.get("trace_id") or "") or None
        status = _s(fields.get(b"status") or fields.get("status") or "").lower()
        from_agent = _s(fields.get(b"from_agent") or fields.get("from_agent") or "")
        handoff_raw = fields.get(b"handoff") or fields.get("handoff")
        usage_raw = fields.get(b"usage") or fields.get("usage")
        detail = _s(fields.get(b"detail") or fields.get("detail") or "")

        handoff: dict[str, Any] | None = None
        if handoff_raw:
            try:
                handoff = json.loads(_s(handoff_raw))
            except (TypeError, ValueError):
                handoff = parse_handoff(_s(handoff_raw))

        usage: dict[str, Any] | None = None
        if usage_raw:
            try:
                usage = json.loads(_s(usage_raw))
            except (TypeError, ValueError):
                usage = None

        tokens = 0
        if usage:
            tokens = int(usage.get("total_tokens") or usage.get("total") or 0)
            if from_agent and tokens:
                await self.breaker.record_tokens(from_agent, tokens)

        if status in {"failed", "error", "dead_letter"}:
            await self.store.set_state(
                task_id, "FAILED", result={"error": detail[:500], "from_agent": from_agent}
            )
            await self.store.audit(
                actor=ACTOR,
                event="task.failed",
                trace_id=trace_id,
                task_id=task_id,
                attrs={"from_agent": from_agent, "detail": detail[:300]},
            )
            await self.breaker.record_failure(task_id)
            metrics.inc("emaw_tasks_failed_total")
            await self.redis.xack(self.s.results_stream, self.results_group, message_id)
            self.processed += 1
            return

        if status in {"waiting_for_approval", "awaiting_approval"}:
            await self.store.set_state(task_id, "AWAITING_APPROVAL")
            await self.store.audit(
                actor=ACTOR,
                event="task.awaiting_approval",
                trace_id=trace_id,
                task_id=task_id,
                attrs={"from_agent": from_agent},
            )
            await self.redis.xack(self.s.results_stream, self.results_group, message_id)
            self.processed += 1
            return

        # completed / dispatched / done
        target = (handoff or {}).get("to_agent") or ""
        reason = (handoff or {}).get("reason") or ""

        # Fallback: completed by a dev worker with no HANDOFF → auto-route to reviewer
        if not target and from_agent in DEV_WORKERS and status in {"completed", "dispatched", "done"}:
            project = self.registry.by_key(
                (await self.store.get_task(task_id) or {}).get("project_key")
                or _s(fields.get(b"project") or fields.get("project") or "")
            ) if self.registry else None
            if project is None and self.registry is not None:
                # try project from fields
                proj_key = _s(fields.get(b"project") or fields.get("project") or "")
                project = self.registry.by_key(proj_key)
            if project and "reviewer" in project.allowed_workers:
                target = "reviewer"
                reason = reason or "auto_review_fallback"
                handoff = handoff or {
                    "to_agent": "reviewer",
                    "reason": reason,
                    "summary": detail[:500] or "auto handoff to reviewer (no HANDOFF block)",
                }

        if handoff and target:
            await self.store.add_handoff(
                task_id=task_id,
                from_agent=from_agent or "unknown",
                to_agent=target,
                reason=reason or handoff.get("reason"),
                worktree_path=handoff.get("worktree_path"),
                branch=handoff.get("branch"),
                summary=handoff.get("summary"),
                open_questions=handoff.get("open_questions"),
                artifacts=handoff.get("artifacts") if isinstance(handoff.get("artifacts"), list) else [],
                token_spent=handoff.get("token_spent") or tokens or None,
            )

        if target and target != from_agent:
            new_state = "REVIEW" if target == "reviewer" else "ASSIGNED"
            # Re-enqueue to the target role stream
            envelope_raw = fields.get(b"envelope") or fields.get("envelope")
            try:
                task = json.loads(_s(envelope_raw)) if envelope_raw else {"task_id": task_id}
            except (TypeError, ValueError):
                task = {"task_id": task_id, "trace_id": trace_id}
            task["assigned_to"] = target
            task["state"] = new_state
            if handoff:
                task.setdefault("handoffs", []).append(handoff)
            if target == "reviewer" and not task.get("skill"):
                task["skill"] = "review-with-socraticode"

            if await self.control.is_paused(target):
                log.info("paused — holding handoff %s → %s", task_id, target)
                # leave un-acked
                return

            await self.redis.xadd(
                self.s.role_stream(target),
                {
                    "task_id": task_id,
                    "trace_id": trace_id or "",
                    "type": task.get("type") or "review",
                    "project": task.get("project") or _s(fields.get(b"project") or fields.get("project") or ""),
                    "assigned_to": target,
                    "state": new_state,
                    "envelope": json.dumps(task, default=str),
                },
                maxlen=self.s.stream_maxlen,
                approximate=True,
            )
            await self.store.set_state(task_id, new_state, assigned_to=target)
            await self.store.audit(
                actor=ACTOR,
                event="task.handed_off",
                trace_id=trace_id,
                task_id=task_id,
                attrs={"from": from_agent, "to": target, "reason": reason},
            )
            metrics.inc("emaw_tasks_routed_total")
        else:
            final = "DONE"
            if reason in {"needs_human", "needing_human"}:
                final = "NEEDS_HUMAN"
            await self.store.set_state(
                task_id,
                final,
                result={"from_agent": from_agent, "detail": detail[:500], "handoff": handoff},
            )
            await self.store.audit(
                actor=ACTOR,
                event="task.done" if final == "DONE" else "task.needs_human",
                trace_id=trace_id,
                task_id=task_id,
                attrs={"from_agent": from_agent, "detail": detail[:300]},
            )

        await self.redis.xack(self.s.results_stream, self.results_group, message_id)
        self.processed += 1
