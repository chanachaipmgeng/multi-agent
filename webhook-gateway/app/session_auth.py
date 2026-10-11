"""Browser session auth for Operator Console (DECISION-21).

Service callers keep using ``Authorization: Bearer <HERMES_API_KEY>`` +
``X-EMAW-User-Id``. The SPA uses a Redis-backed cookie session instead.
"""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, Response
from redis.asyncio import Redis

log = logging.getLogger("emaw.gateway.session")

COOKIE_NAME = "emaw_session"
CSRF_HEADER = "X-CSRF-Token"
SESSION_KEY_PREFIX = "emaw:session:"
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(slots=True)
class ConsoleSession:
    user_id: int
    csrf: str


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


async def create_session(
    redis: Redis,
    *,
    user_id: int,
    ttl_seconds: int,
) -> tuple[str, ConsoleSession]:
    session_id = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": user_id, "csrf": csrf})
    await redis.set(_session_key(session_id), payload, ex=ttl_seconds)
    return session_id, ConsoleSession(user_id=user_id, csrf=csrf)


async def load_session(redis: Redis, session_id: str | None) -> ConsoleSession | None:
    if not session_id:
        return None
    raw = await redis.get(_session_key(session_id))
    if not raw:
        return None
    try:
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return ConsoleSession(user_id=int(data["user_id"]), csrf=str(data["csrf"]))
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        log.warning("corrupt session payload for id prefix %s", session_id[:8])
        return None


async def destroy_session(redis: Redis, session_id: str | None) -> None:
    if session_id:
        await redis.delete(_session_key(session_id))


def set_session_cookie(
    response: Response,
    *,
    session_id: str,
    ttl_seconds: int,
    secure: bool,
) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )


def clear_session_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=secure,
    )


def secrets_equal(stored: str, provided: str) -> bool:
    try:
        return secrets.compare_digest(stored, provided)
    except (TypeError, ValueError):
        return False


async def resolve_actor(
    request: Request,
    authorization: str | None,
    x_emaw_user_id: str | None,
    *,
    require_hermes_bearer,
    parse_user_id,
) -> int:
    """Return the acting Telegram/RBAC user id.

    Prefers a valid console session cookie (DECISION-21). Falls back to Hermes
    bearer + ``X-EMAW-User-Id`` for service callers.
    """
    redis: Redis = request.app.state.redis
    settings = request.app.state.settings
    sid = request.cookies.get(COOKIE_NAME)
    session = await load_session(redis, sid)
    if session is not None:
        if request.method in MUTATING:
            csrf = request.headers.get(CSRF_HEADER) or request.headers.get("x-csrf-token")
            if not csrf or not secrets_equal(session.csrf, csrf):
                raise HTTPException(403, detail="csrf_invalid")
        return session.user_id

    require_hermes_bearer(request, authorization)
    return parse_user_id(x_emaw_user_id)


def session_public(user_id: int, name: str, roles: list[str], csrf: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "name": name,
        "roles": roles,
        "csrf": csrf,
    }
