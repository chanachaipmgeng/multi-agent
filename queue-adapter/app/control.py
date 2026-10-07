"""Kill-switch / safe-mode Redis keys (design §6.6, E11)."""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis

DEFAULT_CONTROL_PREFIX = "emaw:control"


def pause_key(prefix: str, agent: str) -> str:
    return f"{prefix}:pause:{agent}"


def safe_mode_key(prefix: str) -> str:
    return f"{prefix}:safe_mode"


class ControlPlane:
    """Read/write pause and safe-mode flags used by the router and worker adapters."""

    def __init__(self, redis: Redis, *, prefix: str = DEFAULT_CONTROL_PREFIX) -> None:
        self.redis = redis
        self.prefix = prefix

    async def is_paused(self, agent: str) -> bool:
        """True if ``agent`` or ``all`` is paused."""
        all_paused = await self.redis.get(pause_key(self.prefix, "all"))
        if all_paused:
            return True
        specific = await self.redis.get(pause_key(self.prefix, agent))
        return bool(specific)

    async def is_safe_mode(self) -> bool:
        return bool(await self.redis.get(safe_mode_key(self.prefix)))

    async def pause(self, agent: str = "all") -> None:
        await self.redis.set(pause_key(self.prefix, agent), "1")

    async def resume(self, agent: str = "all") -> None:
        if agent == "all":
            # Clear the global flag; per-agent flags stay until explicitly resumed.
            await self.redis.delete(pause_key(self.prefix, "all"))
        else:
            await self.redis.delete(pause_key(self.prefix, agent))

    async def set_safe_mode(self, enabled: bool) -> None:
        key = safe_mode_key(self.prefix)
        if enabled:
            await self.redis.set(key, "1")
        else:
            await self.redis.delete(key)

    async def status(self) -> dict[str, Any]:
        return {
            "safe_mode": await self.is_safe_mode(),
            "pause_all": bool(await self.redis.get(pause_key(self.prefix, "all"))),
        }
