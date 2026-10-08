"""Entry point: ``python -m app.main``."""

from __future__ import annotations

import asyncio
import logging
import signal

from redis.asyncio import Redis

from . import __version__
from .artifacts import build_artifact_store
from .breaker import CircuitBreaker
from .consumer import Consumer
from .control import ControlPlane
from .dispatch import build_dispatcher
from .metrics import start_metrics_server
from .notify import TelegramNotifier
from .projects import ProjectRegistry
from .router import Router
from .scm import build_scm_router
from .settings import Settings
from .store import build_store

log = logging.getLogger("emaw.adapter")


async def _serve_worker(settings: Settings) -> None:
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_timeout=settings.block_ms / 1000 + 10,
        socket_connect_timeout=5,
        health_check_interval=30,
    )
    store = build_store(settings.database_url)
    dispatcher = build_dispatcher(settings)
    registry = None
    if settings.projects_file:
        registry = ProjectRegistry.from_yaml(settings.projects_file)
    scm = build_scm_router(settings, registry=registry)
    notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id)
    control = ControlPlane(redis, prefix=settings.control_prefix)

    async def on_trip(reason: str) -> None:
        await store.audit(
            actor="circuit-breaker",
            event="control.circuit_open",
            trace_id=None,
            task_id=None,
            attrs={"reason": reason},
        )
        await notifier.send(f"⚠️ Circuit breaker OPEN — safe-mode enabled.\n{reason}")

    breaker = CircuitBreaker(
        redis,
        control,
        fail_threshold=settings.fail_threshold,
        fail_window_seconds=settings.fail_window_seconds,
        token_budget_per_agent_hour=settings.token_budget_per_agent_hour,
        on_trip=on_trip,
    )
    artifacts = build_artifact_store(settings)
    consumer = Consumer(
        settings,
        redis=redis,
        store=store,
        dispatcher=dispatcher,
        scm=scm,
        notifier=notifier,
        control=control,
        breaker=breaker,
        artifacts=artifacts,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # Windows
            pass

    metrics_server = start_metrics_server(
        settings.metrics_port, role=settings.role, mode=settings.mode
    )
    await store.connect()
    log.info(
        "queue-adapter %s worker starting (role=%s, stream=%s, dispatcher=%s)",
        __version__,
        settings.role,
        settings.task_stream,
        dispatcher.name,
    )
    try:
        await consumer.ensure_group()
        while not stop.is_set():
            try:
                await consumer.run_once()
            except Exception:  # noqa: BLE001
                log.exception("consumer iteration failed; backing off 5s")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except TimeoutError:
                    pass
    finally:
        if metrics_server is not None:
            metrics_server.shutdown()
        await dispatcher.aclose()
        await scm.aclose()
        await notifier.aclose()
        await artifacts.aclose()
        await store.close()
        await redis.aclose()
        log.info("queue-adapter worker stopped after %d tasks", consumer.processed)


async def _serve_router(settings: Settings) -> None:
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_timeout=settings.block_ms / 1000 + 10,
        socket_connect_timeout=5,
        health_check_interval=30,
    )
    store = build_store(settings.database_url)
    notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id)
    control = ControlPlane(redis, prefix=settings.control_prefix)

    async def on_trip(reason: str) -> None:
        await store.audit(
            actor="circuit-breaker",
            event="control.circuit_open",
            trace_id=None,
            task_id=None,
            attrs={"reason": reason},
        )
        await notifier.send(f"⚠️ Circuit breaker OPEN — safe-mode enabled.\n{reason}")

    breaker = CircuitBreaker(
        redis,
        control,
        fail_threshold=settings.fail_threshold,
        fail_window_seconds=settings.fail_window_seconds,
        token_budget_per_agent_hour=settings.token_budget_per_agent_hour,
        on_trip=on_trip,
    )
    registry = None
    if settings.projects_file:
        registry = ProjectRegistry.from_yaml(settings.projects_file)

    router = Router(
        settings,
        redis=redis,
        store=store,
        control=control,
        breaker=breaker,
        notifier=notifier,
        registry=registry,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    metrics_server = start_metrics_server(
        settings.metrics_port, role="router", mode="router"
    )
    await store.connect()
    log.info(
        "queue-adapter %s router starting (task_stream=%s, results=%s)",
        __version__,
        settings.task_stream,
        settings.results_stream,
    )
    try:
        await router.ensure_groups()
        while not stop.is_set():
            try:
                await router.run_once()
            except Exception:  # noqa: BLE001
                log.exception("router iteration failed; backing off 5s")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except TimeoutError:
                    pass
    finally:
        if metrics_server is not None:
            metrics_server.shutdown()
        await notifier.aclose()
        await store.close()
        await redis.aclose()
        log.info("queue-adapter router stopped after %d messages", router.processed)


async def serve(settings: Settings) -> None:
    if settings.mode == "router":
        await _serve_router(settings)
    else:
        await _serve_worker(settings)


def run() -> None:  # pragma: no cover
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(serve(settings))


if __name__ == "__main__":  # pragma: no cover
    run()
