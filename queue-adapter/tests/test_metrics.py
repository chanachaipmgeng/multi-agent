"""Adapter Prometheus metrics render (§8.2)."""

from __future__ import annotations

from app import metrics


def setup_function() -> None:
    metrics.reset_for_tests()


def test_render_includes_core_counters() -> None:
    metrics.set_label("role", "dev-frontend")
    metrics.set_label("mode", "worker")
    metrics.inc("emaw_tasks_dispatched_total")
    body = metrics.render().decode()
    assert "emaw_tasks_dispatched_total{mode=" in body
    assert "role=\"dev-frontend\"" in body


def test_gauges_and_histogram() -> None:
    metrics.set_gauge("queue_depth", 3, {"stream": "stream:tasks"})
    metrics.set_gauge("agent_heartbeat_timestamp", 1_700_000_000.0, {"agent": "router"})
    metrics.observe_task_duration(45.0, task_type="issue", agent="dev-frontend")
    metrics.observe_llm_tokens(100, agent="dev-frontend")
    body = metrics.render().decode()
    assert 'queue_depth{stream="stream:tasks"} 3.0' in body
    assert 'agent_heartbeat_timestamp{agent="router"} 1700000000.0' in body
    assert "task_duration_seconds_bucket" in body
    assert 'llm_tokens_total{agent="dev-frontend"} 100.0' in body
