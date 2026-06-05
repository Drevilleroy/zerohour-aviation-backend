from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.models import Lane, Signal

PORT_SOURCES = {
    "Port of Los Angeles": "https://www.portoflosangeles.org/business/statistics",
    "Port of Long Beach": "https://polb.com/economics/stats",
    "Port of Houston": "https://porthouston.com/business/economic-development/statistics/",
    "Port of Savannah": "https://gaports.com/facilities/port-of-savannah/",
    "Port of NY/NJ": "https://www.panynj.gov/port/en/our-port/facts-and-figures.html",
}


def run_port_scraper(db: Session) -> dict:
    port_changes = _scrape_port_changes()
    if not port_changes:
        return {"status": "skipped", "reason": "no TEU volume changes parsed"}

    created = 0
    for lane in db.query(Lane).all():
        source, wow_change = max(port_changes.items(), key=lambda item: abs(item[1]))
        direction, weight = port_signal(wow_change)
        db.add(
            Signal(
                lane_id=lane.id,
                zip_code=lane.origin_zip,
                signal_type="PORT_VOLUME",
                signal_value={"port": source, "week_over_week_change_pct": str(wow_change)},
                source=source,
                direction=direction,
                weight=weight,
                subject_hash=f"port:{lane.id}:{source}:{_bucket()}",
                confidence=Decimal("0.7600"),
                score=weight,
                payload={"port": source, "week_over_week_change_pct": str(wow_change)},
            )
        )
        created += 1
    db.commit()
    return {"status": "completed", "signals_created": created, "ports_checked": len(port_changes)}


def port_signal(wow_change_pct: Decimal) -> tuple[str, Decimal]:
    if wow_change_pct > Decimal("15"):
        return "STRONG_UP", Decimal("0.35")
    if wow_change_pct >= Decimal("5"):
        return "MODERATE_UP", Decimal("0.20")
    if wow_change_pct < Decimal("0"):
        return "DOWN", Decimal("0.25")
    return "NEUTRAL", Decimal("0.10")


def _scrape_port_changes() -> dict[str, Decimal]:
    changes: dict[str, Decimal] = {}
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for source, url in PORT_SOURCES.items():
            response = client.get(url)
            response.raise_for_status()
            parsed = _parse_teu_change(response.text)
            if parsed is not None:
                changes[source] = parsed
    return changes


def _parse_teu_change(html: str) -> Decimal | None:
    text = re.sub(r"\s+", " ", html)
    percent_matches = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
    if percent_matches:
        return Decimal(percent_matches[0])
    teu_matches = [
        Decimal(match.replace(",", ""))
        for match in re.findall(r"(\d[\d,]{4,})\s+TEU", text, flags=re.I)
    ]
    if len(teu_matches) >= 2 and teu_matches[1] != 0:
        return ((teu_matches[0] - teu_matches[1]) / teu_matches[1]) * Decimal("100")
    return None


def _bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y%W")
