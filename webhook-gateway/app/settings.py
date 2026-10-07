"""Runtime configuration for the webhook gateway.

All values come from environment variables (or Docker secrets via *_FILE variants).
No secret has a default value: the gateway refuses to start without a webhook secret.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_GITLAB_EVENTS: frozenset[str] = frozenset({"Issue Hook", "Pipeline Hook", "Job Hook"})


def _read_secret_file(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"secret file not found: {path}")
    return p.read_text(encoding="utf-8").strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # --- identity / network -------------------------------------------------
    app_name: str = "emaw-webhook-gateway"
    host: str = "0.0.0.0"
    port: int = 8700
    log_level: str = "info"

    # --- webhook security ---------------------------------------------------
    gitlab_webhook_secret: str | None = Field(default=None, alias="GITLAB_WEBHOOK_SECRET")
    gitlab_webhook_secret_file: str | None = Field(default=None, alias="GITLAB_WEBHOOK_SECRET_FILE")
    allowed_events: frozenset[str] = ALLOWED_GITLAB_EVENTS
    max_body_bytes: int = Field(default=1_048_576, alias="MAX_BODY_BYTES")  # 1 MiB

    # --- idempotency / queue -----------------------------------------------
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    idempotency_ttl_seconds: int = Field(default=86_400, alias="IDEMPOTENCY_TTL_SECONDS")
    idempotency_prefix: str = "emaw:idem:"
    task_stream: str = Field(default="stream:tasks", alias="TASK_STREAM")
    task_stream_maxlen: int = Field(default=10_000, alias="TASK_STREAM_MAXLEN")

    # --- task store (optional in Phase 0) ----------------------------------
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    pg_password_file: str | None = Field(default=None, alias="PG_PASSWORD_FILE")

    # --- project allowlist / routing ---------------------------------------
    projects_file: str = Field(default="/config/projects.yaml", alias="PROJECTS_FILE")
    rbac_file: str = Field(default="/config/rbac.yaml", alias="RBAC_FILE")
    control_prefix: str = Field(default="emaw:control", alias="CONTROL_PREFIX")

    # --- internal API (coordinator → gateway) ------------------------------
    hermes_api_key: str | None = Field(default=None, alias="HERMES_API_KEY")
    hermes_api_key_file: str | None = Field(default=None, alias="HERMES_API_KEY_FILE")

    @model_validator(mode="after")
    def _resolve_secrets(self) -> Settings:
        if not self.gitlab_webhook_secret:
            try:
                self.gitlab_webhook_secret = _read_secret_file(self.gitlab_webhook_secret_file)
            except FileNotFoundError:
                self.gitlab_webhook_secret = None
        if not self.gitlab_webhook_secret:
            raise ValueError(
                "GITLAB_WEBHOOK_SECRET (or GITLAB_WEBHOOK_SECRET_FILE) is required; "
                "the gateway never runs without a webhook secret"
            )
        if not self.hermes_api_key and self.hermes_api_key_file:
            try:
                self.hermes_api_key = _read_secret_file(self.hermes_api_key_file)
            except FileNotFoundError:
                self.hermes_api_key = None
        if self.database_url and "${PG_PASSWORD}" in self.database_url:
            pw = _read_secret_file(self.pg_password_file)
            if pw is None:
                raise ValueError(
                    "DATABASE_URL references ${PG_PASSWORD} but PG_PASSWORD_FILE is unset"
                )
            self.database_url = self.database_url.replace("${PG_PASSWORD}", pw)
        return self
