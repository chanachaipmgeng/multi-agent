"""GitHub Actions enrichment client (job logs for incident-triage).

Returns the same enrichment keys as :class:`GitLabClient` so ``prompt.py`` stays
SCM-agnostic: ``job_trace``, ``job_traces``, ``failed_jobs``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .redaction import redact, tail


class GitHubClient:
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
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(30.0),
            transport=transport,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _repo_path(self, source: dict[str, Any], inputs: dict[str, Any]) -> str | None:
        repo = source.get("repo") or inputs.get("repo") or source.get("path_with_namespace")
        if not repo:
            return None
        return quote(str(repo), safe="/")

    async def job_logs(self, repo: str, job_id: int) -> str:
        r = await self._client.get(f"/repos/{repo}/actions/jobs/{job_id}/logs")
        r.raise_for_status()
        text = r.text if isinstance(r.text, str) else r.content.decode("utf-8", errors="replace")
        return redact(tail(text, self._trace_max))

    async def run_failed_jobs(self, repo: str, run_id: int) -> list[dict[str, Any]]:
        r = await self._client.get(
            f"/repos/{repo}/actions/runs/{run_id}/jobs",
            params={"per_page": 50},
        )
        r.raise_for_status()
        jobs = (r.json() or {}).get("jobs") or []
        return [
            {
                "id": j["id"],
                "name": j.get("name"),
                "stage": (j.get("labels") or [None])[0] if isinstance(j.get("labels"), list) else None,
                "failure_reason": j.get("conclusion"),
            }
            for j in jobs
            if j.get("conclusion") == "failure"
        ]

    async def enrich(self, task: dict[str, Any]) -> dict[str, Any]:
        """Return extra inputs for ``pipeline_failed`` / ``job_failed`` (empty otherwise)."""
        if not self.enabled:
            return {}
        source = task.get("source") or {}
        kind = source.get("kind") or ""
        if kind and not kind.startswith("github"):
            return {}
        inputs = task.get("inputs") or {}
        repo = self._repo_path(source, inputs)
        if not repo:
            return {}

        extra: dict[str, Any] = {}
        if task.get("type") == "job_failed" and source.get("job_id"):
            extra["job_trace"] = await self.job_logs(repo, int(source["job_id"]))
        elif task.get("type") == "pipeline_failed" and source.get("pipeline_id"):
            jobs = inputs.get("failed_jobs") or await self.run_failed_jobs(
                repo, int(source["pipeline_id"])
            )
            traces: dict[str, str] = {}
            for job in jobs[:3]:
                if job.get("id"):
                    traces[str(job["id"])] = await self.job_logs(repo, int(job["id"]))
            extra["failed_jobs"] = jobs
            extra["job_traces"] = traces
        return extra
