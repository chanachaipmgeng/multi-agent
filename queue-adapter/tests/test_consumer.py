"""Consumer behaviour: ack on success, retry via XAUTOCLAIM, dead-letter after max deliveries."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.consumer import Consumer
from app.dispatch import (
    DryRunDispatcher,
    HermesApiDispatcher,
    HermesCliDispatcher,
    HttpDispatcher,
)

from .conftest import FailingDispatcher, enqueue, make_job_failed_task, make_task


async def _pending(redis, settings):
    return await redis.xpending_range(settings.task_stream, settings.consumer_group, "-", "+", 10)


async def test_issue_task_is_dispatched_acked_and_recorded(
    consumer, fake_redis, settings, store, telegram_calls
) -> None:
    await consumer.ensure_group()
    task = make_task()
    await enqueue(fake_redis, settings, task)

    handled = await consumer.run_once(block_ms=1)

    assert handled == 1
    assert await _pending(fake_redis, settings) == []  # acked
    assert store.states[task["task_id"]] == {"state": "IN_PROGRESS", "assigned_to": "hermes-single"}
    assert [e["event"] for e in store.audit_events] == ["task.assigned", "task.dispatched"]
    results = await fake_redis.xrange(settings.results_stream)
    assert len(results) == 1 and results[0][1][b"status"] == b"completed"
    assert results[0][1][b"from_agent"] == b"hermes-single"
    outbox = list(Path(settings.outbox_dir).glob("*.prompt.md"))
    assert len(outbox) == 1 and "run skill resolve-issue" in outbox[0].read_text(encoding="utf-8")
    assert telegram_calls and "รับงาน t-20261007-abc123" in telegram_calls[0]["text"]
    assert Path(settings.heartbeat_file).exists()
    assert await fake_redis.get(settings.heartbeat_key) is not None


async def test_backlog_before_group_creation_is_drained(consumer, fake_redis, settings) -> None:
    await enqueue(fake_redis, settings, make_task(task_id="t-1"))
    await enqueue(fake_redis, settings, make_task(task_id="t-2"))
    await consumer.ensure_group()  # id="0" → sees the backlog
    assert await consumer.run_once(block_ms=1) == 2
    assert consumer.processed == 2


async def test_job_failed_task_gets_trace_in_prompt(consumer, fake_redis, settings) -> None:
    await consumer.ensure_group()
    await enqueue(fake_redis, settings, make_job_failed_task())
    await consumer.run_once(block_ms=1)
    prompt = next(Path(settings.outbox_dir).glob("*.prompt.md")).read_text(encoding="utf-8")
    assert "run skill incident-triage" in prompt
    assert "JOB TRACE (redacted, tail)" in prompt
    assert "SuperSecretValue" not in prompt
    assert "HANDOFF:" in prompt


async def test_retryable_failure_stays_pending_then_dead_letters(
    settings, fake_redis, store, gitlab, notifier, telegram_calls
) -> None:
    dispatcher = FailingDispatcher(retryable=True)
    consumer = Consumer(
        settings,
        redis=fake_redis,
        store=store,
        dispatcher=dispatcher,
        gitlab=gitlab,
        notifier=notifier,
    )
    await consumer.ensure_group()
    task = make_task()
    await enqueue(fake_redis, settings, task)

    # delivery 1 — fails, stays pending (not acked); worker marks IN_PROGRESS
    await consumer.run_once(block_ms=1)
    pending = await _pending(fake_redis, settings)
    assert len(pending) == 1 and pending[0]["times_delivered"] == 1
    assert store.states[task["task_id"]]["state"] == "IN_PROGRESS"
    assert any("ไม่สำเร็จ" in c["text"] for c in telegram_calls)

    # delivery 2 — re-claimed via XAUTOCLAIM (min idle 0 in tests), fails again
    await consumer.run_once(block_ms=1)
    pending = await _pending(fake_redis, settings)
    assert len(pending) == 1 and pending[0]["times_delivered"] == 2

    # delivery 3 — last allowed attempt fails → dead-letter + FAILED + acked
    await consumer.run_once(block_ms=1)
    assert await _pending(fake_redis, settings) == []
    dead = await fake_redis.xrange(settings.dead_letter_stream)
    assert len(dead) == 1
    assert json.loads(dead[0][1][b"envelope"])["task_id"] == task["task_id"]
    assert store.states[task["task_id"]]["state"] == "FAILED"
    assert dispatcher.calls == 3
    events = [e["event"] for e in store.audit_events]
    assert events.count("task.dispatch_failed") == 3 and events[-1] == "task.failed"
    assert any("dead-letter" in c["text"] for c in telegram_calls)


async def test_non_retryable_failure_dead_letters_immediately(
    settings, fake_redis, store, gitlab, notifier
) -> None:
    dispatcher = FailingDispatcher(retryable=False)
    consumer = Consumer(
        settings,
        redis=fake_redis,
        store=store,
        dispatcher=dispatcher,
        gitlab=gitlab,
        notifier=notifier,
    )
    await consumer.ensure_group()
    await enqueue(fake_redis, settings, make_task())
    await consumer.run_once(block_ms=1)
    assert dispatcher.calls == 1
    assert await _pending(fake_redis, settings) == []
    assert len(await fake_redis.xrange(settings.dead_letter_stream)) == 1


async def test_invalid_envelope_is_dead_lettered(consumer, fake_redis, settings) -> None:
    await consumer.ensure_group()
    await fake_redis.xadd(settings.task_stream, {"envelope": "{not json"})
    await consumer.run_once(block_ms=1)
    assert await _pending(fake_redis, settings) == []
    dead = await fake_redis.xrange(settings.dead_letter_stream)
    assert dead[0][1][b"reason"] == b"invalid envelope"


async def test_ensure_group_is_idempotent(consumer) -> None:
    await consumer.ensure_group()
    await consumer.ensure_group()


# ------------------------------------------------------------ dispatchers
async def test_http_dispatcher_posts_task_and_prompt() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(202)

    d = HttpDispatcher(
        "http://hermes:8642/webhook/task",
        token="shim-token",
        transport=httpx.MockTransport(handler),
    )
    result = await d.dispatch(make_task(), "PROMPT")
    assert result.ok and result.detail == "HTTP 202"
    assert seen["auth"] == "Bearer shim-token"
    assert (
        seen["body"]["task"]["task_id"] == "t-20261007-abc123"
        and seen["body"]["prompt"] == "PROMPT"
    )
    await d.aclose()


async def test_http_dispatcher_4xx_is_not_retryable_5xx_is() -> None:
    d4 = HttpDispatcher(
        "http://x/", transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad"))
    )
    d5 = HttpDispatcher(
        "http://x/", transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down"))
    )
    r4, r5 = await d4.dispatch(make_task(), "p"), await d5.dispatch(make_task(), "p")
    assert not r4.ok and r4.retryable is False
    assert not r5.ok and r5.retryable is True


def test_hermes_cli_command_template_rendering(tmp_path) -> None:
    d = HermesCliDispatcher(
        "hermes -p {agent} chat --oneshot -Q --query-file {prompt_file} -s {skill}",
        outbox_dir=str(tmp_path),
    )
    cmd = d.build_command(make_task(), "p", tmp_path / "t.prompt.md")
    assert cmd == [
        "hermes",
        "-p",
        "dev-frontend",
        "chat",
        "--oneshot",
        "-Q",
        "--query-file",
        str(tmp_path / "t.prompt.md"),
        "-s",
        "resolve-issue",
    ]


async def test_hermes_api_dispatcher_create_and_poll_completed() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.method == "POST" and request.url.path.endswith("/v1/runs"):
            assert request.headers.get("Idempotency-Key") == "t-20261007-abc123"
            assert request.headers.get("Authorization") == "Bearer api-key"
            return httpx.Response(202, json={"run_id": "run_abc", "status": "queued"})
        if request.method == "GET" and request.url.path.endswith("/v1/runs/run_abc"):
            return httpx.Response(200, json={"run_id": "run_abc", "status": "completed"})
        return httpx.Response(404)

    d = HermesApiDispatcher(
        "http://hermes:8642",
        token="api-key",
        poll_interval_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )
    result = await d.dispatch(make_task(), "PROMPT")
    assert result.ok
    assert "run_id=run_abc" in result.detail
    assert "status=completed" in result.detail
    assert any(c.startswith("POST ") for c in calls)
    assert any(c.startswith("GET ") for c in calls)
    await d.aclose()


async def test_hermes_api_dispatcher_waiting_for_approval_is_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json={"run_id": "run_wait"})
        return httpx.Response(200, json={"run_id": "run_wait", "status": "waiting_for_approval"})

    d = HermesApiDispatcher(
        "http://hermes:8642/",
        poll_interval_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )
    result = await d.dispatch(make_task(), "PROMPT")
    assert result.ok and "waiting_for_approval" in result.detail
    await d.aclose()


async def test_hermes_api_dispatcher_failed_run_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json={"run_id": "run_fail"})
        return httpx.Response(
            200, json={"run_id": "run_fail", "status": "failed", "error": "boom"}
        )

    d = HermesApiDispatcher(
        "http://hermes:8642",
        poll_interval_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )
    result = await d.dispatch(make_task(), "PROMPT")
    assert not result.ok and result.retryable is True
    assert "boom" in result.detail
    await d.aclose()


async def test_hermes_cli_missing_binary_is_not_retryable(tmp_path) -> None:
    d = HermesCliDispatcher(
        "definitely-not-a-real-binary-xyz {prompt_file}", outbox_dir=str(tmp_path)
    )
    result = await d.dispatch(make_task(), "p")
    assert not result.ok and result.retryable is False


async def test_hermes_cli_runs_real_command(tmp_path) -> None:
    # Cross-platform: python reads the prompt file (cat is unavailable on Windows).
    d = HermesCliDispatcher(
        "python -c \"import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\" {prompt_file}",
        outbox_dir=str(tmp_path),
    )
    result = await d.dispatch(make_task(), "hello from prompt")
    assert result.ok and "hello from prompt" in result.detail


async def test_dryrun_writes_file(tmp_path) -> None:
    d = DryRunDispatcher(str(tmp_path / "out"))
    result = await d.dispatch(make_task(), "x")
    assert result.ok and Path(result.detail).read_text(encoding="utf-8") == "x"
