from __future__ import annotations

from app.services.provisioning import normalize_zip_codes


def test_normalize_zip_codes_dedupes_and_filters() -> None:
    assert normalize_zip_codes([" 90210 ", "90210-1234", "abc", "10001"]) == ["90210", "10001"]

