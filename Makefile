PYTHON ?= python3

.PHONY: help install install-api install-web dev-api dev-web migrate test test-api test-web lint lint-api lint-web format build sample doctor reset-data docker-up docker-verify docker-logs docker-down

help:
	@echo "GroundedPDF development commands"
	@echo "  make install        Install API and web dependencies"
	@echo "  make migrate        Apply database migrations"
	@echo "  make sample         Generate the synthetic sample PDF"
	@echo "  make doctor         Check the local environment"
	@echo "  make dev-api        Start FastAPI on port 8000"
	@echo "  make dev-web        Start Vite on port 5173"
	@echo "  make test           Run backend and frontend unit tests"
	@echo "  make lint           Run backend and frontend linters"
	@echo "  make format         Auto-format backend and frontend code"
	@echo "  make build          Build the production frontend"
	@echo "  make reset-data     Delete local data (guarded; prompts first)"
	@echo "  make docker-up      Build and start the Docker stack"
	@echo "  make docker-verify  Build, start, and smoke-test the Docker stack"
	@echo "  make docker-logs    Follow Docker service logs"
	@echo "  make docker-down    Stop the Docker stack (keeps data volume)"

install: install-api install-web

install-api:
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else ("GroundedPDF requires Python 3.12+ but found %s.%s. Set PYTHON=/path/to/python3.12 or newer." % sys.version_info[:2]))'
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/pip install -e "./apps/api[dev]"

install-web:
	npm --prefix apps/web install

migrate:
	.venv/bin/alembic -c apps/api/alembic.ini upgrade head

dev-api:
	.venv/bin/uvicorn --app-dir apps/api app.main:app --reload --port 8000

dev-web:
	npm --prefix apps/web run dev

test: test-api test-web

test-api:
	cd apps/api && ../../.venv/bin/pytest

test-web:
	npm --prefix apps/web test

lint: lint-api lint-web

lint-api:
	cd apps/api && ../../.venv/bin/ruff check . && ../../.venv/bin/ruff format --check . && ../../.venv/bin/mypy app

lint-web:
	npm --prefix apps/web run lint
	npm --prefix apps/web run format:check

format:
	cd apps/api && ../../.venv/bin/ruff check --fix . && ../../.venv/bin/ruff format .
	npm --prefix apps/web run format

build:
	npm --prefix apps/web run build

sample:
	.venv/bin/python scripts/generate_sample_pdf.py

doctor:
	.venv/bin/python scripts/doctor.py

reset-data:
	.venv/bin/python scripts/reset_local_data.py

docker-up:
	docker compose up --build --detach --wait --wait-timeout 300

docker-verify:
	docker compose config --quiet
	docker compose up --build --detach --wait --wait-timeout 300
	docker compose exec -T web wget -q -O /dev/null http://127.0.0.1:8080/healthz
	docker compose exec -T web wget -q -O /dev/null http://127.0.0.1:8080/api/v1/health
	docker compose exec -T web sh -ec 'worker=$$(find /usr/share/nginx/html/assets -name "pdf.worker*.mjs" -print -quit); test -n "$$worker"; wget -S -O /dev/null "http://127.0.0.1:8080/$${worker#/usr/share/nginx/html/}" 2>&1 | grep -qi "content-type: application/javascript"'
	docker compose exec -T api python -c "import os; raise SystemExit(os.geteuid() == 0)"

docker-down:
	docker compose down

docker-logs:
	docker compose logs --follow
