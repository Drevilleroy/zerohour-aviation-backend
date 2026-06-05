from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from html import unescape

import httpx
from sqlalchemy.orm import Session

from app.models import BrokerScore, Lane, Signal

SAFER_URL = "https://safer.fmcsa.dot.gov/query.asp"


@dataclass(frozen=True)
class BrokerHealth:
    mc_number: str
    name: str | None
    authority_revoked: bool = False
    insurance_lapsed: bool = False
    complaint_count: int = 0
    out_of_service_pct: Decimal = Decimal("0")
    inactive_90_days: bool = False


@dataclass(frozen=True)
class CarrierVerification:
    mc_number: str
    carrier_name: str
    authority_status: str
    home_base_city: str | None
    home_base_state: str | None
    home_base_zip: str | None
    equipment_type: str | None


class McVerificationError(ValueError):
    """Raised when a carrier MC cannot proceed through onboarding."""


def run_fmcsa_pipeline(db: Session, broker_mc_numbers: list[str] | None = None) -> dict:
    updated = 0
    for mc_number in broker_mc_numbers or []:
        health = _fetch_broker_health(mc_number)
        score = broker_health_score(health)
        broker_score = db.query(BrokerScore).filter(
            BrokerScore.broker_mc_number == health.mc_number
        ).one_or_none()
        if not broker_score:
            broker_score = BrokerScore(broker_mc_number=health.mc_number)
            db.add(broker_score)
        broker_score.broker_name = health.name
        broker_score.score = score
        broker_score.risk_level = risk_level(score)
        broker_score.fmcsa_status = "REVOKED" if health.authority_revoked else "ACTIVE"
        broker_score.complaint_count = health.complaint_count
        updated += 1
    _emit_capacity_signals(db)
    db.commit()
    return {"status": "completed", "broker_scores_updated": updated}


def broker_health_score(health: BrokerHealth) -> int:
    score = 100
    if health.authority_revoked:
        score -= 50
    if health.insurance_lapsed:
        score -= 30
    score -= health.complaint_count * 5
    if health.out_of_service_pct > Decimal("20"):
        score -= 20
    if health.inactive_90_days:
        score -= 10
    return max(0, min(100, score))


def risk_level(score: int) -> str:
    if score >= 80:
        return "GREEN"
    if score >= 50:
        return "YELLOW"
    return "RED"


def _fetch_broker_health(mc_number: str) -> BrokerHealth:
    with httpx.Client(timeout=20) as client:
        response = client.get(
            SAFER_URL,
            params={
                "searchtype": "ANY",
                "query_type": "queryCarrierSnapshot",
                "query_param": "MC_MX",
                "query_string": mc_number,
            },
        )
        response.raise_for_status()
        text = response.text.lower()
    return BrokerHealth(
        mc_number=mc_number,
        name=None,
        authority_revoked="revoked" in text,
        insurance_lapsed="insurance required" in text or "inactive" in text,
        complaint_count=text.count("complaint"),
        out_of_service_pct=Decimal("0"),
        inactive_90_days="no activity" in text,
    )


def verify_mc_number(mc_number: str) -> CarrierVerification:
    normalized_mc = _normalize_mc(mc_number)
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        response = client.get(
            SAFER_URL,
            params={"searchtype": "MC", "query": normalized_mc},
        )
        response.raise_for_status()

    text = _clean_html(response.text)
    lowered = text.lower()
    if any(marker in lowered for marker in ["record not found", "no records", "not found"]):
        raise McVerificationError("MC number not found")

    carrier_name = _first_match(
        text,
        [
            r"Legal Name:\s*([A-Z0-9 &'.,/-]+?)(?:\s{2,}| DBA Name:| Entity Type:)",
            r"Entity Name:\s*([A-Z0-9 &'.,/-]+?)(?:\s{2,}| DBA Name:| Entity Type:)",
        ],
    )
    authority_status = _first_match(
        text,
        [
            r"Operating Status:\s*([A-Z ]+?)(?:\s{2,}| Out of Service Date:)",
            r"Authority Status:\s*([A-Z ]+?)(?:\s{2,}|$)",
        ],
    )
    if not carrier_name:
        raise McVerificationError("MC number not found")
    if not _is_active_authority(authority_status):
        raise McVerificationError("authority inactive")

    city, state, zip_code = _parse_home_base(text)
    return CarrierVerification(
        mc_number=normalized_mc,
        carrier_name=carrier_name.title(),
        authority_status=authority_status or "ACTIVE",
        home_base_city=city.title() if city else None,
        home_base_state=state,
        home_base_zip=zip_code,
        equipment_type=_parse_equipment_type(text),
    )


def _emit_capacity_signals(db: Session) -> None:
    for lane in db.query(Lane).all():
        db.add(
            Signal(
                lane_id=lane.id,
                zip_code=lane.origin_zip,
                signal_type="CARRIER_CAPACITY",
                signal_value={"status": "awaiting FMCSA carrier lane mapping"},
                source="FMCSA",
                direction="NEUTRAL",
                weight=Decimal("0.20"),
                subject_hash=f"fmcsa-capacity:{lane.id}:{_bucket()}",
                confidence=Decimal("0.5000"),
                score=Decimal("0.20"),
                payload={"status": "awaiting FMCSA carrier lane mapping"},
            )
        )


def _bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _normalize_mc(mc_number: str) -> str:
    return re.sub(r"\D", "", mc_number)


def _clean_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :")
            if value:
                return value.upper()
    return None


def _is_active_authority(authority_status: str | None) -> bool:
    if not authority_status:
        return False
    status = authority_status.upper()
    if "INACTIVE" in status or "OUT-OF-SERVICE" in status or "REVOKED" in status:
        return False
    return "ACTIVE" in status or "AUTHORIZED" in status


def _parse_home_base(text: str) -> tuple[str | None, str | None, str | None]:
    address = _first_match(
        text,
        [
            r"Physical Address:\s*(.+?)(?:\s{2,}Phone:| Mailing Address:)",
            r"Address:\s*(.+?)(?:\s{2,}Phone:| Mailing Address:)",
        ],
    )
    if not address:
        return None, None, None

    match = re.search(r"\b([A-Z]{2})\s+(\d{5})(?:-\d{4})?", address)
    if not match:
        return None, None, None
    state = match.group(1)
    zip_code = match.group(2)
    prefix = address[: match.start()].strip(" ,")
    city = prefix.split(",")[-1].strip()
    if not city:
        return None, state, zip_code
    return city, state, zip_code


def _parse_equipment_type(text: str) -> str | None:
    cargo = _first_match(
        text,
        [
            r"Cargo Carried:\s*(.+?)(?:\s{2,}Operation Classification:|$)",
            r"Operation Classification:\s*(.+?)(?:\s{2,}|$)",
        ],
    )
    if not cargo:
        return None
    lowered = cargo.lower()
    if "refrigerated" in lowered or "reefer" in lowered:
        return "reefer"
    if "flatbed" in lowered:
        return "flatbed"
    if "tank" in lowered:
        return "tanker"
    return "van"
