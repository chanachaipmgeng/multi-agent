"""Prometheus metrics (design §8.2)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

registry = CollectorRegistry()

webhook_received_total = Counter(
    "webhook_received_total",
    "GitLab webhooks received, by event type, project key and outcome",
    labelnames=("event", "project", "status"),
    registry=registry,
)
webhook_auth_fail_total = Counter(
    "webhook_auth_fail_total",
    "Webhooks rejected because X-Gitlab-Token did not match",
    registry=registry,
)
tasks_enqueued_total = Counter(
    "tasks_enqueued_total",
    "Tasks published to the coordinator inbox stream",
    labelnames=("type", "worker"),
    registry=registry,
)
webhook_processing_seconds = Histogram(
    "webhook_processing_seconds",
    "End-to-end time to verify, normalize and enqueue a webhook",
    registry=registry,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
approval_latency_seconds = Histogram(
    "approval_latency_seconds",
    "Time from approval request to decision",
    registry=registry,
    buckets=(30.0, 60.0, 120.0, 300.0, 600.0, 1200.0, 3600.0),
)
task_state_total = Gauge(
    "task_state_total",
    "Tasks currently in each state (scraped from task store)",
    labelnames=("state",),
    registry=registry,
)
