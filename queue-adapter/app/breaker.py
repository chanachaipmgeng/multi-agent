"""Circuit breaker: auto safe-mode on failure / token budget (design §6.6, E9/E11)."""

from __future__ import annotations

import logging
import time
from typing import Any

from redis.asyncio import Redis

from .control import ControlPlane

log = logging.getLogger("emaw.adapter.breaker")

FAILED_ZSET = "emaw:metrics:failed"
TOKENS_ZSET_PREFIX = "emaw:metrics:tokens:"  # + agent name


class CircuitBreaker:
    def __init__(
        self,
        redis: Redis,
        control: ControlPlane,
        *,
        fail_threshold: int = 3,
        fail_window_seconds: int = 900,  # 15 min
        token_budget_per_agent_hour: int = 500_000,
        on_trip: Any | None = None,
    ) -> None:
        self.redis = redis
        self.control = control
        self.fail_threshold = fail_threshold
        self.fail_window = fail_window_seconds
        self.token_budget = token_budget_per_agent_hour
        self.on_trip = on_trip  # optional async callable(reason: str)

    async def record_failure(self, task_id: str) -> None:
        now = time.time()
        await self.redis.zadd(FAILED_ZSET, {f"{task_id}:{now}": now})
        cutoff = now - self.fail_window
        await self.redis.zremrangebyscore(FAILED_ZSET, 0, cutoff)
        count = await self.redis.zcard(FAILED_ZSET)
        if count > self.fail_threshold:
            await self._trip(f"tasks_failed_total={count} in {self.fail_window // 60}m")

    async def record_tokens(self, agent: str, tokens: int) -> None:
        if tokens <= 0:
            return
        now = time.time()
        key = f"{TOKENS_ZSET_PREFIX}{agent}"
        member = f"{tokens}:{now}"
        await self.redis.zadd(key, {member: now})
        cutoff = now - 3600
        await self.redis.zremrangebyscore(key, 0, cutoff)
        # Sum token amounts encoded in member keys
        members = await self.redis.zrangebyscore(key, cutoff, "+inf")
        total = 0
        for m in members:
            text = m.decode() if isinstance(m, bytes) else str(m)
            try:
                total += int(text.split(":", 1)[0])
            except ValueError:
                continue
        if total > self.token_budget:
            await self._trip(
                f"token_budget_exceeded agent={agent} tokens={total} "
                f"budget={self.token_budget}/h"
            )

    async def _trip(self, reason: str) -> None:
        already = await self.control.is_safe_mode()
        await self.control.set_safe_mode(True)
        log.warning("circuit breaker OPEN: %s", reason)
        if not already and self.on_trip is not None:
            await self.on_trip(reason)
