from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    full_name: str | None = None
    zip_codes: list[str] = Field(default_factory=list, max_length=20)
    creator_code: str | None = None


class SignupResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    tenant_id: UUID
    provisioning_job_id: UUID
    onboarding_state: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

