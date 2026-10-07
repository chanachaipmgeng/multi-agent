"""Redis Streams consumer: ``XREADGROUP`` → enrich → prompt → dispatch → ``XACK``.

Failure handling follows design §10.3: a message that is not acknowledged is re-claimed
with ``XAUTOCLAIM`` after ``claim_min_idle_ms``; after ``max_deliveries`` attempts it goes to
the dead-letter stream and the task becomes ``FAILED``.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from .dispatch import Dispatcher, dumps
from .gitlab import GitLabClient
from .notify import (
    TelegramNotifier,
    dead_letter_text,
    dispatch_failed_text,
    task_received_text,
)
from .prompt import build_prompt
from .settings import Settings
from .store import StateStore

log = logging.getLogger("emaw.adapter.consumer")

ACTOR = "queue-adapter"


def _s(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class Consumer:
    def __init__(
        self,
        settings: Settings,
        *,
        redis: Redis,
        store: StateStore,
        dispatcher: Dispatcher,
        gitlab: GitLabClient,
        notifier: TelegramNotifier,
    ) -> None:
        self.s = settings
        self.redis = redis
        self.store = store
        self.dispatcher = dispatcher
        self.gitlab = gitlab
        self.notifier = notifier
        self.processed = 0

    # ----------------------------------------------------------------- setup
    async def ensure_group(self) -> None:
        try:
            # id="0" so a freshly created group also drains any backlog the gateway produced
            await self.redis.xgroup_create(
                self.s.task_stream, self.s.consumer_group, id="0", mkstream=True
            )
            log.info("created consumer group %s on %s", self.s.consumer_group, self.s.task_stream)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def heartbeat(self) -> None:
        await self.redis.set(self.s.heartbeat_key, str(int(time.time())), ex=180)
        Path(self.s.heartbeat_file).write_text(str(int(time.time())), encoding="utf-8")

    # ------------------------------------------------------------------ loop
    async def run_once(self, *, block_ms: int | None = None) -> int:
        """Claim stale messages, then read new ones. Returns the number handled."""
        handled = 0
        handled += await self._claim_stale()
        entries = await self.redis.xreadgroup(
            self.s.consumer_group,
            self.s.consumer_name,
            {self.s.task_stream: ">"},
            count=10,
            block=self.s.block_ms if block_ms is None else block_ms,
        )
        for _stream, messages in entries or []:
            for message_id, fields in messages:
                await self.handle(_s(message_id), fields)
                handled += 1
        await self.heartbeat()
        return handled

    async def _claim_stale(self) -> int:
        _next, messages, _deleted = await self.redis.xautoclaim(
            self.s.task_stream,
            self.s.consumer_group,
            self.s.consumer_name,
            min_idle_time=self.s.claim_min_idle_ms,
            start_id="0-0",
            count=10,
        )
        for message_id, fields in messages:
            await self.handle(_s(message_id), fields)
        return len(messages)

    # ---------------------------------------------------------------- handle
    async def _deliveries(self, message_id: str) -> int:
        pending = await self.redis.xpending_range(
            self.s.task_stream, self.s.consumer_group, min=message_id, max=message_id, count=1
        )
        return int(pending[0]["times_delivered"]) if pending else 1

    async def handle(self, message_id: str, fields: dict[Any, Any]) -> None:
        raw = fields.get(b"envelope") or fields.get("envelope")
        try:
            task: dict[str, Any] = json.loads(_s(raw))
        except (TypeError, ValueError):
            log.error("message %s has no valid envelope; dead-lettering", message_id)
            await self._dead_letter(
                message_id, {"task_id": "?", "trace_id": None}, "invalid envelope"
            )
            return

        task_id = task.get("task_id", "?")
        trace_id = task.get("trace_id")
        deliveries = await self._deliveries(message_id)
        if deliveries > self.s.max_deliveries:
            await self._dead_letter(
                message_id, task, f"exceeded {self.s.max_deliveries} deliveries"
            )
            return

        if deliveries == 1:
            await self.store.set_state(task_id, "ASSIGNED", assigned_to=self.s.single_agent_name)
            await self.store.audit(
                actor=ACTOR,
                event="task.assigned",
                trace_id=trace_id,
                task_id=task_id,
                attrs={
                    "consumer": self.s.consumer_name,
                    "message_id": message_id,
                    "proposed_worker": task.get("assigned_to"),
                },
            )
            await self.notifier.send(task_received_text(task))

        enrichment: dict[str, Any] = {}
        try:
            enrichment = await self.gitlab.enrich(task)
        except Exception as exc:  # noqa: BLE001 — enrichment is best effort
            log.warning("enrichment failed for %s: %s", task_id, exc)
            await self.store.audit(
                actor=ACTOR,
                event="task.enrich_failed",
                trace_id=trace_id,
                task_id=task_id,
                attrs={"error": str(exc)[:300]},
            )

        prompt = build_prompt(task, enrichment)
        result = await self.dispatcher.dispatch(task, prompt)

        if result.ok:
            await self.store.set_state(task_id, "IN_PROGRESS")
            await self.store.audit(
                actor=ACTOR,
                event="task.dispatched",
                trace_id=trace_id,
                task_id=task_id,
                attrs={
                    "dispatcher": self.dispatcher.name,
                    "detail": result.detail[:300],
                    "deliveries": deliveries,
                    "prompt_chars": len(prompt),
                },
            )
            await self.redis.xadd(
                self.s.results_stream,
                {
                    "task_id": task_id,
                    "trace_id": trace_id or "",
                    "status": "dispatched",
                    "dispatcher": self.dispatcher.name,
                    "detail": result.detail[:500],
                },
            )
            await self.redis.xack(self.s.task_stream, self.s.consumer_group, message_id)
            self.processed += 1
            log.info(
                "dispatched %s via %s (delivery %d)", task_id, self.dispatcher.name, deliveries
            )
            return

        await self.store.audit(
            actor=ACTOR,
            event="task.dispatch_failed",
            trace_id=trace_id,
            task_id=task_id,
            attrs={
                "dispatcher": self.dispatcher.name,
                "detail": result.detail[:300],
                "deliveries": deliveries,
                "retryable": result.retryable,
            },
        )
        if not result.retryable or deliveries >= self.s.max_deliveries:
            await self._dead_letter(message_id, task, result.detail)
            return
        # leave un-acked: XAUTOCLAIM re-delivers after claim_min_idle_ms
        await self.notifier.send(
            dispatch_failed_text(task, result.detail, deliveries, self.s.max_deliveries)
        )
        log.warning(
            "dispatch of %s failed (delivery %d/%d): %s",
            task_id,
            deliveries,
            self.s.max_deliveries,
            result.detail[:200],
        )

    async def _dead_letter(self, message_id: str, task: dict[str, Any], reason: str) -> None:
        task_id = task.get("task_id", "?")
        await self.redis.xadd(
            self.s.dead_letter_stream,
            {
                "task_id": task_id,
                "trace_id": task.get("trace_id") or "",
                "reason": reason[:500],
                "envelope": dumps(task),
                "source_message_id": message_id,
            },
        )
        await self.redis.xack(self.s.task_stream, self.s.consumer_group, message_id)
        if task_id != "?":
            await self.store.set_state(task_id, "FAILED", result={"error": reason[:500]})
        await self.store.audit(
            actor=ACTOR,
            event="task.failed",
            trace_id=task.get("trace_id"),
            task_id=task_id,
            attrs={"reason": reason[:300], "dead_letter": True},
        )
        await self.notifier.send(dead_letter_text(task, reason))
        log.error("dead-lettered %s: %s", task_id, reason[:200])
