SHELL := /bin/bash
.DEFAULT_GOAL := help
BACKEND := backend
FRONTEND := frontend

# Model routing. `make dev` uses .env (default: qwen3.5:9b for every role; no model swap).
# `make dev COACH=gpt-oss:20b` (or `make dev-strong-coach`) starts the backend with that coach
# and LLM_MAX_RETRIES=4 without editing .env: the bigger coach makes Ollama swap models at
# feedback time, and the extra retries absorb Ollama's occasional reload crash (HTTP 500).
STRONG_COACH := gpt-oss:20b
COACH ?=
COACH_ENV := $(if $(strip $(COACH)),LLM_MODEL_COACH=$(COACH) LLM_MAX_RETRIES=4)

.PHONY: help install hooks dev dev-strong-coach dev-backend dev-frontend chat test test-live lint typecheck fmt build docker-up validate-content content-schema openapi eval

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm ci

hooks: ## Install pre-commit persistently and enable the git hook
	uv tool install pre-commit
	pre-commit install

dev: ## Run backend (:8000) and frontend (:5173); COACH=<model> overrides the coach
	@$(MAKE) -j2 --no-print-directory dev-backend dev-frontend

dev-strong-coach: ## Same as `make dev COACH=gpt-oss:20b` (models swap at feedback time)
	@$(MAKE) --no-print-directory dev COACH=$(STRONG_COACH)

dev-backend: ## Run the FastAPI backend with reload on :8000 (accepts COACH= like dev)
	cd $(BACKEND) && $(COACH_ENV) uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Run the Vite dev server on :5173
	cd $(FRONTEND) && npm run dev

chat: ## Interview a client in the terminal: make chat CLIENT=<id> [DEBUG=1] [SCRIPT=path]
	@test -n "$(CLIENT)" || { echo "Usage: make chat CLIENT=<client-id> [DEBUG=1] [SCRIPT=path]" >&2; exit 2; }
	@uv run --project $(BACKEND) python scripts/chat.py --client "$(CLIENT)" $(if $(filter 1 true yes,$(DEBUG)),--debug) $(if $(SCRIPT),--script "$(SCRIPT)")

test: ## Unit and API tests (no real model)
	cd $(BACKEND) && uv run pytest
	cd $(FRONTEND) && npm test

test-live: ## Tests that need a real model endpoint
	cd $(BACKEND) && uv run pytest -m live

lint: ## ruff (backend/ and scripts/) + eslint
	cd $(BACKEND) && uv run ruff check . ../scripts && uv run ruff format --check . ../scripts
	cd $(FRONTEND) && npm run lint

typecheck: ## mypy (strict, backend/app and scripts/) + tsc
	cd $(BACKEND) && uv run mypy
	cd $(FRONTEND) && npm run typecheck

fmt: ## Auto-format and auto-fix
	cd $(BACKEND) && uv run ruff format . ../scripts && uv run ruff check --fix . ../scripts
	cd $(FRONTEND) && npx eslint . --fix

build: ## Build the frontend into frontend/dist
	cd $(FRONTEND) && npm run build

docker-up: ## Build and run the app container on :8000
	docker compose up --build

validate-content: ## Validate content/ YAML: prints the counts, or every error with its file and field
	@cd $(BACKEND) && uv run python -m app.content validate

content-schema: ## Regenerate content/schema/*.schema.json (editor autocomplete) from the models
	@cd $(BACKEND) && uv run python -m app.content schema

openapi: ## Write the API contract (openapi.json, error-codes.json) and the frontend's types
	@cd $(BACKEND) && uv run python -m app.api.openapi_export
	@cd $(FRONTEND) && npm run --silent gen:api

eval: ## Run the evaluation harness
	@echo "eval: added in M7"
