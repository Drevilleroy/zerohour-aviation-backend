web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: celery -A app.workers.celery_app worker --loglevel=INFO -Q aviation,freight,ingestion,analytics,cache,billing,notifications,direct_mail,provisioning
beat: celery -A app.workers.celery_app beat --loglevel=INFO
