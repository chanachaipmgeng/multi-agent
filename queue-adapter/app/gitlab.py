"""Minimal GitLab read-only client used to enrich tasks (job traces for incident-triage)."""

from __future__ import annotations

from typing import Any

import httpx

from .redaction import redact, tail


class GitLabClient:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        *,
        trace_max_bytes: int = 65_536,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.enabled = bool(token)
        self._trace_max = trace_max_bytes
        headers = {"PRIVATE-TOKEN": token} if token else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/api/v4",
            headers=headers,
            timeout=httpx.Timeout(20.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def job_trace(self, project_id: int, job_id: int) -> str:
        r = await self._client.get(f"/projects/{project_id}/jobs/{job_id}/trace")
        r.raise_for_status()
        return redact(tail(r.text, self._trace_max))

    async def pipeline_failed_jobs(self, project_id: int, pipeline_id: int) -> list[dict[str, Any]]:
        r = await self._client.get(
            f"/projects/{project_id}/pipelines/{pipeline_id}/jobs",
            params={"scope[]": "failed", "per_page": 20},
        )
        r.raise_for_status()
        return [
            {
                "id": j["id"],
                "name": j.get("name"),
                "stage": j.get("stage"),
                "failure_reason": j.get("failure_reason"),
            }
            for j in r.json()
        ]

    async def enrich(self, task: dict[str, Any]) -> dict[str, Any]:
        """Return extra inputs for ``pipeline_failed`` / ``job_failed`` tasks (empty otherwise)."""
        if not self.enabled:
            return {}
        source = task.get("source") or {}
        kind = source.get("kind") or ""
        if kind and not kind.startswith("gitlab"):
            return {}
        project_id = source.get("gitlab_project_id")
        if not project_id:
            return {}

        extra: dict[str, Any] = {}
        if task.get("type") == "job_failed" and source.get("job_id"):
            extra["job_trace"] = await self.job_trace(project_id, source["job_id"])
        elif task.get("type") == "pipeline_failed" and source.get("pipeline_id"):
            jobs = task.get("inputs", {}).get("failed_jobs") or await self.pipeline_failed_jobs(
                project_id, source["pipeline_id"]
            )
            traces = {}
            for job in jobs[:3]:  # bound the prompt size; the agent can fetch more via read_api
                if job.get("id"):
                    traces[str(job["id"])] = await self.job_trace(project_id, job["id"])
            extra["failed_jobs"] = jobs
            extra["job_traces"] = traces
        return extra
