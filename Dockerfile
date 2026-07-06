FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app
COPY alembic ./alembic
COPY scripts ./scripts
COPY alembic.ini ./

CMD ["sh", "-c", "python scripts/run_migrations.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
