from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import DirectMailCampaign, Letter
from app.services.audit import write_audit_log
from app.services.compliance import enforce_direct_mail_controls
from app.services.owner_resolution import fallback_letter_context, get_cached_letter_context


def create_direct_mail_campaign(
    db: Session,
    *,
    tenant_id,
    user_id,
    signal_ids,
    recipient_address_hashes: list[str],
    property_address: str | None,
    zip_code: str | None,
    template_key: str,
    metadata: dict,
) -> DirectMailCampaign:
    letter_context_mode = None
    if property_address and zip_code:
        letter_context = get_cached_letter_context(
            user_id=user_id,
            address=property_address,
            zip_code=zip_code,
        ) or fallback_letter_context(address=property_address, zip_code=zip_code)
        letter_context_mode = "resolved_owner_session" if letter_context.get("resolved") else "fallback_homeowner"

    enforce_direct_mail_controls(
        db,
        tenant_id=tenant_id,
        recipient_address_hashes=recipient_address_hashes,
    )
    credit_cost = len(recipient_address_hashes)
    campaign = DirectMailCampaign(
        tenant_id=tenant_id,
        user_id=user_id,
        status="queued",
        credit_cost=credit_cost,
        metadata_={
            "template_key": template_key,
            "recipient_count": len(recipient_address_hashes),
            "property_address": property_address,
            "zip": zip_code,
            "letter_context_mode": letter_context_mode,
            **metadata,
        },
    )
    db.add(campaign)
    db.flush()

    for index, address_hash in enumerate(recipient_address_hashes):
        signal_id = signal_ids[index] if index < len(signal_ids) else None
        db.add(
            Letter(
                campaign_id=campaign.id,
                signal_id=signal_id,
                status="queued",
                content_hash=f"{template_key}:{address_hash}",
                provider_payload={
                    "address_hash": address_hash,
                    "delivery_context": letter_context_mode,
                    "privacy": "owner_name_not_persisted",
                },
            )
        )

    write_audit_log(
        db,
        "direct_mail.campaign_queued",
        actor_user_id=user_id,
        entity_type="direct_mail_campaign",
        entity_id=str(campaign.id),
        metadata={"credit_cost": credit_cost, "template_key": template_key},
    )
    return campaign
