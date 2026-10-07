"""Dispatchers: how a prompt reaches the Hermes agent.

Hermes' exact non-interactive interface is still to be confirmed (design DECISION-1, open
question "HTTP/CLI interface for queue-adapter"), so the adapter is pluggable:

* ``DryRunDispatcher``   — writes the prompt to an outbox directory (no Hermes needed; CI/dev)
* ``HttpDispatcher``     — POSTs ``{task, prompt}`` to a URL (Hermes gateway webhook or a shim)
* ``HermesCliDispatcher``— runs a shell template, e.g. ``hermes run --file {prompt_file}``
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

log = logging.getLogger("emaw.adapter.dispatch")


@dataclass(slots=True)
class DispatchResult:
    ok: bool
    detail: str = ""
    retryable: bool = True


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
        # 4xx = our payload/auth is wrong → retrying will not help
        return DispatchResult(
            ok=False, detail=f"HTTP {r.status_code}: {r.text[:200]}", retryable=r.status_code >= 500
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
        if proc.returncode == 0:
            return DispatchResult(ok=True, detail=text)
        return DispatchResult(ok=False, detail=f"exit {proc.returncode}: {text}", retryable=True)

    async def aclose(self) -> None:
        return None


def build_dispatcher(settings: Any) -> Dispatcher:
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
