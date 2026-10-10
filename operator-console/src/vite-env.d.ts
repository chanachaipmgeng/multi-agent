/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GRAFANA_URL?: string;
  readonly VITE_GRAFANA_PORT?: string;
  readonly VITE_HERMES_URL?: string;
  readonly VITE_HERMES_PORT?: string;
  readonly VITE_MINIO_URL?: string;
  readonly VITE_PROM_URL?: string;
  readonly VITE_GATEWAY_PROXY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
