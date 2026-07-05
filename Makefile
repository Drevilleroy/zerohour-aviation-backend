.PHONY: install dev migrate worker beat test lint seed openapi

install:
	python -m pip install -r requirements-dev.txt

dev:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

migrate:
	alembic upgrade head

worker:
	celery -A app.workers.celery_app worker --loglevel=INFO -Q aviation,provisioning,ingestion,normalization,scoring,cache,notifications,direct_mail,billing,analytics,admin

beat:
	celery -A app.workers.celery_app beat --loglevel=INFO

test:
	pytest tests

lint:
	ruff check app tests

seed:
	python scripts/seed_operational_defaults.py

openapi:
	python scripts/export_openapi.py
