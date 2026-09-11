.DEFAULT_GOAL := help

# Agencx - central task runner, styled after the monorepo sample: simple verbs,
# green banners, thin bodies. Everything runs in containers (F-3) - the host
# needs only Docker. No target reimplements logic already in scripts/; multi-
# step logic stays in scripts/dev.sh and scripts/up-infra.sh.

# --- shared --------------------------------------------------------------------
DC  := docker compose
DCP := docker compose --profile mail --profile dbui --profile e2e
BE  := $(DC) run --rm backend
BE_ := $(DC) run --rm --no-deps backend
FE  := $(DC) run --rm frontend
FE_ := $(DC) run --rm --no-deps frontend
# Whether a model provider is actually reachable, answered on the host and
# handed to the runner as a yes/no. The two paste-a-link specs drive the real
# URL ingest, which calls the provider to turn a page into sections - with no
# key they can only time out, which is exactly what they did the first time the
# suite ran in CI. The key lives in backend/.env, the file the backend
# container reads, and not in the host environment or the root .env, so a
# compose interpolation would read "unconfigured" on a developer's machine too.
# The container gets the answer, never the key. This is the same gate the eval
# job already uses in .github/workflows/ci.yml (`if [ -n "${LLM_API_KEY}" ]`).
E2E_LLM := $(shell grep -qs '^LLM_API_KEY=.' backend/.env && echo 1)
E2E := $(DC) --profile e2e run --rm -e E2E_LLM=$(E2E_LLM) e2e
# Loopback mirrors of the stack. The browser bundle inlines absolute origins
# (NEXT_PUBLIC_API_URL=http://localhost:8000, NEXT_PUBLIC_SUPABASE_URL=
# http://localhost:54321), and inside this container localhost is the container
# itself - so the e2e runner forwards its own 3000/8000/54321 to the compose
# services and every spec URL behaves exactly as it does on the host. 8025
# mirrors Mailpit's web UI - auth-helpers.ts reads the OTP code straight out of
# its API to log in.
E2E_NET := sh -c 'socat TCP-LISTEN:3000,fork,reuseaddr,bind=127.0.0.1 TCP:frontend:3000 & socat TCP-LISTEN:8000,fork,reuseaddr,bind=127.0.0.1 TCP:backend:8000 & socat TCP-LISTEN:54321,fork,reuseaddr,bind=127.0.0.1 TCP:auth-proxy:80 & socat TCP-LISTEN:8025,fork,reuseaddr,bind=127.0.0.1 TCP:mailpit:8025 & exec "$$@"' --

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_.-]+:.*## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── dev ────────────────────────────────────────────────────────────────────────

.PHONY: demo
demo: ## One-command demo: full stack + migrate + seed (see docs/agencx/running.md)
	@printf "\033[0;32m>>> Starting demo stack\033[0m\n"
	./scripts/dev.sh --seed

.PHONY: dev
dev: ## Start the full dev environment (all containers): infra + migrate, no seed
	@printf "\033[0;32m>>> Starting dev stack\033[0m\n"
	./scripts/dev.sh

.PHONY: run
run: dev ## Alias of dev

.PHONY: dev-backend
dev-backend: ## Start the backend container only (:8000)
	@printf "\033[0;32m>>> Starting backend\033[0m\n"
	$(DC) up -d backend

.PHONY: dev-frontend
dev-frontend: ## Start the frontend container only (:3000)
	@printf "\033[0;32m>>> Starting frontend\033[0m\n"
	$(DC) up -d frontend

.PHONY: dev-reset
dev-reset: ## Wipe the frontend build cache and restart it (a new theme token has no effect)
	@printf "\033[0;32m>>> Clearing the frontend build cache\033[0m\n"
	$(FE_) find /app/.next -mindepth 1 -delete
	$(DC) restart frontend

.PHONY: stop
stop: ## Stop all containers (data survives - volumes are kept)
	@printf "\033[0;32m>>> Stopping all services\033[0m\n"
	$(DCP) down --remove-orphans

.PHONY: clean
clean: ## Full reset: containers + volumes (db data, deps, model cache) + dev images
	@printf "\033[0;32m>>> Cleaning everything\033[0m\n"
	$(DCP) down -v --remove-orphans --rmi local

# ── install ────────────────────────────────────────────────────────────────────

.PHONY: install
install: ## Install all dependencies into their container volumes
	@printf "\033[0;32m>>> Installing dependencies\033[0m\n"
	$(DC) build backend frontend
	$(BE_) uv sync --frozen
	$(FE_) npm ci
	$(E2E) sh -c "[ -d node_modules/@playwright ] || npm ci"

# ── database & infra ───────────────────────────────────────────────────────────

.PHONY: db
db: ## Start the Postgres + pgvector container
	$(DC) up -d db

.PHONY: services
services: ## Start local services only: db + GoTrue auth + auth-proxy
	./scripts/up-infra.sh

.PHONY: services.stop
services.stop: ## Stop local services (alias of stop)
	$(MAKE) stop

.PHONY: db-full
db-full: ## Start db + GoTrue auth + auth-proxy (demo-ready infra)
	./scripts/up-infra.sh

.PHONY: mail
mail: ## Start Mailpit inbox for login-in-chat OTP codes (SMTP :1025, UI :8025)
	$(DC) up -d mailpit
	@echo "  inbox: http://localhost:8025 (make dev/demo start this automatically too - GoTrue's auth service depends on it)"

