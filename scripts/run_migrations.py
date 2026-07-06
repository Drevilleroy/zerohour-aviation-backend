from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import settings


MIGRATION_LOCK_ID = 707_048_2026


def main() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_engine(settings.database_url, pool_pre_ping=True, poolclass=NullPool)

    with engine.begin() as connection:
        connection.execute(text("select pg_advisory_xact_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


if __name__ == "__main__":
    main()
