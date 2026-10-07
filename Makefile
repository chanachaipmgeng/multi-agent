# Enterprise Multi-Agent Workspace — developer entry points
SHELL := /bin/bash
COMPOSE ?= docker compose
COMPOSE_LOCAL_FREE ?= $(COMPOSE) -f docker-compose.yml -f docker-compose.local-free.yml
PY      ?= python3
GW      := webhook-gateway
QA      := queue-adapter
VENV    := $(GW)/.venv
QVENV   := $(QA)/.venv
LOCAL_LLM_MODEL ?= qwen2.5-coder:7b

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
up: ## start redis + postgres + gateway + minio + router + 5 role adapters
	@test -s secrets/gitlab_webhook_secret || (echo "run 'make secrets-decrypt' (or secrets-dev) first"; exit 1)
	@test -s secrets/minio_agent_secret || (printf '%s' 'emaw-minio-agent-dev' > secrets/minio_agent_secret)
	@cp -n config/rbac.example.yaml config/rbac.yaml 2>/dev/null || true
	$(COMPOSE) up -d --build redis postgres webhook-gateway minio router \
		adapter-dev-frontend adapter-dev-backend adapter-reviewer adapter-qa adapter-devops

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

socraticode-check: ## smoke-check SocratiCode Ollama + Qdrant (no license needed)
	@scripts/socraticode-infra-check.sh

up-local-free: ## local-free stack: platform + router + 5 adapters + socraticode + inference + 6 agents
	@test -s secrets/hermes_api_key || (echo "set SECRET_HERMES_API_KEY in .env and re-run secrets-dev/decrypt"; exit 1)
	@test -s secrets/minio_agent_secret || (echo "emaw-minio-agent-dev" > secrets/minio_agent_secret)
	@cp -n config/rbac.example.yaml config/rbac.yaml 2>/dev/null || true
	@docker volume create socraticode_ollama_data >/dev/null
	@docker volume create socraticode_qdrant_data >/dev/null
	@LLM_MODE=local scripts/hermes-seed-env.sh
	@scripts/sync-skills.sh
	ADAPTER_DISPATCHER=hermes_api $(COMPOSE_LOCAL_FREE) --profile agents --profile socraticode --profile onprem-llm up -d \
		redis postgres webhook-gateway minio router \
		adapter-dev-frontend adapter-dev-backend adapter-reviewer adapter-qa adapter-devops \
		inference-ollama socraticode-ollama socraticode-qdrant \
		coordinator dev-frontend dev-backend reviewer qa devops
	@scripts/minio-init.sh || true

local-llm-pull: ## pull LOCAL_LLM_MODEL into inference-ollama (default qwen2.5-coder:7b)
	docker exec emaw-inference-ollama ollama pull $(LOCAL_LLM_MODEL)

local-free-check: ## smoke-check local-free LLM + SocratiCode infra
	@scripts/local-free-check.sh

up-prod: ## production override on Linux VM (needs secrets + rbac.yaml)
	@test -s secrets/hermes_api_key || (echo "decrypt secrets first"; exit 1)
	@test -f config/rbac.yaml || (echo "copy config/rbac.example.yaml → config/rbac.yaml"; exit 1)
	ADAPTER_DISPATCHER=hermes_api $(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml --profile agents --profile ingress up -d

phase3-check: ## Phase 3 smoke: router + adapters + pause control
	@scripts/phase3-check.sh

backup: ## D4.5: dump Postgres + tar named volumes → backups/<ts>
	@scripts/backup.sh

restore-drill: ## D4.5: non-destructive restore check (BACKUP=backups/<ts>)
	@test -n "$(BACKUP)" || (echo "usage: make restore-drill BACKUP=backups/<ts>"; exit 1)
	@scripts/restore.sh "$(BACKUP)" --drill

restore: ## D4.5: DESTRUCTIVE restore (BACKUP=backups/<ts>)
	@test -n "$(BACKUP)" || (echo "usage: make restore BACKUP=backups/<ts>"; exit 1)
	@scripts/restore.sh "$(BACKUP)"

worktree-clean: ## prune worktrees idle > 7 days (D2.4)
	@scripts/worktree-cleanup.sh

down: ## stop everything (keeps volumes)
	$(COMPOSE_LOCAL_FREE) --profile agents --profile ingress --profile onprem-llm --profile socraticode --profile single down
	$(COMPOSE) --profile agents --profile ingress --profile onprem-llm --profile socraticode --profile single down

logs: ## tail gateway + router + adapter logs
	$(COMPOSE) logs -f webhook-gateway router adapter-dev-backend

outbox: ## list prompts adapters produced in dryrun mode
	$(COMPOSE) exec adapter-dev-backend sh -c 'ls -1t /var/lib/queue-adapter/outbox | head -20'

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

.PHONY: help prereqs venv hooks secrets-init secrets-encrypt secrets-decrypt secrets-dev up up-agents hermes-seed up-ingress up-socraticode socraticode-check up-local-free local-llm-pull local-free-check up-prod phase3-check backup restore-drill restore worktree-clean down logs outbox ps migrate tunnel-setup tunnel-status gitlab-webhook gitlab-token-check hermes-configure skills-sync skills-check onboard test test-integration lint gitleaks webhook-test verify-phase0
