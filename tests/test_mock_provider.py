from __future__ import annotations

import pytest

from app.ingestion.adapters.mock import MockSignalProvider


@pytest.mark.asyncio
async def test_mock_provider_is_deterministic() -> None:
    provider = MockSignalProvider()

    first = await provider.fetch_zip("90210")
    second = await provider.fetch_zip("90210")

    assert len(first) == len(second)
    assert first[0].subject_hash == second[0].subject_hash
    assert first[0].payload["demo"] is True

