from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

read_engine = create_engine(
    settings.database_replica_url or settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
ReadSessionLocal = sessionmaker(bind=read_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_read_db() -> Generator[Session, None, None]:
    db = ReadSessionLocal()
    try:
        yield db
    finally:
        db.close()
