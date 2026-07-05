from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, seconds: int) -> None:
        return None


def test_health_is_open_in_production_even_with_untrusted_host(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "environment", "production")

    client = TestClient(main.app, base_url="http://testserver")
    response = client.get("/health", headers={"host": "untrusted.example"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_backup_rate_limit_blocks_after_configured_limit(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "backup_rate_limit_enabled", True)
    monkeypatch.setattr(main.settings, "auth_register_rate_limit_per_hour", 1)
    monkeypatch.setattr(main, "redis_client", FakeRedis())

    client = TestClient(main.app)

    first = client.post("/auth/register")
    second = client.post("/auth/register")

    assert first.status_code != 429
    assert second.status_code == 429
    assert second.json() == {"detail": "Rate limit exceeded"}
