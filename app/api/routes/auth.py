from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import TenantMembership, User
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from app.services.attribution import record_creator_referral
from app.services.provisioning import create_provisioning_job, create_user_tenant_membership
from app.tasks.provisioning import process_provisioning_job

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_202_ACCEPTED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> SignupResponse:
    try:
        user, tenant, membership = create_user_tenant_membership(
            db,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
        )
        job = create_provisioning_job(
            db,
            user=user,
            tenant=tenant,
            zip_codes=payload.zip_codes,
            creator_code=payload.creator_code,
        )
        record_creator_referral(db, creator_code=payload.creator_code, user=user, tenant=tenant)
        user.onboarding_state = "provisioning_queued"
        db.commit()
        db.refresh(job)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists") from exc

    process_provisioning_job.apply_async(args=[str(job.id)], queue="provisioning")
    token = create_access_token(user.id, tenant.id, membership.role)
    return SignupResponse(
        access_token=token,
        user_id=user.id,
        tenant_id=tenant.id,
        provisioning_job_id=job.id,
        onboarding_state=user.onboarding_state,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).one_or_none()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    membership = db.query(TenantMembership).filter(TenantMembership.user_id == user.id).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant membership")
    return LoginResponse(access_token=create_access_token(user.id, membership.tenant_id, membership.role))
