# ============================================================================
# LeadGen AI Voice Agent - Makefile
# Production-ready commands for development and deployment
# ============================================================================

.PHONY: help install dev test lint format build deploy clean

# Default target
help:
	@echo "LeadGen AI Voice Agent - Available Commands"
	@echo "============================================"
	@echo ""
	@echo "Development:"
	@echo "  make install      - Install dependencies"
	@echo "  make dev          - Start development server"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format code"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate   - Run database migrations"
	@echo "  make db-upgrade   - Upgrade database"
	@echo "  make db-revision  - Create new migration"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-up    - Start all services"
	@echo "  make docker-down  - Stop all services"
	@echo "  make docker-logs  - View logs"
	@echo ""
	@echo "Production:"
	@echo "  make deploy       - Deploy to production"
	@echo "  make deploy-staging - Deploy to staging"
	@echo ""

# ============================================================================
# DEVELOPMENT
# ============================================================================

install:
	python -m pip install --upgrade pip
	pip install -e ".[dev,ml,monitoring]"
	pre-commit install
	playwright install chromium

dev:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-worker:
	celery -A app.worker worker --loglevel=debug --concurrency=2

dev-beat:
	celery -A app.worker beat --loglevel=debug

dev-flower:
	celery -A app.worker flower --port=5555

# ============================================================================
# TESTING
# ============================================================================

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

test-fast:
	pytest tests/ -v -x --ff

test-coverage:
	pytest tests/ --cov=app --cov-report=html
	open htmlcov/index.html

# ============================================================================
# CODE QUALITY
# ============================================================================

lint:
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

format:
	black app/ tests/
	isort app/ tests/
	ruff check app/ tests/ --fix

pre-commit:
	pre-commit run --all-files

# ============================================================================
# DATABASE
# ============================================================================

db-migrate:
	alembic revision --autogenerate -m "Auto migration"

db-upgrade:
	alembic upgrade head

db-downgrade:
	alembic downgrade -1

db-history:
	alembic history

db-revision:
	@read -p "Migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

# ============================================================================
# DOCKER
# ============================================================================

APP_VERSION ?= $(shell git rev-parse --short=8 HEAD)
LOCAL_IMAGE_REPOSITORY ?= leadgen-local/app

docker-build:
	docker build --build-arg APP_VERSION=$(APP_VERSION) -t $(LOCAL_IMAGE_REPOSITORY):$(APP_VERSION) -f Dockerfile.lock .

docker-build-dev:
	docker build --build-arg APP_VERSION=$(APP_VERSION) -t $(LOCAL_IMAGE_REPOSITORY):$(APP_VERSION) -f Dockerfile.lock .

# docker-compose.vps.yml is the CANONICAL production stack (AUDIT 2026-08-05);
# root docker-compose.yml was quarantined to deploy/legacy/ (bare `up` = prod-502).
COMPOSE := -f docker-compose.vps.yml

docker-up:
	APP_VERSION=$(APP_VERSION) APP_IMAGE_REPOSITORY=$(LOCAL_IMAGE_REPOSITORY) docker compose $(COMPOSE) --profile celery up -d

docker-up-prod:
	APP_VERSION=$(APP_VERSION) docker compose $(COMPOSE) --profile celery up -d

docker-down:
	APP_VERSION=$(APP_VERSION) docker compose $(COMPOSE) down

docker-logs:
	APP_VERSION=$(APP_VERSION) docker compose $(COMPOSE) logs -f

docker-logs-app:
	APP_VERSION=$(APP_VERSION) docker compose $(COMPOSE) logs -f app

docker-shell:
	APP_VERSION=$(APP_VERSION) docker compose $(COMPOSE) exec app /bin/bash

docker-clean:
	docker image prune -f
	docker builder prune -f --filter "unused-for=168h"

# ============================================================================
# PRODUCTION DEPLOYMENT
# ============================================================================

deploy-staging:
	@echo "Deploying to staging..."
	gcloud run deploy leadgen-ai-api-staging \
		--source . \
		--region asia-south1 \
		--platform managed \
		--allow-unauthenticated

deploy:
	@echo "Deploying to production..."
	git push origin main

deploy-terraform:
	cd infrastructure/terraform && \
	terraform init && \
	terraform plan -var-file="environments/production.tfvars" && \
	terraform apply -var-file="environments/production.tfvars" -auto-approve

# ============================================================================
# UTILITIES
# ============================================================================

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	find . -type d -name ".mypy_cache" -delete
	find . -type d -name "htmlcov" -delete
	find . -type f -name ".coverage" -delete
	rm -rf build/ dist/ *.egg-info/

logs:
	tail -f logs/*.log

shell:
	python -m IPython

scrape-test:
	python -c "from app.scripts.growth_engine import run_growth_engine; import asyncio; asyncio.run(run_growth_engine())"

# ============================================================================
# INFRASTRUCTURE
# ============================================================================

tf-init:
	cd infrastructure/terraform && terraform init

tf-plan:
	cd infrastructure/terraform && terraform plan -var-file="environments/production.tfvars"

tf-apply:
	cd infrastructure/terraform && terraform apply -var-file="environments/production.tfvars"

tf-destroy:
	cd infrastructure/terraform && terraform destroy -var-file="environments/production.tfvars"

# ============================================================================
# MONITORING
# ============================================================================

health:
	curl -s http://localhost:8000/health | python -m json.tool

metrics:
	curl -s http://localhost:8000/metrics

stats:
	curl -s http://localhost:8000/api/platform/stats | python -m json.tool

# ============================================================================
# PRODUCTION READINESS
# ============================================================================

validate:
	python scripts/validate_deployment.py --skip-tests

validate-strict:
	python scripts/validate_deployment.py --env production --strict

validate-full:
	python scripts/validate_deployment.py --env production

setup-secrets:
	@echo "Setting up secrets in GCP Secret Manager..."
	@read -p "GCP Project ID: " project; \
	python scripts/setup_secrets.py --project-id $$project --env production --interactive  # pragma: allowlist secret

setup-secrets-staging:
	@echo "Setting up staging secrets..."
	@read -p "GCP Project ID: " project; \
	python scripts/setup_secrets.py --project-id $$project --env staging --interactive  # pragma: allowlist secret

setup-secrets-dry-run:
	@echo "Dry run - checking what secrets would be created..."
	@read -p "GCP Project ID: " project; \
	python scripts/setup_secrets.py --project-id $$project --env production --dry-run  # pragma: allowlist secret

deploy-full:
	@echo "Retired: use scripts/deploy_vps.sh so production deploys one immutable SHA image."
	@exit 1
