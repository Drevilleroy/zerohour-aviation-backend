from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DashboardResponse(BaseModel):
    tenant_id: UUID
    mode: str
    message: str | None = None
    zip_codes: list[str]
    signals: list[dict]
    generated_at: datetime | str | None = None


class ZipSignalsResponse(BaseModel):
    zip_code: str
    cache_status: str
    payload: dict
