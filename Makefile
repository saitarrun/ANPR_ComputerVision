.PHONY: help docker-build docker-up docker-down docker-logs docker-clean docker-test docker-shell

# Colors for terminal output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(GREEN)ANPR Backend Development Commands$(NC)\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-25s$(NC) %s\n", $$1, $$2}'
	@echo "\n$(YELLOW)Docker Compose Flags:$(NC)"
	@echo "  DEV=1          Use development stack (default)"
	@echo "  PROD=1         Use production overrides"

# ---- Docker Compose ----

docker-up: ## Start Docker Compose stack (dev by default)
	@echo "$(GREEN)Starting ANPR stack...$(NC)"
	@if [ "$(PROD)" = "1" ]; then \
		docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d; \
		echo "$(GREEN)Production stack started$(NC)"; \
	else \
		docker-compose up -d; \
		echo "$(GREEN)Development stack started$(NC)"; \
	fi
	@sleep 3 && make docker-health

docker-down: ## Stop and remove Docker Compose stack
	@echo "$(YELLOW)Stopping ANPR stack...$(NC)"
	docker-compose down
	@echo "$(GREEN)Stack stopped$(NC)"

docker-down-v: ## Stop stack and remove volumes (WARNING: deletes data)
	@echo "$(RED)Removing stack and volumes...$(NC)"
	docker-compose down -v
	@echo "$(GREEN)Stack and volumes removed$(NC)"

docker-logs: ## Follow logs from all services (ctrl+c to stop)
	docker-compose logs -f

docker-logs-api: ## Follow logs from API service
	docker-compose logs -f api

docker-logs-worker: ## Follow logs from Celery worker
	docker-compose logs -f celery-worker

docker-logs-db: ## Follow logs from PostgreSQL
	docker-compose logs -f postgres

docker-health: ## Check health status of all services
	@echo "$(GREEN)Service Status:$(NC)"
	@docker-compose ps --services | while read service; do \
		status=$$(docker-compose ps $$service | tail -1 | awk '{print $$NF}'); \
		if echo "$$status" | grep -q healthy || echo "$$status" | grep -q "Up"; then \
			echo "  $(GREEN)✓$(NC) $$service ($$status)"; \
		else \
			echo "  $(RED)✗$(NC) $$service ($$status)"; \
		fi; \
	done

docker-rebuild: ## Rebuild Docker images without cache
	@echo "$(YELLOW)Rebuilding Docker images...$(NC)"
	docker-compose build --no-cache
	@echo "$(GREEN)Images rebuilt$(NC)"

docker-shell: ## Open shell in API container
	@docker-compose exec api /bin/bash

docker-db-shell: ## Open psql shell in PostgreSQL container
	@docker-compose exec postgres psql -U $${POSTGRES_USER:-anpr} -d $${POSTGRES_DB:-anpr}

docker-redis-cli: ## Open Redis CLI
	@docker-compose exec redis redis-cli

# ---- Database ----

db-migrate: ## Run Alembic migrations
	@echo "$(GREEN)Running migrations...$(NC)"
	docker-compose exec api alembic upgrade head
	@echo "$(GREEN)Migrations complete$(NC)"

db-migrate-create: ## Create new Alembic migration (requires MESSAGE=...)
	@if [ -z "$(MESSAGE)" ]; then \
		echo "$(RED)Error: MESSAGE not provided. Usage: make db-migrate-create MESSAGE='Add user table'$(NC)"; \
		exit 1; \
	fi
	docker-compose exec api alembic revision --autogenerate -m "$(MESSAGE)"

db-seed: ## Populate database with seed data
	@echo "$(GREEN)Seeding database...$(NC)"
	docker-compose exec api python -m scripts.seed_db
	@echo "$(GREEN)Database seeded$(NC)"

db-reset: ## Drop and recreate database (WARNING: deletes all data)
	@echo "$(RED)Dropping database...$(NC)"
	docker-compose exec postgres psql -U $${POSTGRES_USER:-anpr} -d postgres -c "DROP DATABASE IF EXISTS $${POSTGRES_DB:-anpr};"
	docker-compose exec postgres psql -U $${POSTGRES_USER:-anpr} -d postgres -c "CREATE DATABASE $${POSTGRES_DB:-anpr};"
	@make db-migrate
	@echo "$(GREEN)Database reset$(NC)"

# ---- Testing ----

test: ## Run all tests
	@echo "$(GREEN)Running tests...$(NC)"
	docker-compose exec api pytest -v

test-unit: ## Run unit tests only
	docker-compose exec api pytest tests/unit -v

test-integration: ## Run integration tests (requires running stack)
	docker-compose exec api pytest tests/integration -v

test-e2e: ## Run end-to-end tests (requires running stack)
	docker-compose exec api pytest tests/e2e -v

test-cov: ## Run tests with coverage report
	docker-compose exec api pytest --cov=api --cov=workers --cov=db --cov-report=html

# ---- Linting & Type Checking ----

lint: ## Run linters (ruff, mypy)
	@echo "$(GREEN)Running linters...$(NC)"
	docker-compose exec api ruff check . --fix
	docker-compose exec api mypy api workers db

format: ## Format code (ruff)
	docker-compose exec api ruff format .

check: ## Run all checks (lint + type check)
	docker-compose exec api ruff check .
	docker-compose exec api mypy api workers db
	@echo "$(GREEN)All checks passed$(NC)"

# ---- Image Building for CI/CD ----

image-build: ## Build Docker image locally
	./scripts/docker-build.sh

image-build-push: ## Build and push Docker image to registry
	./scripts/docker-build.sh --push

image-build-tag: ## Build and tag Docker image (requires TAG=...)
	@if [ -z "$(TAG)" ]; then \
		echo "$(RED)Error: TAG not provided. Usage: make image-build-tag TAG=v0.1.0$(NC)"; \
		exit 1; \
	fi
	./scripts/docker-build.sh --tag $(TAG) --push

# ---- Cleanup ----

docker-clean: ## Remove stopped containers and dangling images
	@echo "$(YELLOW)Cleaning up Docker artifacts...$(NC)"
	docker system prune -f
	@echo "$(GREEN)Cleanup complete$(NC)"

docker-clean-all: ## Remove all unused Docker resources (⚠️ aggressive)
	@echo "$(RED)Removing all unused Docker resources...$(NC)"
	docker system prune -a --volumes -f
	@echo "$(GREEN)Aggressive cleanup complete$(NC)"

# ---- Development Setup ----

setup: ## Initialize local development environment
	@echo "$(GREEN)Setting up development environment...$(NC)"
	@[ -f .env.local ] || cp .env.example .env.local
	@echo "$(YELLOW)→ Created .env.local (edit with your secrets)$(NC)"
	@make docker-up
	@make db-migrate
	@make db-seed
	@echo "$(GREEN)Setup complete! API running at http://localhost:8000/docs$(NC)"

reset: ## Full reset (stop stack, remove volumes, setup)
	@make docker-down-v
	@make setup

.DEFAULT_GOAL := help
