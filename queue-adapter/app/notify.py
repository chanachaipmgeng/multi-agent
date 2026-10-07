"""Optional Telegram notifications (Phase 1: the single Hermes agent is the main channel;
these messages make sure a human hears about a task even if dispatch to Hermes fails)."""

from __future__ import annotations

import logging

import httpx

from .redaction import redact

log = logging.getLogger("emaw.adapter.notify")


class TelegramNotifier:
    def __init__(
        self,
        token: str | None,
        chat_id: str | None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.enabled = bool(token and chat_id)
        self._chat_id = chat_id
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{token}"
            if token
            else "https://api.telegram.org",
            timeout=10.0,
            transport=transport,
        )

    async def send(self, text: str) -> None:
        if not self.enabled:
            return
        safe = redact(text)[:4000]
        try:
            r = await self._client.post(
                "/sendMessage",
                json={
                    "chat_id": self._chat_id,
                    "text": safe,
                    "disable_web_page_preview": True,
                },
            )
            if r.status_code >= 300:
                log.warning("telegram sendMessage failed: HTTP %s", r.status_code)
        except httpx.HTTPError as exc:
            log.warning("telegram sendMessage error: %s", exc)

    async def aclose(self) -> None:
        await self._client.aclose()


def task_received_text(task: dict) -> str:
    inputs = task.get("inputs") or {}
    title = inputs.get("issue_title") or inputs.get("job_name") or inputs.get("ref") or ""
    return (
        f"🤖 รับงาน {task.get('task_id')} ({task.get('type')}) · {task.get('project')}\n"
        f"{title}\nskill: {task.get('skill')} · worker: {task.get('assigned_to') or '-'}\n"
        f"trace: {task.get('trace_id')}"
    )


def dispatch_failed_text(task: dict, detail: str, deliveries: int, max_deliveries: int) -> str:
    return (
        f"⚠️ ส่งงาน {task.get('task_id')} ให้ agent ไม่สำเร็จ (ครั้งที่ {deliveries}/{max_deliveries})\n"
        f"{redact(detail)[:300]}\ntrace: {task.get('trace_id')}"
    )


def dead_letter_text(task: dict, detail: str) -> str:
    return (
        f"🛑 งาน {task.get('task_id')} ล้มเหลวหลัง retry ครบ → FAILED (dead-letter)\n"
        f"{redact(detail)[:300]}\ntrace: {task.get('trace_id')}"
    )
