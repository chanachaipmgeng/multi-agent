# Enterprise Multi-Agent Workspace — developer entry points
SHELL := /bin/bash
COMPOSE ?= docker compose
PY      ?= python3
GW      := webhook-gateway
VENV    := $(GW)/.venv

.DEFAULT_GOAL := help

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ----------------------------------------------------------------- setup
prereqs: ## check host prerequisites (D0.1)
	@scripts/check-prereqs.sh

venv: ## create the gateway virtualenv with dev deps
	@test -d $(VENV) || (cd $(GW) && ($(PY) -m venv .venv || uv venv .venv))
	@if command -v uv >/dev/null; then uv pip install --python $(VENV)/bin/python -q -e "$(GW)[dev]"; \
	 else $(VENV)/bin/pip install -q -e "$(GW)[dev]"; fi

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
up: ## start redis + postgres + webhook-gateway
	@test -s secrets/gitlab_webhook_secret || (echo "run 'make secrets-decrypt' (or secrets-dev) first"; exit 1)
	$(COMPOSE) up -d --build redis postgres webhook-gateway

up-agents: ## also start the 6 Hermes profile containers
	$(COMPOSE) --profile agents up -d

up-ingress: ## start the cloudflared tunnel connector (needs secrets/tunnel_token)
	$(COMPOSE) --profile ingress up -d cloudflared

down: ## stop everything (keeps volumes)
	$(COMPOSE) --profile agents --profile ingress --profile onprem-llm down

logs: ## tail gateway logs
	$(COMPOSE) logs -f webhook-gateway

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
test: venv ## gateway unit tests (fakeredis + in-memory store)
	cd $(GW) && .venv/bin/pytest -q

test-integration: venv ## gateway integration tests against TEST_DATABASE_URL
	cd $(GW) && .venv/bin/pytest -q -m integration

lint: venv ## ruff lint + format check
	cd $(GW) && .venv/bin/ruff check . && .venv/bin/ruff format --check .

gitleaks: ## scan the repo for secrets
	gitleaks detect --no-banner --redact --config .gitleaks.toml --source .

webhook-test: ## send a sample Issue Hook to the running gateway (KIND=issue|pipeline|job)
	@scripts/send-test-webhook.sh $(or $(KIND),issue)

verify-phase0: ## run the Phase 0 exit-criteria self-check
	@scripts/verify-phase0.sh

.PHONY: help prereqs venv hooks secrets-init secrets-encrypt secrets-decrypt secrets-dev up up-agents up-ingress down logs ps migrate hermes-configure skills-sync skills-check onboard test test-integration lint gitleaks webhook-test verify-phase0
