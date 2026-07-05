from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import TenantMembership, User


@dataclass(frozen=True)
class RequestContext:
    user_id: UUID
    tenant_id: UUID
    role: str


def get_request_context(authorization: str | None = Header(default=None)) -> RequestContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return RequestContext(
            user_id=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            role=payload.get("role", "member"),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def get_optional_request_context(
    authorization: str | None = Header(default=None),
) -> RequestContext | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return get_request_context(authorization)


def require_admin(ctx: RequestContext = Depends(get_request_context)) -> RequestContext:
    if ctx.role not in {"admin", "owner"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return ctx


def get_current_user(
    db: Session = Depends(get_db), ctx: RequestContext = Depends(get_request_context)
) -> User:
    user = db.get(User, ctx.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    membership = (
        db.query(TenantMembership)
        .filter(TenantMembership.user_id == ctx.user_id, TenantMembership.tenant_id == ctx.tenant_id)
        .one_or_none()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    return user