.PHONY: dbui
dbui: ## Start pgweb DB browser (UI :8081)
	$(DC) --profile dbui up -d pgweb
	@echo "  db ui: http://localhost:8081 (postgres/postgres, database wren)"

.PHONY: db-down
db-down: ## Stop and remove containers + volumes (tears out persistent data)
	$(DCP) down -v --remove-orphans

# ── data ───────────────────────────────────────────────────────────────────────
# Every `docker compose run backend ...` brings its dependencies up first
# (backend depends_on db healthy), so migrate/seed work standalone.

.PHONY: migrate
migrate: ## Apply forward-only DB migrations
	@printf "\033[0;32m>>> Migrating\033[0m\n"
	$(BE) python -m app.shared.migrate

.PHONY: seed
seed: migrate ## Seed the full demo world (two tenants, auth users, conversations)
	@printf "\033[0;32m>>> Seeding\033[0m\n"
	$(BE) python -m seeds.seed_demo

.PHONY: seed-tenant1
seed-tenant1: migrate ## Seed Tenant 1 (Bytefix phone repair) only - no auth users
	$(BE) python -m seeds.seed_tenant1_phoneshop

.PHONY: seed-tenant2
seed-tenant2: ## Seed Tenant 2 via the public API - NEEDS the stack up (make dev)
	$(BE) python -m seeds.seed_tenant2_dental --api-base http://backend:8000

# ── lint & format ──────────────────────────────────────────────────────────────

.PHONY: lint
lint: lint-frontend lint-backend ## Lint frontend + backend

.PHONY: lint-backend
lint-backend: ## Lint backend (ruff + import boundary)
	$(BE_) ruff check .
	$(BE_) lint-imports

.PHONY: lint-frontend
lint-frontend: ## Lint frontend (ESLint + token guard)
	$(FE_) npm run lint && $(FE_) npm run check:tokens

.PHONY: lint.fix
lint.fix: ## Autofix lint + formatting issues (ruff fix/format, eslint --fix)
	@printf "\033[0;32m>>> Fixing lint\033[0m\n"
	$(BE_) sh -c "ruff check --fix . && ruff format ."
	$(FE_) npm run lint -- --fix

.PHONY: format
format: ## Auto-format backend code (ruff, writes changes)
	$(BE_) ruff format .

.PHONY: format-check
format-check: ## Check backend formatting without writing
	$(BE_) ruff format --check .

# ── typecheck ──────────────────────────────────────────────────────────────────

.PHONY: typecheck
typecheck: typecheck-frontend typecheck-backend ## Typecheck frontend + backend

.PHONY: typecheck-frontend
typecheck-frontend: ## Typecheck frontend (tsc --noEmit)
	$(FE_) npm run typecheck

.PHONY: typecheck-backend
typecheck-backend: ## Typecheck backend (mypy strict)
	$(BE_) mypy

# ── test ───────────────────────────────────────────────────────────────────────

.PHONY: test
test: test-frontend test-backend ## Run all unit tests

.PHONY: test-frontend
test-frontend: ## Run frontend unit tests (vitest)
	$(FE_) npm run test

# No --no-deps on purpose: tests marked db need live Postgres, and compose run
# starts the backend service's depends_on chain (db healthy) automatically.
.PHONY: test-backend
test-backend: ## Run backend tests (pytest)
	$(BE) pytest

.PHONY: test-e2e
test-e2e: ## Run Playwright e2e in a container - NEEDS the stack up (make dev && make seed)
	@[ -n "$(E2E_LLM)" ] || printf "\033[0;33m  ! LLM_API_KEY is empty in backend/.env - the two paste-a-link specs skip (see E2E_LLM above)\033[0m\n"
	$(E2E) $(E2E_NET) npm run test:e2e

.PHONY: test-e2e-ui
test-e2e-ui: ## Playwright e2e UI mode (report at localhost:9323 while running)
	$(E2E) $(E2E_NET) npm run test:e2e:ui

# ── eval ───────────────────────────────────────────────────────────────────────

.PHONY: eval
eval: ## Run the full eval gate (deterministic + LLM-judged) - NEEDS make seed-tenant1 first
	$(BE) python -m evals.run_gate

.PHONY: eval-skip-llm
eval-skip-llm: ## Deterministic eval gate only (skip LLM-judged) - NEEDS make seed-tenant1 first
	$(BE) python -m evals.run_gate --skip-llm

# ── build & CI ─────────────────────────────────────────────────────────────────

.PHONY: build
build: ## Build the frontend (next build) inside its container
	@printf "\033[0;32m>>> Building frontend\033[0m\n"
	$(FE_) npm run build

.PHONY: check
check: lint typecheck test ## Fast inner loop (lint + typecheck + test)

.PHONY: ci
ci: check format-check build ## Run the CI pipeline locally
	@printf "\033[0;32m>>> CI complete\033[0m\n"

.PHONY: ci-infra
ci-infra: ## Validate Terraform (fmt check + init + validate)
	cd infra && terraform fmt -check -recursive && terraform init -backend=false && terraform validate

.PHONY: ci-eval
ci-eval: ## Run eval gate standalone (needs LLM credentials for LLM-judged evals)
	$(BE) python -m evals.run_gate
