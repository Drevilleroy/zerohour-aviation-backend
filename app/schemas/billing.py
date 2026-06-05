from __future__ import annotations

from pydantic import BaseModel, Field


class StripeWebhookPayload(BaseModel):
    id: str
    type: str
    data: dict = Field(default_factory=dict)


class PlanResponse(BaseModel):
    key: str
    interval: str
    territory_limit: int
    monthly_equivalent_cents: int

