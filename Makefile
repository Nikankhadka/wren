.DEFAULT_GOAL := help

# Wren - central task runner. Thin dispatcher over existing scripts and commands.
# No target reimplements logic already in scripts/; multi-step logic stays there.

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_.-]+:.*## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── demo ───────────────────────────────────────────────────────────────────────

.PHONY: demo
demo: ## One-command demo: GoTrue + DB + migrate + seed + dev servers (see docs/DEMO.md)
	./scripts/demo.sh

# ── dev servers ─────────────────────────────────────────────────────────────────

.PHONY: dev
dev: ## Start backend + frontend dev servers concurrently (no GoTrue/seed; Ctrl-C to stop)
	@trap 'kill 0' EXIT INT TERM; \
	( cd backend && uv run uvicorn app.main:app --reload --port 8000 ) & \
	( cd frontend && npm run dev ) & \
	wait

.PHONY: dev-backend
dev-backend: ## Start backend dev server only (:8000)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

.PHONY: dev-frontend
dev-frontend: ## Start frontend dev server only (:3000)
	cd frontend && npm run dev

# ── database ────────────────────────────────────────────────────────────────────

.PHONY: db
db: ## Start the local Postgres + pgvector container
	docker compose up -d db

.PHONY: db-full
db-full: ## Start db + GoTrue auth + auth-proxy (demo-ready infra)
	docker compose up -d db auth auth-proxy

.PHONY: db-down
db-down: ## Stop and remove containers + volumes (tears out persistent data)
	docker compose down -v

# ── data ────────────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## Apply forward-only DB migrations
	cd backend && uv run python -m app.core.migrate

.PHONY: seed
seed: ## Seed the full demo world (two tenants, auth users, conversations)
	cd backend && uv run python -m seeds.seed_demo

.PHONY: seed-tenant1
seed-tenant1: ## Seed Tenant 1 (Bytefix phone repair) only
	cd backend && uv run python -m seeds.seed_tenant1_phoneshop

.PHONY: seed-tenant2
seed-tenant2: ## Seed Tenant 2 (dental clinic) via the public API (generalization proof)
	cd backend && uv run python -m seeds.seed_tenant2_dental

# ── install ─────────────────────────────────────────────────────────────────────

.PHONY: install
install: install-frontend install-backend ## Install all dependencies

.PHONY: install-frontend
install-frontend: ## Install frontend deps (npm ci)
	cd frontend && npm ci

.PHONY: install-backend
install-backend: ## Install backend deps (uv sync)
	cd backend && uv sync

# ── lint ────────────────────────────────────────────────────────────────────────

.PHONY: lint
lint: lint-frontend lint-backend ## Lint frontend + backend

.PHONY: lint-frontend
lint-frontend: ## Lint frontend (ESLint) + token guard
	cd frontend && npm run lint && npm run check:tokens

.PHONY: lint-backend
lint-backend: ## Lint backend (ruff)
	cd backend && uv run ruff check .

# ── format ──────────────────────────────────────────────────────────────────────

.PHONY: format
format: ## Auto-format backend code (ruff, writes changes)
	cd backend && uv run ruff format .

.PHONY: format-check
format-check: ## Check backend formatting without writing
	cd backend && uv run ruff format --check .

# ── typecheck ───────────────────────────────────────────────────────────────────

.PHONY: typecheck
typecheck: typecheck-frontend typecheck-backend ## Typecheck frontend + backend

.PHONY: typecheck-frontend
typecheck-frontend: ## Typecheck frontend (tsc --noEmit)
	cd frontend && npm run typecheck

.PHONY: typecheck-backend
typecheck-backend: ## Typecheck backend (mypy strict)
	cd backend && uv run mypy

# ── test ────────────────────────────────────────────────────────────────────────

.PHONY: test
test: test-frontend test-backend ## Run all unit tests

.PHONY: test-frontend
test-frontend: ## Run frontend unit tests (vitest)
	cd frontend && npm run test

.PHONY: test-backend
test-backend: ## Run backend tests (pytest)
	cd backend && uv run pytest

.PHONY: test-e2e
test-e2e: ## Run Playwright end-to-end tests
	cd frontend && npm run test:e2e

.PHONY: test-e2e-ui
test-e2e-ui: ## Run Playwright e2e tests with UI mode
	cd frontend && npm run test:e2e:ui

# ── eval ────────────────────────────────────────────────────────────────────────

.PHONY: eval
eval: ## Run the full eval gate (deterministic + LLM-judged)
	cd backend && uv run python -m evals.run_gate

.PHONY: eval-skip-llm
eval-skip-llm: ## Run deterministic eval gate only (skip LLM-judged evals)
	cd backend && uv run python -m evals.run_gate --skip-llm

# ── CI ──────────────────────────────────────────────────────────────────────────

.PHONY: check
check: lint typecheck test ## Fast local inner loop (lint + typecheck + test)

.PHONY: ci
ci: check format-check ## Run the CI pipeline locally (check + format-check + build)
	cd frontend && npm run build

.PHONY: ci-infra
ci-infra: ## Validate Terraform (fmt check + init + validate)
	cd infra && terraform fmt -check -recursive && terraform init -backend=false && terraform validate

.PHONY: ci-eval
ci-eval: ## Run eval gate standalone (needs LLM credentials for LLM-judged evals)
	cd backend && uv run python -m evals.run_gate

# ── clean ───────────────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove node_modules, venv cache, and __pycache__ (no Docker/volume touch)
	rm -rf frontend/node_modules
	rm -rf backend/.venv
	find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	uv cache clean 2>/dev/null || true
