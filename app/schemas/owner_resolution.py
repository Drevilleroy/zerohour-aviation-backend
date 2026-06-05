from __future__ import annotations

from pydantic import BaseModel, Field


class OwnerResolutionRequest(BaseModel):
    address: str = Field(min_length=3)
    zip: str = Field(min_length=5, max_length=10)


class MailingAddress(BaseModel):
    line1: str
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None


class OwnerResolutionResponse(BaseModel):
    resolved: bool
    name: str | None = None
    mailing_address: MailingAddress | None = None

