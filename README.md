# ZEROHOUR REALTOR PULSE Backend

Production-oriented FastAPI backend scaffold for ZEROHOUR REALTOR PULSE(TM), a cache-first real estate signal intelligence platform.

The architecture is intentionally lean for MVP deployment while preserving scale paths for viral signup spikes, async provisioning, cached dashboards, scheduled ingestion, direct mail, creator attribution, compliance controls, and operational kill switches.

Start with:

```bash
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_operational_defaults.py
```

Core services:

- `api`: FastAPI application
- `worker`: Celery background workers
- `beat`: Celery scheduled jobs
- `postgres`: relational source of truth
- `redis`: cache, broker, rate-limit state

Architecture details live in [docs/architecture.md](/Users/drevilleroy/Documents/ZeroHour%20Property%20pulse%20backend/docs/architecture.md).
Local development details live in [docs/local_development.md](/Users/drevilleroy/Documents/ZeroHour%20Property%20pulse%20backend/docs/local_development.md).
Frontend integration details live in [docs/frontend_api_contract.md](/Users/drevilleroy/Documents/ZeroHour%20Property%20pulse%20backend/docs/frontend_api_contract.md).

Useful local commands:

```bash
make migrate
make seed
make test
```
