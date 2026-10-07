"""Configuration for the queue adapter (environment variables / Docker secrets)."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret_file(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    value = p.read_text(encoding="utf-8").strip()
    return value or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    log_level: str = Field(default="info", alias="LOG_LEVEL")

    # --- queue ---------------------------------------------------------------
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    task_stream: str = Field(default="stream:tasks", alias="TASK_STREAM")
    results_stream: str = Field(default="stream:results", alias="RESULTS_STREAM")
    dead_letter_stream: str = Field(default="stream:dead-letter", alias="DEAD_LETTER_STREAM")
    consumer_group: str = Field(default="hermes-single", alias="CONSUMER_GROUP")
    consumer_name: str = Field(default_factory=socket.gethostname, alias="CONSUMER_NAME")
    block_ms: int = Field(default=5_000, alias="BLOCK_MS")
    claim_min_idle_ms: int = Field(default=600_000, alias="CLAIM_MIN_IDLE_MS")  # 10 min (§10.3)
    max_deliveries: int = Field(default=3, alias="MAX_DELIVERIES")  # 1 + 2 retries (§10.3)
    heartbeat_key: str = "emaw:heartbeat:queue-adapter"
    heartbeat_file: str = Field(default="/tmp/queue-adapter.heartbeat", alias="HEARTBEAT_FILE")

    # --- task store (optional) ----------------------------------------------
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    pg_password_file: str | None = Field(default=None, alias="PG_PASSWORD_FILE")

    # --- dispatch --------------------------------------------------------------
    # dryrun      → write the prompt to OUTBOX_DIR and log it (no Hermes needed)
    # hermes_api  → POST /v1/runs on Hermes API server :8642 (preferred, DECISION-1)
    # http        → POST {task, prompt} to HERMES_HTTP_URL (legacy shim)
    # hermes_cli  → hermes -p {agent} chat --oneshot -Q --query-file {prompt_file} -s {skill}
    dispatcher: Literal["dryrun", "http", "hermes_cli", "hermes_api"] = Field(
        default="dryrun", alias="DISPATCHER"
    )
    outbox_dir: str = Field(default="/var/lib/queue-adapter/outbox", alias="OUTBOX_DIR")
    hermes_http_url: str | None = Field(default=None, alias="HERMES_HTTP_URL")
    hermes_http_token_file: str | None = Field(default=None, alias="HERMES_HTTP_TOKEN_FILE")
    hermes_api_url: str | None = Field(default=None, alias="HERMES_API_URL")
    hermes_api_key_file: str | None = Field(default=None, alias="HERMES_API_KEY_FILE")
    hermes_api_poll_interval_seconds: float = Field(
        default=2.0, alias="HERMES_API_POLL_INTERVAL_SECONDS"
    )
    hermes_cli_template: str = Field(
        default=(
            "hermes -p {agent} chat --oneshot -Q --query-file {prompt_file} -s {skill}"
        ),
        alias="HERMES_CLI_TEMPLATE",
    )
    dispatch_timeout_seconds: int = Field(default=1_800, alias="DISPATCH_TIMEOUT_SECONDS")
    # Phase 1–2: one Hermes instance handles every role. Phase 3: one adapter per role.
    single_agent_name: str = Field(default="hermes-single", alias="SINGLE_AGENT_NAME")

    # --- enrichment (GitLab read_api) -----------------------------------------
    gitlab_base_url: str = Field(default="https://gitlab.com", alias="GITLAB_BASE_URL")
    gitlab_token: str | None = Field(default=None, alias="GITLAB_TOKEN")
    gitlab_token_file: str | None = Field(default=None, alias="GITLAB_TOKEN_FILE")
    trace_max_bytes: int = Field(default=65_536, alias="TRACE_MAX_BYTES")

    # --- optional Telegram notifications --------------------------------------
    telegram_token_file: str | None = Field(default=None, alias="TELEGRAM_TOKEN_FILE")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")

    @model_validator(mode="after")
    def _resolve(self) -> Settings:
        if not self.gitlab_token:
            self.gitlab_token = _read_secret_file(self.gitlab_token_file)
        if self.database_url and "${PG_PASSWORD}" in self.database_url:
            pw = _read_secret_file(self.pg_password_file)
            if pw is None:
                raise ValueError(
                    "DATABASE_URL references ${PG_PASSWORD} but PG_PASSWORD_FILE is unset"
                )
            self.database_url = self.database_url.replace("${PG_PASSWORD}", pw)
        if self.dispatcher == "http" and not self.hermes_http_url:
            raise ValueError("DISPATCHER=http requires HERMES_HTTP_URL")
        if self.dispatcher == "hermes_api" and not self.hermes_api_url:
            raise ValueError("DISPATCHER=hermes_api requires HERMES_API_URL")
        return self

    @property
    def telegram_token(self) -> str | None:
        return _read_secret_file(self.telegram_token_file)

    @property
    def hermes_http_token(self) -> str | None:
        return _read_secret_file(self.hermes_http_token_file)

    @property
    def hermes_api_token(self) -> str | None:
        return _read_secret_file(self.hermes_api_key_file)
