from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import RequestContext, get_request_context
from app.db.session import get_db
from app.schemas.direct_mail import DirectMailCampaignRequest, DirectMailCampaignResponse
from app.services.compliance import ComplianceError
from app.services.direct_mail import create_direct_mail_campaign
from app.tasks.direct_mail import submit_direct_mail_campaign

router = APIRouter(prefix="/direct-mail", tags=["direct-mail"])


@router.get("/credits")
def credits() -> dict:
    return {"credits": 0, "mode": "feature_flagged"}


@router.post("/campaigns", response_model=DirectMailCampaignResponse)
def create_campaign(
    payload: DirectMailCampaignRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> DirectMailCampaignResponse:
    try:
        campaign = create_direct_mail_campaign(
            db,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            signal_ids=payload.signal_ids,
            recipient_address_hashes=payload.recipient_address_hashes,
            property_address=payload.property_address,
            zip_code=payload.zip,
            template_key=payload.template_key,
            metadata=payload.metadata,
        )
        db.commit()
    except ComplianceError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    submit_direct_mail_campaign.apply_async(args=[str(campaign.id)], queue="direct_mail")
    return DirectMailCampaignResponse(
        campaign_id=campaign.id,
        status=campaign.status,
        credit_cost=campaign.credit_cost,
        message="Campaign queued. Provider submission runs asynchronously.",
    )
