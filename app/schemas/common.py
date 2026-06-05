from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class StatusResponse(BaseModel):
    status: str
    message: str | None = None


class EventCaptureRequest(BaseModel):
    event_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    tenant_id: UUID | None = None
    user_id: UUID | None = None
    properties: dict = Field(default_factory=dict)


class OutcomeRequest(BaseModel):
    outcome_type: str
    properties: dict = Field(default_factory=dict)


class SecondPlaceAlertResponse(BaseModel):
    show: bool
    signal_type: str | None = None
    address: str | None = None
    claim_delta_minutes: int | None = None
