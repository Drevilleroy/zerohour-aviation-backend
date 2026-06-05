from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import RequestContext, get_request_context
from app.db.session import get_db
from app.models import ProvisioningJob
from app.schemas.onboarding import DreVerificationRequest, DreVerificationResponse
from app.services.dre import submit_dre_verification

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/provisioning/{job_id}")
def provisioning_status(
    job_id: UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> dict:
    job = db.get(ProvisioningJob, job_id)
    if not job or job.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Provisioning job not found")
    return {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "requested_zips": job.requested_zips.get("zip_codes", []),
    }


@router.post("/dre-verification", response_model=DreVerificationResponse)
def dre_verification(
    payload: DreVerificationRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> DreVerificationResponse:
    from app.models import User

    user = db.get(User, ctx.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    verification = submit_dre_verification(
        db,
        user=user,
        state=payload.state,
        license_number=payload.license_number,
    )
    db.commit()
    return DreVerificationResponse(
        verification_id=verification.id,
        status=verification.status,
        message="DRE verification queued. Dashboard access can remain in limited mode while processing.",
    )
