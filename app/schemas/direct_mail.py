from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class DirectMailCampaignRequest(BaseModel):
    signal_ids: list[UUID] = Field(default_factory=list, max_length=250)
    recipient_address_hashes: list[str] = Field(default_factory=list, max_length=250)
    property_address: str | None = None
    zip: str | None = None
    template_key: str = "seller_signal_intro"
    metadata: dict = Field(default_factory=dict)


class DirectMailCampaignResponse(BaseModel):
    campaign_id: UUID
    status: str
    credit_cost: int
    message: str
