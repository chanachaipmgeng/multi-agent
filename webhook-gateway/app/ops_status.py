"""Ops health / queue / DLQ helpers for Operator Console (roadmap W4)."""

from __future__ import annotations

import json
import time
from typing import Any

from redis.asyncio import Redis

HEARTBEAT_STALE_SECONDS = 180
DEAD_LETTER_STREAM = "stream:dead-letter"
TASK_STREAM = "stream:tasks"

# (stream, consumer_group or None if no group / pending N/A)
QUEUE_STREAMS: tuple[tuple[str, str | None], ...] = (
    (TASK_STREAM, "router"),
    ("stream:results", "router-results"),
    (DEAD_LETTER_STREAM, None),
    ("stream:dev-frontend", "adapter-dev-frontend"),
    ("stream:dev-backend", "adapter-dev-backend"),
    ("stream:reviewer", "adapter-reviewer"),
    ("stream:qa", "adapter-qa"),
    ("stream:devops", "adapter-devops"),
)

# Expected heartbeat keys written by router / worker adapters
EXPECTED_HEARTBEATS: tuple[tuple[str, str], ...] = (
    ("router", "emaw:heartbeat:router"),
    ("adapter-dev-frontend", "emaw:heartbeat:adapter-dev-frontend"),
    ("adapter-dev-backend", "emaw:heartbeat:adapter-dev-backend"),
    ("adapter-reviewer", "emaw:heartbeat:adapter-reviewer"),
    ("adapter-qa", "emaw:heartbeat:adapter-qa"),
    ("adapter-devops", "emaw:heartbeat:adapter-devops"),
)


