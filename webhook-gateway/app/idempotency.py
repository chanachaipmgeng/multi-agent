"""Replay / duplicate protection keyed on ``X-Gitlab-Event-UUID`` (design §5.3)."""

from __future__ import annotations

from redis.asyncio import Redis


class IdempotencyStore:
    def __init__(self, redis: Redis, *, prefix: str, ttl_seconds: int) -> None:
        self._redis = redis
        self._prefix = prefix
        self._ttl = ttl_seconds

    def key(self, event_uuid: str) -> str:
        return f"{self._prefix}{event_uuid}"

    async def claim(self, event_uuid: str) -> bool:
        """Atomically claim an event UUID.

        Returns ``True`` the first time an event is seen and ``False`` for any
        replay inside the TTL window. ``SET NX EX`` makes the check-and-set atomic
        even with several gateway replicas.
        """
        result = await self._redis.set(self.key(event_uuid), "1", nx=True, ex=self._ttl)
        return bool(result)

    async def release(self, event_uuid: str) -> None:
        """Undo a claim (used when enqueueing fails so GitLab's retry is not treated as a dup)."""
        await self._redis.delete(self.key(event_uuid))
