from __future__ import annotations

import json

from app.prompt import build_prompt

from .conftest import make_job_failed_task, make_task


def test_prompt_contains_skill_task_and_platform_rules() -> None:
    task = make_task()
    prompt = build_prompt(task)
    assert prompt.startswith("run skill resolve-issue with task t-20261007-abc123")
    assert "ห้าม push ไป main" in prompt
    assert "human-approval-gate" in prompt
    assert "token_budget=400000" in prompt
    # the full envelope is embedded verbatim as JSON
    start = prompt.index("TASK (JSON):") + len("TASK (JSON):\n")
    end = prompt.index("\n\n", start)
    embedded = json.loads(prompt[start:end])
    assert embedded["task_id"] == task["task_id"]
    assert embedded["inputs"]["branch"] == "fix/issue-89"


def test_prompt_includes_redacted_trace_when_enriched() -> None:
    task = make_job_failed_task()
    prompt = build_prompt(task, {"job_trace": "ERROR: exit code 1\nTOKEN=[REDACTED]"})
    assert "JOB TRACE (redacted, tail)" in prompt
    assert "ERROR: exit code 1" in prompt


async def test_gitlab_enrich_fetches_and_redacts_job_trace(gitlab) -> None:
    extra = await gitlab.enrich(make_job_failed_task())
    trace = extra["job_trace"]
    assert "Could not find a version" in trace
    assert "SuperSecretValue" not in trace
    assert "GITLAB_TOKEN=[REDACTED]" in trace


async def test_gitlab_enrich_pipeline_uses_failed_jobs(gitlab) -> None:
    task = make_job_failed_task()
    task["type"] = "pipeline_failed"
    task["inputs"] = {"failed_jobs": [{"id": 9002, "name": "docker-build", "stage": "build"}]}
    extra = await gitlab.enrich(task)
    assert list(extra["job_traces"]) == ["9002"]
    assert "ERROR: Job failed" in extra["job_traces"]["9002"]


async def test_gitlab_enrich_is_noop_for_issue_and_without_token(gitlab) -> None:
    assert await gitlab.enrich(make_task()) == {}
    from app.gitlab import GitLabClient

    disabled = GitLabClient("https://gitlab.example.com", None)
    assert disabled.enabled is False
    assert await disabled.enrich(make_job_failed_task()) == {}
    await disabled.aclose()
