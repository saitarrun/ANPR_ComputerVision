.PHONY: help install up down logs migrate demo-webcam demo-iphone test test-unit test-int lint fmt bench clean

PYTHON ?= uv run python
COMPOSE ?= docker compose -f ops/docker-compose.yml

help:
	@echo "ANPR Make targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## uv sync deps
	uv sync

up: ## Start infra via OrbStack (postgres, redis, minio, prometheus, grafana)
	$(COMPOSE) up -d
	@echo "Postgres: localhost:5432 | Redis: localhost:6379 | MinIO console: http://localhost:9001 | Grafana: http://localhost:3001"

down: ## Stop infra
	$(COMPOSE) down

logs: ## Tail infra logs
	$(COMPOSE) logs -f --tail=100

migrate: ## Run Alembic migrations
	$(PYTHON) -m alembic -c db/alembic.ini upgrade head

demo-webcam: ## Live laptop-camera plate detection
	$(PYTHON) -m scripts.demo --source webcam

demo-iphone: ## Live iPhone (Continuity Camera or RTSP) plate detection
	$(PYTHON) -m scripts.demo --source iphone

smoke-webcam: ## Verify cv2.VideoCapture sees the laptop camera
	$(PYTHON) scripts/smoke_webcam.py

test: test-unit test-int ## Run all tests

test-unit:
	$(PYTHON) -m pytest tests/unit -q

test-int:
	$(PYTHON) -m pytest tests/integration -q

lint: ## Ruff + mypy
	uv run ruff check .
	uv run mypy anpr_core api ingest workers db

fmt: ## Ruff format
	uv run ruff format .
	uv run ruff check --fix .

bench: ## Accuracy + latency benchmark
	$(PYTHON) benchmarks/eval.py --set golden_in_small

clean: ## Remove caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache

m2-setup: ## M2: Initialize detector fine-tuning (golden sets + configs)
	$(PYTHON) benchmarks/golden_sets.py
	@echo "✓ Golden sets initialized"
	@echo "Next: python training/data/prepare_splits.py --cache ~/.cache/anpr-datasets"

m2-baseline: ## M2: Train baseline detector (10 epochs, CCPD only)
	$(PYTHON) training/scripts/train_detector_m2.py --phase baseline

m2-full: ## M2: Full detector fine-tuning (100 epochs, CCPD + synthetic)
	$(PYTHON) training/scripts/train_detector_m2.py --phase full

m2-train: ## M2: Complete training (baseline + full)
	$(PYTHON) training/scripts/train_detector_m2.py --phase all

m2-eval: ## M2: Evaluate detector on golden sets
	$(PYTHON) benchmarks/eval_m2.py --set golden_in_small --quick

m2-mlflow: ## M2: View MLflow UI (training metrics)
	mlflow ui
