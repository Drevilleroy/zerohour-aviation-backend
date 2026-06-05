from __future__ import annotations

from app.services.dashboard import build_dashboard_snapshot


class EmptyQuery:
    def filter(self, *args):
        return self

    def all(self):
        return []


class EmptySession:
    def query(self, model):
        return EmptyQuery()


def test_dashboard_snapshot_empty_state() -> None:
    snapshot = build_dashboard_snapshot(
        EmptySession(),
        tenant_id="00000000-0000-0000-0000-000000000001",
        user_id="00000000-0000-0000-0000-000000000002",
    )

    assert snapshot["mode"] == "empty_state"
    assert snapshot["signals"] == []
    assert "Add ZIP codes" in snapshot["message"]

