SHELL := /bin/bash
.DEFAULT_GOAL := help
BACKEND := backend
FRONTEND := frontend

.PHONY: help install hooks dev dev-backend dev-frontend test test-live lint typecheck fmt build docker-up validate-content openapi eval

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm ci

hooks: ## Install pre-commit persistently and enable the git hook
	uv tool install pre-commit
	pre-commit install

dev: ## Run backend (:8000) and frontend (:5173) together
	@$(MAKE) -j2 --no-print-directory dev-backend dev-frontend

dev-backend: ## Run the FastAPI backend with reload on :8000
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Run the Vite dev server on :5173
	cd $(FRONTEND) && npm run dev

test: ## Unit and API tests (no real model)
	cd $(BACKEND) && uv run pytest
	cd $(FRONTEND) && npm test

test-live: ## Tests that need a real model endpoint
	cd $(BACKEND) && uv run pytest -m live

lint: ## ruff + eslint
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .
	cd $(FRONTEND) && npm run lint

typecheck: ## mypy (strict) + tsc
	cd $(BACKEND) && uv run mypy
	cd $(FRONTEND) && npm run typecheck

fmt: ## Auto-format and auto-fix
	cd $(BACKEND) && uv run ruff format . && uv run ruff check --fix .
	cd $(FRONTEND) && npx eslint . --fix

build: ## Build the frontend into frontend/dist
	cd $(FRONTEND) && npm run build

docker-up: ## Build and run the app container on :8000
	docker compose up --build

validate-content: ## Validate content YAML
	@echo "validate-content: added in M2"

openapi: ## Export OpenAPI schema and TS types
	@echo "openapi: added in M3"

eval: ## Run the evaluation harness
	@echo "eval: added in M7"
