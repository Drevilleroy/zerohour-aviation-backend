from __future__ import annotations

import json

from app.main import app


def test_consumer_api_schema_uses_zerohour_names_only() -> None:
    schema = json.dumps(app.openapi()).lower()

    assert "prophfesy" not in schema
    assert "disruption_probability" not in schema
    assert "balanced_score" not in schema
    assert "monitoring_confirmed" not in schema
    assert "zerohour_score" in schema
