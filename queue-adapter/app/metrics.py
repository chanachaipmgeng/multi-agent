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

_LABELED_PREFIXES = (
    "llm_tokens_total|",
    "llm_cost_usd_total|",
    "self_heal_iterations|",
    "sandbox_exec_total|",
)


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


def _inc_labeled(name: str, amount: float, labels: dict[str, str]) -> None:
    key = _label_key(labels)
    with _lock:
        store_key = f"{name}|{key}"
        _counters[store_key] = _counters.get(store_key, 0.0) + float(amount)


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


def observe_llm_tokens(
    tokens: int,
    *,
    agent: str,
    model: str = "unknown",
    kind: str = "total",
) -> None:
    """Cumulative counter ``llm_tokens_total{agent,model,kind}`` (§8.2)."""
    _inc_labeled(
        "llm_tokens_total",
        float(tokens),
        {
            "agent": agent or "unknown",
            "model": model or "unknown",
            "kind": kind or "total",
        },
    )


def observe_llm_cost_usd(usd: float, *, agent: str) -> None:
    """Cumulative counter ``llm_cost_usd_total{agent}`` (§8.2 stub)."""
    _inc_labeled(
        "llm_cost_usd_total",
        float(usd),
        {"agent": agent or "unknown"},
    )


def observe_self_heal(iterations: int | float, *, agent: str) -> None:
    """Cumulative counter ``self_heal_iterations{agent}`` (§8.2)."""
    _inc_labeled(
        "self_heal_iterations",
        float(iterations),
        {"agent": agent or "unknown"},
    )


def inc_sandbox_exec(exit_code: int) -> None:
    """Counter ``sandbox_exec_total{exit_code}`` (§8.2)."""
    _inc_labeled(
        "sandbox_exec_total",
        1.0,
        {"exit_code": str(int(exit_code))},
    )


def _append_labeled_counter(
    lines: list[str],
    *,
    name: str,
    help_txt: str,
    stub_labels: dict[str, str],
) -> None:
    prefix = f"{name}|"
    keys = [k for k in _counters if k.startswith(prefix)]
    lines.append(f"# HELP {name} {help_txt}")
    lines.append(f"# TYPE {name} counter")
    if not keys:
        stub_key = _label_key(stub_labels)
        lbl = f"{{{stub_key}}}" if stub_key else ""
        lines.append(f"{name}{lbl} 0.0")
        return
    for k in sorted(keys):
        label = k.split("|", 1)[1]
        lbl = f"{{{label}}}" if label else ""
        lines.append(f"{name}{lbl} {_counters[k]}")


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

        _append_labeled_counter(
            lines,
            name="llm_tokens_total",
            help_txt="Cumulative LLM tokens by agent/model/kind",
            stub_labels={"agent": "unset", "model": "unknown", "kind": "total"},
        )
        _append_labeled_counter(
            lines,
            name="llm_cost_usd_total",
            help_txt="Cumulative estimated LLM cost in USD by agent",
            stub_labels={"agent": "unset"},
        )
        _append_labeled_counter(
            lines,
            name="self_heal_iterations",
            help_txt="Cumulative self-heal iterations by agent",
            stub_labels={"agent": "unset"},
        )
        _append_labeled_counter(
            lines,
            name="sandbox_exec_total",
            help_txt="Sandbox / Hermes CLI process exits by exit code",
            stub_labels={"exit_code": "0"},
        )

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
            if any(k.startswith(p) for p in _LABELED_PREFIXES):
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
