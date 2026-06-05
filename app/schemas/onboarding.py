from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class DreVerificationRequest(BaseModel):
    state: str
    license_number: str


class DreVerificationResponse(BaseModel):
    verification_id: UUID
    status: str
    message: str