def _s(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _field_map(fields: dict[Any, Any]) -> dict[str, str]:
    return {_s(k): _s(v) for k, v in fields.items()}


async def collect_health(redis: Redis, *, store_ok: bool) -> dict[str, Any]:
    redis_ok = False
    try:
        redis_ok = bool(await redis.ping())
    except Exception:  # noqa: BLE001
        redis_ok = False

    now = time.time()
    heartbeats: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    if redis_ok:
        for name, key in EXPECTED_HEARTBEATS:
            seen_keys.add(key)
            raw = await redis.get(key)
            if raw is None:
                heartbeats.append(
                    {
                        "name": name,
                        "key": key,
                        "ts": None,
                        "age_seconds": None,
                        "stale": True,
                        "missing": True,
                    }
                )
                continue
            try:
                ts = float(_s(raw))
            except ValueError:
                heartbeats.append(
                    {
                        "name": name,
                        "key": key,
                        "ts": None,
                        "age_seconds": None,
                        "stale": True,
                        "missing": False,
                    }
                )
                continue
            age = max(0.0, now - ts)
            heartbeats.append(
                {
                    "name": name,
                    "key": key,
                    "ts": ts,
                    "age_seconds": round(age, 1),
                    "stale": age > HEARTBEAT_STALE_SECONDS,
                    "missing": False,
                }
            )

        try:
            async for key in redis.scan_iter(match="emaw:heartbeat:*", count=50):
                k = _s(key)
                if k in seen_keys:
                    continue
                raw = await redis.get(key)
                if raw is None:
                    continue
                name = k.rsplit(":", 1)[-1]
                try:
                    ts = float(_s(raw))
                    age = max(0.0, now - ts)
                except ValueError:
                    continue
                heartbeats.append(
                    {
                        "name": name,
                        "key": k,
                        "ts": ts,
                        "age_seconds": round(age, 1),
                        "stale": age > HEARTBEAT_STALE_SECONDS,
                        "missing": False,
                        "extra": True,
                    }
                )
        except Exception:  # noqa: BLE001
            pass

    stale_count = sum(1 for h in heartbeats if h.get("stale"))
    return {
        "redis_ok": redis_ok,
        "store_ok": store_ok,
        "heartbeat_stale_after_seconds": HEARTBEAT_STALE_SECONDS,
        "heartbeats": heartbeats,
        "stale_count": stale_count,
        "ok": redis_ok and store_ok and stale_count == 0 and len(heartbeats) > 0,
    }


async def _pending_count(redis: Redis, stream: str, group: str | None) -> int | None:
    if not group:
        return None
    try:
        summary = await redis.xpending(stream, group)
    except Exception:  # noqa: BLE001 — group may not exist yet
        return None
    if summary is None:
        return 0
    # redis-py: [min, max, count, consumers] or dict in some versions
    if isinstance(summary, dict):
        return int(summary.get("pending") or summary.get("count") or 0)
    if isinstance(summary, (list, tuple)) and len(summary) >= 3:
        try:
            return int(summary[2])
        except (TypeError, ValueError):
            return 0
    return 0


async def collect_queues(redis: Redis) -> dict[str, Any]:
    streams: list[dict[str, Any]] = []
    for stream, group in QUEUE_STREAMS:
        try:
            depth = int(await redis.xlen(stream))
        except Exception:  # noqa: BLE001
            depth = 0
        pending = await _pending_count(redis, stream, group)
        streams.append(
            {
                "stream": stream,
                "consumer_group": group,
                "length": depth,
                "pending": pending,
            }
        )
    return {"streams": streams, "count": len(streams)}


async def list_dead_letters(redis: Redis, *, limit: int = 50) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    try:
        entries = await redis.xrevrange(DEAD_LETTER_STREAM, count=limit)
    except Exception:  # noqa: BLE001
        entries = []
    rows: list[dict[str, Any]] = []
    for message_id, fields in entries or []:
        fm = _field_map(fields)
        envelope_raw = fm.get("envelope") or ""
        assigned = None
        project = None
        if envelope_raw:
            try:
                env = json.loads(envelope_raw)
                assigned = env.get("assigned_to")
                project = env.get("project")
            except (TypeError, ValueError, json.JSONDecodeError):
                env = None
        else:
            env = None
        preview = envelope_raw[:240] + ("…" if len(envelope_raw) > 240 else "")
        rows.append(
            {
                "id": _s(message_id),
                "task_id": fm.get("task_id") or "",
                "trace_id": fm.get("trace_id") or "",
                "reason": fm.get("reason") or "",
                "source_message_id": fm.get("source_message_id") or "",
                "assigned_to": assigned,
                "project": project,
                "envelope_preview": preview,
            }
        )
    return {"entries": rows, "count": len(rows)}


async def get_dead_letter(
    redis: Redis, message_id: str
) -> tuple[dict[str, str], str] | None:
    try:
        entries = await redis.xrange(DEAD_LETTER_STREAM, min=message_id, max=message_id, count=1)
    except Exception:  # noqa: BLE001
        return None
    if not entries:
        return None
    mid, fields = entries[0]
    return _field_map(fields), _s(mid)


async def retry_dead_letter(
    redis: Redis,
    message_id: str,
    *,
    task_stream: str = TASK_STREAM,
    maxlen: int = 10_000,
) -> dict[str, Any]:
    got = await get_dead_letter(redis, message_id)
    if got is None:
        raise KeyError("dead_letter_not_found")
    fields, _mid = got
    envelope_raw = fields.get("envelope") or ""
    if not envelope_raw:
        raise ValueError("dead_letter_missing_envelope")
    try:
        task = json.loads(envelope_raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("dead_letter_invalid_envelope") from exc

    task_id = str(task.get("task_id") or fields.get("task_id") or "?")
    out_fields = {
        "task_id": task_id,
        "trace_id": str(task.get("trace_id") or fields.get("trace_id") or ""),
        "type": str(task.get("type") or ""),
        "project": str(task.get("project") or ""),
        "assigned_to": str(task.get("assigned_to") or ""),
        "state": "QUEUED",
        "envelope": envelope_raw,
    }
    new_id = await redis.xadd(task_stream, out_fields, maxlen=maxlen, approximate=True)
    await redis.xdel(DEAD_LETTER_STREAM, message_id)
    return {
        "task_id": task_id,
        "trace_id": out_fields["trace_id"],
        "stream_id": _s(new_id),
        "dead_letter_id": message_id,
    }


async def discard_dead_letter(redis: Redis, message_id: str) -> dict[str, Any]:
    got = await get_dead_letter(redis, message_id)
    if got is None:
        raise KeyError("dead_letter_not_found")
    fields, _mid = got
    deleted = await redis.xdel(DEAD_LETTER_STREAM, message_id)
    return {
        "dead_letter_id": message_id,
        "task_id": fields.get("task_id") or "",
        "trace_id": fields.get("trace_id") or "",
        "deleted": int(deleted),
    }
