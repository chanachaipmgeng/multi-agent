"""Redis Streams publisher.

The gateway publishes every actionable task to a single inbox stream consumed by
the coordinator (``stream:tasks`` by default). Per-role streams
(``stream:dev-frontend`` …) are written by the coordinator after routing — the
gateway only *proposes* ``assigned_to``.
"""

from __future__ import annotations

from redis.asyncio import Redis

from .envelope import Task


class TaskPublisher:
    def __init__(self, redis: Redis, *, stream: str, maxlen: int) -> None:
        self._redis = redis
        self.stream = stream
        self._maxlen = maxlen

    async def publish(self, task: Task) -> str:
        fields = {
            "task_id": task.task_id,
            "trace_id": task.trace_id,
            "type": task.type,
            "project": task.project,
            "assigned_to": task.assigned_to or "",
            "state": task.state.value,
            "envelope": task.model_dump_json(),
        }
        message_id = await self._redis.xadd(
            self.stream, fields, maxlen=self._maxlen, approximate=True
        )
        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)
