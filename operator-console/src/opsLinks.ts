/** Build ops deep-links from the browser host (LAN Console) + bake-time ports. */

function pageHost(): string {
  if (typeof window === "undefined") return "127.0.0.1";
  return window.location.hostname || "127.0.0.1";
}

export function isRemoteConsole(): boolean {
  const h = pageHost();
  return h !== "127.0.0.1" && h !== "localhost" && h !== "::1";
}

export function grafanaPort(): string {
  return import.meta.env.VITE_GRAFANA_PORT || "3000";
}

export function hermesDashboardPort(): string {
  return import.meta.env.VITE_HERMES_PORT || "9119";
}

export function grafanaBaseUrl(): string {
  if (import.meta.env.VITE_GRAFANA_URL) return import.meta.env.VITE_GRAFANA_URL.replace(/\/$/, "");
  return `http://${pageHost()}:${grafanaPort()}`;
}

export function hermesDashboardUrl(): string {
  if (import.meta.env.VITE_HERMES_URL) return import.meta.env.VITE_HERMES_URL.replace(/\/$/, "");
  return `http://${pageHost()}:${hermesDashboardPort()}`;
}

/** Loopback-only on the host — use SSH -L from a laptop. */
export function loopbackUrl(port: string, path = ""): string {
  return `http://127.0.0.1:${port}${path}`;
}

export function sshTunnelHint(host: string): string {
  const g = grafanaPort();
  const h = hermesDashboardPort();
  return `ssh -L ${g}:127.0.0.1:${g} -L ${h}:127.0.0.1:${h} -L 9001:127.0.0.1:9001 -L 9090:127.0.0.1:9090 USER@${host}`;
}
