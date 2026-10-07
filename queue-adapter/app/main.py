"""Entry point: ``python -m app.main``."""

from __future__ import annotations

import asyncio
import logging
import signal

from redis.asyncio import Redis

from . import __version__
from .consumer import Consumer
from .dispatch import build_dispatcher
from .gitlab import GitLabClient
from .notify import TelegramNotifier
from .settings import Settings
from .store import build_store

log = logging.getLogger("emaw.adapter")


async def serve(settings: Settings) -> None:
    # redis-py >= 8 defaults socket_timeout to 5s, which equals BLOCK_MS and makes every idle
    # XREADGROUP raise TimeoutError. Give the socket more headroom than the blocking read.
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_timeout=settings.block_ms / 1000 + 10,
        socket_connect_timeout=5,
        health_check_interval=30,
    )
    store = build_store(settings.database_url)
    dispatcher = build_dispatcher(settings)
    gitlab = GitLabClient(
        settings.gitlab_base_url, settings.gitlab_token, trace_max_bytes=settings.trace_max_bytes
    )
    notifier = TelegramNotifier(settings.telegram_token, settings.telegram_chat_id)
    consumer = Consumer(
        settings, redis=redis, store=store, dispatcher=dispatcher, gitlab=gitlab, notifier=notifier
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await store.connect()
    log.info(
        "queue-adapter %s starting (dispatcher=%s, gitlab_enrichment=%s, telegram=%s)",
        __version__,
        dispatcher.name,
        gitlab.enabled,
        notifier.enabled,
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
        await dispatcher.aclose()
        await gitlab.aclose()
        await notifier.aclose()
        await store.close()
        await redis.aclose()
        log.info("queue-adapter stopped after %d tasks", consumer.processed)


def run() -> None:  # pragma: no cover
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(serve(settings))


if __name__ == "__main__":  # pragma: no cover
    run()
