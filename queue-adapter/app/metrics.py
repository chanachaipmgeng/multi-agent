"""Prometheus metrics HTTP server for adapters (design §8.2)."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

log = logging.getLogger("emaw.adapter.metrics")

DURATION_BUCKETS = (30.0, 60.0, 120.0, 300.0, 600.0, 900.0, 1800.0, 3600.0)

# Simple in-process counters/gauges/histograms (no prometheus_client — keep adapter light).
_counters: dict[str, float] = {
    "emaw_tasks_dispatched_total": 0.0,
    "emaw_tasks_failed_total": 0.0,
    "emaw_tasks_routed_total": 0.0,
    "emaw_run_seconds_sum": 0.0,
    "emaw_tokens_total": 0.0,
}
_labels: dict[str, str] = {}
# gauge name → {label_tuple_str → value}
_gauges: dict[str, dict[str, float]] = {}
# histogram name → {label_tuple_str → {"buckets": [...counts], "sum": f, "count": f}}
_histograms: dict[str, dict[str, dict[str, Any]]] = {}
_hist_buckets: dict[str, tuple[float, ...]] = {}
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


def _label_key(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))


def set_gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    key = _label_key(labels)
    with _lock:
        _gauges.setdefault(name, {})[key] = float(value)


def observe_histogram(
    name: str,
    value: float,
    *,
    buckets: tuple[float, ...] = DURATION_BUCKETS,
    labels: dict[str, str] | None = None,
) -> None:
    key = _label_key(labels)
    with _lock:
        _hist_buckets[name] = buckets
        series = _histograms.setdefault(name, {}).setdefault(
            key,
            {"buckets": [0.0] * len(buckets), "sum": 0.0, "count": 0.0, "+Inf": 0.0},
        )
        series["sum"] += float(value)
        series["count"] += 1.0
        for i, edge in enumerate(buckets):
            if value <= edge:
                series["buckets"][i] += 1.0
        series["+Inf"] += 1.0


def observe_task_duration(seconds: float, *, task_type: str, agent: str) -> None:
    observe_histogram(
        "task_duration_seconds",
        seconds,
        buckets=DURATION_BUCKETS,
        labels={"type": task_type or "unknown", "agent": agent or "unknown"},
    )


def observe_llm_tokens(tokens: int, *, agent: str) -> None:
    # Cumulative counter with agent label (separate from unlabeled emaw_tokens_total).
    name = "llm_tokens_total"
    key = _label_key({"agent": agent or "unknown"})
    with _lock:
        _counters[f"{name}|{key}"] = _counters.get(f"{name}|{key}", 0.0) + float(tokens)


def render() -> bytes:
    with _lock:
        lines: list[str] = [
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
        ]

        # llm_tokens_total{agent}
        token_keys = [k for k in _counters if k.startswith("llm_tokens_total|")]
        if token_keys:
            lines.append("# HELP llm_tokens_total Cumulative LLM tokens by agent")
            lines.append("# TYPE llm_tokens_total counter")
            for k in sorted(token_keys):
                label = k.split("|", 1)[1]
                lbl = f"{{{label}}}" if label else ""
                lines.append(f"llm_tokens_total{lbl} {_counters[k]}")

        for name, series_map in sorted(_gauges.items()):
            help_txt = {
                "queue_depth": "Redis stream length",
                "queue_oldest_age_seconds": "Age of oldest pending stream entry",
                "agent_heartbeat_timestamp": "Unix timestamp of last agent/adapter heartbeat",
                "task_state_total": "Tasks currently in each state",
            }.get(name, name)
            lines.append(f"# HELP {name} {help_txt}")
            lines.append(f"# TYPE {name} gauge")
            for label, value in sorted(series_map.items()):
                lbl = f"{{{label}}}" if label else ""
                lines.append(f"{name}{lbl} {value}")

        for name, series_map in sorted(_histograms.items()):
            buckets = _hist_buckets.get(name, DURATION_BUCKETS)
            lines.append(f"# HELP {name} {name}")
            lines.append(f"# TYPE {name} histogram")
            for label, series in sorted(series_map.items()):
                cumulative = 0.0
                for i, edge in enumerate(buckets):
                    cumulative += series["buckets"][i]
                    if label:
                        le = "{" + label + f',le="{edge}"}}'
                    else:
                        le = f'{{le="{edge}"}}'
                    lines.append(f"{name}_bucket{le} {cumulative}")
                if label:
                    inf = "{" + label + ',le="+Inf"}'
                    sum_lbl = "{" + label + "}"
                else:
                    inf = '{le="+Inf"}'
                    sum_lbl = ""
                lines.append(f"{name}_bucket{inf} {series['+Inf']}")
                lines.append(f"{name}_sum{sum_lbl} {series['sum']}")
                lines.append(f"{name}_count{sum_lbl} {series['count']}")

        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _fmt_labels() -> str:
    if not _labels:
        return ""
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(_labels.items()))
    return "{" + parts + "}"


def reset_for_tests() -> None:
    """Clear all series (unit tests only)."""
    with _lock:
        for k in list(_counters):
            if k.startswith("llm_tokens_total|"):
                del _counters[k]
            else:
                _counters[k] = 0.0
        _gauges.clear()
        _histograms.clear()
        _hist_buckets.clear()
        _labels.clear()


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
