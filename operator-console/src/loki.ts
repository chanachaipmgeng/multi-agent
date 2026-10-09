const GRAFANA = import.meta.env.VITE_GRAFANA_URL || "http://127.0.0.1:3000";

/** Grafana Explore deep-link for a Loki LogQL expression (best-effort). */
export function lokiExploreUrl(expr: string): string {
  const left = {
    datasource: "Loki",
    queries: [{ refId: "A", expr }],
    range: { from: "now-24h", to: "now" },
  };
  return `${GRAFANA}/explore?orgId=1&left=${encodeURIComponent(JSON.stringify(left))}`;
}

export function lokiByTaskId(taskId: string): string {
  return lokiExploreUrl(
    `{compose_service=~"webhook-gateway|router|adapter-.*"} |= \`task_id=${taskId}\``,
  );
}

export function lokiByTraceId(traceId: string): string {
  return lokiExploreUrl(
    `{compose_service=~"webhook-gateway|router|adapter-.*"} |= \`trace_id=${traceId}\``,
  );
}
