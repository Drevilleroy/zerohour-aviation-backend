from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ProvisioningJob, Tenant, TenantMembership, Territory, User
from app.services.audit import write_audit_log


def normalize_zip_codes(zip_codes: list[str]) -> list[str]:
    normalized = []
    for zip_code in zip_codes:
        cleaned = "".join(ch for ch in zip_code if ch.isdigit())[:5]
        if len(cleaned) == 5 and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def create_provisioning_job(
    db: Session,
    *,
    user: User,
    tenant: Tenant,
    zip_codes: list[str],
    creator_code: str | None,
) -> ProvisioningJob:
    normalized_zips = normalize_zip_codes(zip_codes)
    job = ProvisioningJob(
        tenant_id=tenant.id,
        user_id=user.id,
        requested_zips={"zip_codes": normalized_zips, "creator_code": creator_code},
        status="queued",
        message="Provisioning queued. Dashboard cache will fill as territory data loads.",
    )
    db.add(job)
    write_audit_log(
        db,
        "provisioning.job_created",
        actor_user_id=user.id,
        entity_type="provisioning_job",
        entity_id=str(job.id),
        metadata={"zip_codes": normalized_zips, "creator_code": creator_code},
    )
    return job


def apply_provisioning_job(db: Session, job: ProvisioningJob) -> None:
    job.status = "processing"
    job.attempts += 1
    zip_codes = job.requested_zips.get("zip_codes", [])
    for zip_code in zip_codes:
        exists = (
            db.query(Territory)
            .filter(Territory.tenant_id == job.tenant_id, Territory.zip_code == zip_code)
            .one_or_none()
        )
        if not exists:
            db.add(Territory(tenant_id=job.tenant_id, zip_code=zip_code))
    job.status = "ready"
    job.message = "Initial dashboard is ready. Additional intelligence may continue processing."
    user = db.get(User, job.user_id)
    if user:
        user.onboarding_state = "dashboard_ready"
    write_audit_log(
        db,
        "provisioning.job_completed",
        actor_user_id=job.user_id,
        entity_type="provisioning_job",
        entity_id=str(job.id),
        metadata={"zip_count": len(zip_codes)},
    )


def create_user_tenant_membership(db: Session, *, email: str, hashed_password: str, full_name: str | None):
    user = User(email=email.lower(), hashed_password=hashed_password, full_name=full_name)
    tenant = Tenant(name=full_name or email, tenant_type="agent")
    db.add_all([user, tenant])
    db.flush()
    membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db.add(membership)
    return user, tenant, membership

