"""Dispatchers: how a prompt reaches the Hermes agent.

Confirmed against Hermes Agent v0.21.5 (docs/hermes-capability-check.md, DECISION-1):

* ``DryRunDispatcher``    — writes the prompt to an outbox directory (CI/dev)
* ``HttpDispatcher``      — POSTs ``{task, prompt}`` to a shim URL (legacy/simple)
* ``HermesApiDispatcher`` — ``POST /v1/runs`` + poll (preferred for long tasks)
* ``HermesCliDispatcher`` — ``hermes -p … chat --oneshot -Q --query-file … -s …``
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx

from . import metrics

log = logging.getLogger("emaw.adapter.dispatch")

# Terminal statuses reported by Hermes /v1/runs (see API server docs).
_TERMINAL = frozenset({"completed", "failed", "cancelled", "error", "stopped"})
_WAITING = frozenset({"waiting_for_approval", "awaiting_approval"})


@dataclass(slots=True)
class DispatchResult:
    ok: bool
    detail: str = ""
    retryable: bool = True
    output: str = ""
    usage: dict[str, Any] | None = None
    run_id: str | None = None
    elapsed_seconds: float = 0.0


class Dispatcher(Protocol):
    name: str

    async def dispatch(self, task: dict[str, Any], prompt: str) -> DispatchResult: ...

    async def aclose(self) -> None: ...


class DryRunDispatcher:
    name = "dryrun"

    def __init__(self, outbox_dir: str) -> None:
        self._dir = Path(outbox_dir)

    async def dispatch(self, task: dict[str, Any], prompt: str) -> DispatchResult:
        self._dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        path = self._dir / f"{stamp}-{task['task_id']}.prompt.md"
        path.write_text(prompt, encoding="utf-8")
        log.info("dryrun: wrote prompt for %s to %s (%d chars)", task["task_id"], path, len(prompt))
        return DispatchResult(ok=True, detail=str(path))

    async def aclose(self) -> None:
        return None


class HttpDispatcher:
    name = "http"

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout, transport=transport)

    async def dispatch(self, task: dict[str, Any], prompt: str) -> DispatchResult:
        try:
            r = await self._client.post(self._url, json={"task": task, "prompt": prompt})
        except httpx.HTTPError as exc:
            return DispatchResult(ok=False, detail=f"http error: {exc}", retryable=True)
        if 200 <= r.status_code < 300:
            return DispatchResult(ok=True, detail=f"HTTP {r.status_code}")
        return DispatchResult(
            ok=False, detail=f"HTTP {r.status_code}: {r.text[:200]}", retryable=r.status_code >= 500
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class HermesApiDispatcher:
    """Preferred dispatcher: Hermes OpenAI-compatible API server on :8642.

    Creates a run with ``Idempotency-Key: <task_id>``, then polls ``GET /v1/runs/{id}``
    until a terminal status (or ``waiting_for_approval``, which we treat as success —
    the human gate continues outside the adapter).
    """

    name = "hermes_api"

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_seconds: int = 1_800,
        poll_interval_seconds: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/") + "/"
        self._timeout = timeout_seconds
        self._poll = poll_interval_seconds
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # Connect/read timeouts for individual HTTP calls; overall budget is self._timeout.
        self._client = httpx.AsyncClient(
            headers=headers, timeout=httpx.Timeout(60.0, connect=10.0), transport=transport
        )

    def _url(self, path: str) -> str:
        return urljoin(self._base, path.lstrip("/"))

    async def dispatch(self, task: dict[str, Any], prompt: str) -> DispatchResult:
        task_id = task["task_id"]
        skill = task.get("skill") or "dev-flow"
        body = {
            "input": prompt,
            "metadata": {
                "task_id": task_id,
                "trace_id": task.get("trace_id"),
                "skill": skill,
                "assigned_to": task.get("assigned_to"),
                "project": task.get("project"),
            },
        }
        # Hermes accepts OpenAI-style messages as well; prefer a simple prompt field + messages.
        body["messages"] = [{"role": "user", "content": prompt}]
        headers = {"Idempotency-Key": task_id[:255]}
        try:
            r = await self._client.post(self._url("/v1/runs"), json=body, headers=headers)
        except httpx.HTTPError as exc:
            return DispatchResult(ok=False, detail=f"create run http error: {exc}", retryable=True)

        if r.status_code == 409:
            return DispatchResult(
                ok=False,
                detail=f"idempotency conflict for {task_id}: {r.text[:200]}",
                retryable=False,
            )
        if not (200 <= r.status_code < 300):
            return DispatchResult(
                ok=False,
                detail=f"create run HTTP {r.status_code}: {r.text[:200]}",
                retryable=r.status_code >= 500,
            )

        try:
            payload = r.json()
        except ValueError:
            return DispatchResult(ok=False, detail="create run: non-JSON body", retryable=True)

        run_id = payload.get("run_id") or payload.get("id")
        if not run_id:
            return DispatchResult(
                ok=False, detail=f"create run missing run_id: {payload!r}"[:300], retryable=True
            )
        replayed = r.headers.get("Idempotency-Replayed", "").lower() == "true"
        log.info(
            "hermes_api: created run %s for %s (replayed=%s)", run_id, task_id, replayed
        )
        started = time.monotonic()
        result = await self._poll_until_done(run_id, task_id)
        result.elapsed_seconds = time.monotonic() - started
        result.run_id = str(run_id)
        return result

    @staticmethod
    def _extract_output(data: dict[str, Any]) -> str:
        for key in ("output", "result", "response", "message"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
            if isinstance(val, dict):
                for nested in ("content", "text", "output"):
                    if isinstance(val.get(nested), str) and val[nested].strip():
                        return val[nested]
        messages = data.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                content = last.get("content")
                if isinstance(content, str):
                    return content
        return ""

    @staticmethod
    def _extract_usage(data: dict[str, Any]) -> dict[str, Any] | None:
        usage = data.get("usage") or data.get("token_usage")
        if not isinstance(usage, dict):
            return None
        # Promote top-level model onto usage so consumer can label llm_tokens_total.
        out = dict(usage)
        if "model" not in out and data.get("model"):
            out["model"] = data["model"]
        return out

    async def _poll_until_done(self, run_id: str, task_id: str) -> DispatchResult:
        deadline = time.monotonic() + self._timeout
        last_status = "unknown"
        while time.monotonic() < deadline:
            try:
                r = await self._client.get(self._url(f"/v1/runs/{run_id}"))
            except httpx.HTTPError as exc:
                log.warning("hermes_api: poll error for %s: %s", run_id, exc)
                await asyncio.sleep(self._poll)
                continue
            if r.status_code >= 500:
                await asyncio.sleep(self._poll)
                continue
            if r.status_code == 404:
                return DispatchResult(
                    ok=False, detail=f"run {run_id} not found", retryable=True
                )
            if r.status_code >= 400:
                return DispatchResult(
                    ok=False,
                    detail=f"poll HTTP {r.status_code}: {r.text[:200]}",
                    retryable=False,
                )
            try:
                data = r.json()
            except ValueError:
                await asyncio.sleep(self._poll)
                continue
            last_status = str(data.get("status") or data.get("state") or "unknown").lower()
            output = self._extract_output(data)
            usage = self._extract_usage(data)
            if last_status in _WAITING:
                # Human gate is outside the adapter — count as successfully handed off.
                return DispatchResult(
                    ok=True,
                    detail=f"run_id={run_id} status={last_status} task_id={task_id}",
                    output=output,
                    usage=usage,
                )
            if last_status in _TERMINAL:
                if last_status == "completed":
                    return DispatchResult(
                        ok=True,
                        detail=f"run_id={run_id} status=completed task_id={task_id}",
                        output=output,
                        usage=usage,
                    )
                err = data.get("error") or data.get("detail") or last_status
                return DispatchResult(
                    ok=False,
                    detail=f"run_id={run_id} status={last_status}: {err}"[:500],
                    retryable=last_status in {"failed", "error"},
                    output=output,
                    usage=usage,
                )
            await asyncio.sleep(self._poll)

        return DispatchResult(
            ok=False,
            detail=f"run_id={run_id} poll timed out after {self._timeout}s (last={last_status})",
            retryable=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class HermesCliDispatcher:
    name = "hermes_cli"

    def __init__(self, template: str, *, outbox_dir: str, timeout_seconds: int = 1_800) -> None:
        self._template = template
        self._dir = Path(outbox_dir)
        self._timeout = timeout_seconds

    def build_command(self, task: dict[str, Any], prompt: str, prompt_file: Path) -> list[str]:
        rendered = self._template.format(
            prompt_file=shlex.quote(str(prompt_file)),
            prompt=shlex.quote(prompt),
            agent=shlex.quote(task.get("assigned_to") or "hermes"),
            task_id=shlex.quote(task["task_id"]),
            skill=shlex.quote(task.get("skill") or "dev-flow"),
        )
        return shlex.split(rendered)

    async def dispatch(self, task: dict[str, Any], prompt: str) -> DispatchResult:
        self._dir.mkdir(parents=True, exist_ok=True)
        prompt_file = self._dir / f"{task['task_id']}.prompt.md"
        prompt_file.write_text(prompt, encoding="utf-8")
        cmd = self.build_command(task, prompt, prompt_file)
        log.info("hermes_cli: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except FileNotFoundError:
            return DispatchResult(ok=False, detail=f"command not found: {cmd[0]}", retryable=False)
        except TimeoutError:
            proc.kill()
            return DispatchResult(ok=False, detail="hermes cli timed out", retryable=True)
        text = out.decode("utf-8", errors="replace")[-2000:]
        rc = int(proc.returncode if proc.returncode is not None else -1)
        metrics.inc_sandbox_exec(rc)
        if rc == 0:
            return DispatchResult(ok=True, detail=text)
        return DispatchResult(ok=False, detail=f"exit {rc}: {text}", retryable=True)

    async def aclose(self) -> None:
        return None


def build_dispatcher(settings: Any) -> Dispatcher:
    if settings.dispatcher == "hermes_api":
        return HermesApiDispatcher(
            settings.hermes_api_url,
            token=settings.hermes_api_token,
            timeout_seconds=settings.dispatch_timeout_seconds,
            poll_interval_seconds=settings.hermes_api_poll_interval_seconds,
        )
    if settings.dispatcher == "http":
        return HttpDispatcher(settings.hermes_http_url, token=settings.hermes_http_token)
    if settings.dispatcher == "hermes_cli":
        return HermesCliDispatcher(
            settings.hermes_cli_template,
            outbox_dir=settings.outbox_dir,
            timeout_seconds=settings.dispatch_timeout_seconds,
        )
    return DryRunDispatcher(settings.outbox_dir)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
