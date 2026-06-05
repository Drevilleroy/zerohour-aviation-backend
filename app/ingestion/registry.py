from __future__ import annotations

from app.core.config import settings
from app.ingestion.adapters.base import IngestionAdapter
from app.ingestion.adapters.mock import MockSignalProvider


def get_provider_adapter(source: str | None = None) -> IngestionAdapter:
    provider_key = source or settings.provider_mode
    if provider_key in {"mock", "mock_provider", "seed_adapter", "simulated"}:
        return MockSignalProvider()
    raise ValueError(f"Unknown provider adapter: {provider_key}")
