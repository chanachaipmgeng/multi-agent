# Enterprise Multi-Agent Workspace — developer entry points
SHELL := /bin/bash
COMPOSE ?= docker compose
PY      ?= python3
GW      := webhook-gateway
QA      := queue-adapter
VENV    := $(GW)/.venv
QVENV   := $(QA)/.venv

.DEFAULT_GOAL := help

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ----------------------------------------------------------------- setup
prereqs: ## check host prerequisites (D0.1)
	@scripts/check-prereqs.sh

venv: ## create the gateway + adapter virtualenvs with dev deps
	@test -d $(VENV) || (cd $(GW) && ($(PY) -m venv .venv || uv venv .venv))
	@if command -v uv >/dev/null; then uv pip install --python $(VENV)/bin/python -q -e "$(GW)[dev]"; \
	 else $(VENV)/bin/pip install -q -e "$(GW)[dev]"; fi
	@test -d $(QVENV) || (cd $(QA) && ($(PY) -m venv .venv || uv venv .venv))
	@if command -v uv >/dev/null; then uv pip install --python $(QVENV)/bin/python -q -e "$(QA)[dev]"; \
	 else $(QVENV)/bin/pip install -q -e "$(QA)[dev]"; fi

hooks: ## install pre-commit hooks (gitleaks, ruff)
	@command -v pre-commit >/dev/null || pip install --user pre-commit
	@pre-commit install

# --------------------------------------------------------------- secrets
secrets-init: ## generate age key + wire into .sops.yaml (D0.6)
	@scripts/secrets-init.sh

secrets-encrypt: ## .env → .env.enc (SOPS/age)
	@scripts/secrets-encrypt.sh

secrets-decrypt: ## .env.enc → ./secrets/* files for compose
	@scripts/secrets-decrypt.sh

secrets-dev: ## dev shortcut: plaintext .env → ./secrets/* (no SOPS)
	@scripts/secrets-decrypt.sh --from-plain-env

# --------------------------------------------------------------- compose
up: ## start redis + postgres + webhook-gateway + queue-adapter
	@test -s secrets/gitlab_webhook_secret || (echo "run 'make secrets-decrypt' (or secrets-dev) first"; exit 1)
	$(COMPOSE) up -d --build redis postgres webhook-gateway queue-adapter

up-agents: ## seed Hermes .env + skills, then start agent profile containers
	@test -s secrets/hermes_api_key || (echo "set SECRET_HERMES_API_KEY in .env and re-run secrets-dev/decrypt"; exit 1)
	@scripts/hermes-seed-env.sh
	@scripts/sync-skills.sh
	$(COMPOSE) --profile agents up -d
hermes-seed: ## write hermes-data/<agent>/.env from ./secrets/*
	@scripts/hermes-seed-env.sh

up-ingress: ## start the cloudflared tunnel connector (needs secrets/tunnel_token)
	$(COMPOSE) --profile ingress up -d cloudflared

up-socraticode: ## start Ollama + Qdrant for SocratiCode MCP (DECISION-6)
	@docker volume create socraticode_ollama_data >/dev/null
	@docker volume create socraticode_qdrant_data >/dev/null
	$(COMPOSE) --profile socraticode up -d socraticode-ollama socraticode-qdrant

down: ## stop everything (keeps volumes)
	$(COMPOSE) --profile agents --profile ingress --profile onprem-llm --profile socraticode down

logs: ## tail gateway + adapter logs
	$(COMPOSE) logs -f webhook-gateway queue-adapter

outbox: ## list prompts the adapter produced in dryrun mode
	$(COMPOSE) exec queue-adapter sh -c 'ls -1t /var/lib/queue-adapter/outbox | head -20'

# ---------------------------------------------------------------- phase 1
tunnel-setup: ## create Named Tunnel + DNS + config (HOST=webhook.example.com [NAME=emaw] [SERVICE=1])
	@scripts/tunnel-setup.sh "$(HOST)" "$(or $(NAME),emaw)" $(if $(SERVICE),--service,)

tunnel-status: ## show cloudflared / gateway / public-path status (URL=https://webhook.example.com)
	@scripts/tunnel-status.sh $(URL)

gitlab-webhook: ## register/update the GitLab webhook (PROJECT=group/repo URL=https://webhook.example.com, needs GITLAB_ADMIN_TOKEN)
	@scripts/gitlab-webhook-register.sh "$(PROJECT)" "$(URL)"

gitlab-token-check: ## verify scopes/expiry of secrets/gitlab_token_*
	@scripts/gitlab-token-check.sh

ps: ## show service status
	$(COMPOSE) --profile agents --profile ingress ps

migrate: ## apply pending db/migrations to the compose postgres
	@scripts/migrate.sh

# ----------------------------------------------------------------- hermes
hermes-configure: ## configure host hermes for Phase 0 (needs TELEGRAM_ALLOWED_USERS)
	@scripts/hermes-configure.sh

skills-sync: ## copy skills/ into hermes-data/<agent>/skills/
	@scripts/sync-skills.sh

skills-check: ## fail if hermes-data skills drift from skills/
	@scripts/sync-skills.sh --check

onboard: ## onboard a repo: make onboard KEY=backend-api URL=git@... TEST="pytest -q"
	@scripts/onboard-project.sh "$(KEY)" "$(URL)" "$(TEST)"

# ------------------------------------------------------------------ tests
test: venv ## gateway + adapter unit tests (fakeredis + in-memory stores)
	cd $(GW) && .venv/bin/pytest -q
	cd $(QA) && .venv/bin/pytest -q

test-integration: venv ## gateway integration tests against TEST_DATABASE_URL
	cd $(GW) && .venv/bin/pytest -q -m integration

lint: venv ## ruff lint + format check (gateway + adapter)
	cd $(GW) && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd $(QA) && .venv/bin/ruff check . && .venv/bin/ruff format --check .

gitleaks: ## scan the repo for secrets
	gitleaks detect --no-banner --redact --config .gitleaks.toml --source .

webhook-test: ## send a sample Issue Hook to the running gateway (KIND=issue|pipeline|job)
	@scripts/send-test-webhook.sh $(or $(KIND),issue)

verify-phase0: ## run the Phase 0 exit-criteria self-check
	@scripts/verify-phase0.sh

.PHONY: help prereqs venv hooks secrets-init secrets-encrypt secrets-decrypt secrets-dev up up-agents hermes-seed up-ingress down logs outbox ps migrate tunnel-setup tunnel-status gitlab-webhook gitlab-token-check hermes-configure skills-sync skills-check onboard test test-integration lint gitleaks webhook-test verify-phase0
