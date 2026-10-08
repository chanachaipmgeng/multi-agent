"""GitHub enrichment client — same keys as GitLab for prompt.py."""

from __future__ import annotations

import httpx
import pytest

from app.github import GitHubClient
from app.scm import ScmRouter

from .conftest import make_job_failed_task, make_task


@pytest.fixture
def github_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/actions/jobs/88001/logs"):
            assert request.headers.get("Authorization") == "Bearer ghp-test-token"
            body = (
                "Run pytest -q\n"
                "export GITHUB_TOKEN=ghp-SuperSecretValue1234567890\n"
                "ERROR: Could not find a version that satisfies the requirement foo==9.9.9\n"
                "ERROR: Process completed with exit code 1.\n"
            )
            return httpx.Response(200, text=body)
        if "/actions/runs/77001/jobs" in path:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 88001,
                            "name": "test",
                            "labels": ["ubuntu-latest"],
                            "conclusion": "failure",
                        },
                        {
                            "id": 88002,
                            "name": "lint",
                            "labels": ["ubuntu-latest"],
                            "conclusion": "success",
                        },
                    ]
                },
            )
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def github(settings, github_transport) -> GitHubClient:
    return GitHubClient(
        "https://api.github.com",
        "ghp-test-token",
        trace_max_bytes=settings.trace_max_bytes,
        transport=github_transport,
    )


def make_github_job_failed_task() -> dict:
    return make_task(
        task_id="t-20261009-ghjob",
        type="job_failed",
        project="sandbox-github",
        assigned_to="devops",
        skill="incident-triage",
        source={
            "kind": "github_webhook",
            "event": "workflow_job",
            "event_uuid": "gh-evt-1",
            "repo": "acme/sandbox-github",
            "repo_id": 88888,
            "job_id": 88001,
            "pipeline_id": 77001,
        },
        inputs={
            "job_id": 88001,
            "job_name": "test",
            "pipeline_id": 77001,
            "branch": "hotfix/ci-77001",
            "scm": "github",
            "repo": "acme/sandbox-github",
        },
        constraints={"token_budget": 300000, "self_heal_limit": 2, "deadline_min": 45},
    )


async def test_github_enrich_fetches_and_redacts_job_logs(github) -> None:
    extra = await github.enrich(make_github_job_failed_task())
    trace = extra["job_trace"]
    assert "Could not find a version" in trace
    assert "SuperSecretValue" not in trace
    assert "GITHUB_TOKEN=[REDACTED]" in trace


async def test_github_enrich_pipeline_failed_jobs(github) -> None:
    task = make_github_job_failed_task()
    task["type"] = "pipeline_failed"
    task["inputs"]["failed_jobs"] = []
    extra = await github.enrich(task)
    assert list(extra["job_traces"]) == ["88001"]
    assert "ERROR: Process completed" in extra["job_traces"]["88001"]
    assert len(extra["failed_jobs"]) == 1


async def test_github_enrich_noop_without_token_or_gitlab_kind(github) -> None:
    assert await github.enrich(make_task()) == {}
    disabled = GitHubClient("https://api.github.com", None)
    assert disabled.enabled is False
    assert await disabled.enrich(make_github_job_failed_task()) == {}
    await disabled.aclose()


async def test_scm_router_picks_github(gitlab, github) -> None:
    router = ScmRouter(gitlab, github)
    assert router.client_for(make_github_job_failed_task()) is github
    assert router.client_for(make_job_failed_task()) is gitlab
    extra = await router.enrich(make_github_job_failed_task())
    assert "job_trace" in extra
