"""Prometheus metrics HTTP server for adapters (design §8, Phase 3 prep for Phase 4)."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

log = logging.getLogger("emaw.adapter.metrics")

# Simple in-process counters (no prometheus_client dependency — keep adapter light).
_counters: dict[str, float] = {
    "emaw_tasks_dispatched_total": 0.0,
    "emaw_tasks_failed_total": 0.0,
    "emaw_tasks_routed_total": 0.0,
    "emaw_run_seconds_sum": 0.0,
    "emaw_tokens_total": 0.0,
}
_labels: dict[str, str] = {}
_lock = threading.Lock()


def set_label(key: str, value: str) -> None:
    with _lock:
        _labels[key] = value


def inc(name: str, amount: float = 1.0) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0.0) + amount


def observe_run_seconds(seconds: float) -> None:
    inc("emaw_run_seconds_sum", seconds)


def observe_tokens(tokens: int) -> None:
    inc("emaw_tokens_total", float(tokens))


def render() -> bytes:
    with _lock:
        lines = [
            "# HELP emaw_tasks_dispatched_total Tasks successfully dispatched to Hermes",
            "# TYPE emaw_tasks_dispatched_total counter",
            f"emaw_tasks_dispatched_total{_fmt_labels()} {_counters['emaw_tasks_dispatched_total']}",
            "# HELP emaw_tasks_failed_total Tasks dead-lettered or failed",
            "# TYPE emaw_tasks_failed_total counter",
            f"emaw_tasks_failed_total{_fmt_labels()} {_counters['emaw_tasks_failed_total']}",
            "# HELP emaw_tasks_routed_total Tasks routed to a role stream",
            "# TYPE emaw_tasks_routed_total counter",
            f"emaw_tasks_routed_total{_fmt_labels()} {_counters['emaw_tasks_routed_total']}",
            "# HELP emaw_run_seconds_sum Cumulative Hermes run wall time",
            "# TYPE emaw_run_seconds_sum counter",
            f"emaw_run_seconds_sum{_fmt_labels()} {_counters['emaw_run_seconds_sum']}",
            "# HELP emaw_tokens_total Cumulative tokens reported by Hermes runs",
            "# TYPE emaw_tokens_total counter",
            f"emaw_tokens_total{_fmt_labels()} {_counters['emaw_tokens_total']}",
            "",
        ]
    return "\n".join(lines).encode("utf-8")


def _fmt_labels() -> str:
    if not _labels:
        return ""
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(_labels.items()))
    return "{" + parts + "}"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/metrics", "/metrics/"}:
            self.send_response(404)
            self.end_headers()
            return
        body = render()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def start_metrics_server(port: int, *, role: str, mode: str) -> HTTPServer | None:
    if port <= 0:
        return None
    set_label("role", role)
    set_label("mode", mode)
    try:
        server = HTTPServer(("0.0.0.0", port), _Handler)
    except OSError as exc:
        log.warning("metrics server could not bind :%d: %s", port, exc)
        return None

    thread = threading.Thread(target=server.serve_forever, name="metrics", daemon=True)
    thread.start()
    log.info("metrics listening on :%d/metrics", port)
    return server
