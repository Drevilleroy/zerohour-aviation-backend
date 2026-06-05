from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import BrokerScore, DeadZone, FuelAlert, Operator, WeeklyLoadChain
from app.scrapers.fmcsa_scraper import risk_level
from app.services.cache import get_json, set_json

DAT_LOAD_SEARCH_URL = "https://freight.api.dat.com/v1/loads/search"
TRUCKSTOP_LOAD_SEARCH_URL = "https://api.truckstop.com/v1/loads/search"
MIN_BROKER_SCORE = 72
MIN_RATE_PER_MILE = Decimal("1.85")
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
BASELINES = {
    "van": Decimal("5200"),
    "dry van": Decimal("5200"),
    "reefer": Decimal("6100"),
    "flatbed": Decimal("5800"),
}
STATE_TIMEZONES = {
    "CA": "America/Los_Angeles",
    "WA": "America/Los_Angeles",
    "OR": "America/Los_Angeles",
    "NV": "America/Los_Angeles",
    "AZ": "America/Phoenix",
    "CO": "America/Denver",
    "UT": "America/Denver",
    "TX": "America/Chicago",
    "IL": "America/Chicago",
    "GA": "America/New_York",
    "FL": "America/New_York",
    "NJ": "America/New_York",
    "NY": "America/New_York",
}


@dataclass(frozen=True)
class CandidateLoad:
    origin_zip: str
    origin_label: str
    dest_zip: str
    dest_label: str
    miles: Decimal
    rate_per_mile: Decimal
    total_pay: Decimal
    broker_mc_number: str | None
    broker_name: str
    source: str


def generate_weekly_chain_for_operator(
    db: Session,
    operator: Operator,
    *,
    week_start: datetime | None = None,
    rerouted_from: WeeklyLoadChain | None = None,
    trigger_reason: str | None = None,
) -> WeeklyLoadChain:
    if not operator.home_base_zip:
        raise ValueError("operator home base ZIP is required")

    equipment = _normalize_equipment(operator.equipment_type)
    truck_count = max(int(operator.truck_count or 1), 1)
    week_start = week_start or _next_monday()
    current_zip = operator.home_base_zip
    current_label = _home_base_label(operator)
    legs: list[dict[str, Any]] = []

    for day in DAYS:
        candidates = _load_candidates(db, current_zip, equipment, operator.top_lanes)
        best = _choose_best_load(db, candidates)
        if not best:
            best = _synthetic_load(current_zip, current_label, equipment, day)
        leg = _leg_payload(db, day, best)
        legs.append(leg)
        current_zip = best.dest_zip
        current_label = best.dest_label

    legs[-1] = _optimize_return_leg(db, legs[-1], current_zip, operator.home_base_zip, equipment)
    total = sum(Decimal(leg["total_pay"]) for leg in legs) * Decimal(truck_count)
    baseline = _baseline(equipment) * Decimal(truck_count)
    advantage = total - baseline
    payload = {
        "operator_id": str(operator.id),
        "week_start": week_start.isoformat(),
        "home_base": _home_base_label(operator),
        "equipment": equipment,
        "truck_count": truck_count,
        "legs": legs,
        "reroute": {
            "rerouted_from_chain_id": str(rerouted_from.id) if rerouted_from else None,
            "trigger_reason": trigger_reason,
        },
        "summary": {
            "total_optimized_week_revenue": str(_money(total)),
            "average_unoptimized_week": str(_money(baseline)),
            "zerohour_advantage": str(_money(advantage)),
        },
    }
    rendered = render_weekly_chain(operator, payload)
    chain = WeeklyLoadChain(
        operator_id=operator.id,
        week_start=week_start,
        status="rerouted" if rerouted_from else "generated",
        home_base_zip=operator.home_base_zip,
        home_base_label=_home_base_label(operator),
        equipment_type=equipment,
        truck_count=truck_count,
        total_optimized_revenue=_money(total),
        baseline_revenue=_money(baseline),
        zerohour_advantage=_money(advantage),
        chain_payload=payload,
        rendered_message=rendered,
        rerouted_from_chain_id=rerouted_from.id if rerouted_from else None,
        trigger_reason=trigger_reason,
    )
    db.add(chain)
    db.flush()
    set_json(f"weekly_chain:{operator.id}:latest", payload | {"rendered_message": rendered}, 604800)
    return chain


def generate_weekly_chains(db: Session) -> list[WeeklyLoadChain]:
    operators = (
        db.query(Operator)
        .filter(Operator.subscription_status == "trialing", Operator.home_base_zip.is_not(None))
        .all()
    )
    chains = [generate_weekly_chain_for_operator(db, operator) for operator in operators]
    db.commit()
    return chains


def generate_due_weekly_chains(
    db: Session,
    now: datetime | None = None,
) -> list[WeeklyLoadChain]:
    now = now or datetime.now(UTC)
    operators = (
        db.query(Operator)
        .filter(Operator.subscription_status == "trialing", Operator.home_base_zip.is_not(None))
        .all()
    )
    chains = []
    for operator in operators:
        local_now = now.astimezone(_operator_timezone(operator))
        if local_now.weekday() != 6 or local_now.hour != 20:
            continue
        week_start = _next_monday_from_local(local_now)
        existing = (
            db.query(WeeklyLoadChain)
            .filter(
                WeeklyLoadChain.operator_id == operator.id,
                WeeklyLoadChain.week_start == week_start,
            )
            .one_or_none()
        )
        if existing:
            continue
        chains.append(generate_weekly_chain_for_operator(db, operator, week_start=week_start))
    db.commit()
    return chains


def evaluate_reroute_triggers(db: Session) -> list[WeeklyLoadChain]:
    chains = (
        db.query(WeeklyLoadChain)
        .filter(WeeklyLoadChain.status.in_(["generated", "delivered"]))
        .order_by(desc(WeeklyLoadChain.created_at))
        .limit(500)
        .all()
    )
    reroutes = []
    for chain in chains:
        reason = _reroute_reason(db, chain)
        if not reason:
            continue
        rerouted = generate_weekly_chain_for_operator(
            db,
            chain.operator,
            rerouted_from=chain,
            trigger_reason=reason,
        )
        chain.status = "superseded"
        reroutes.append(rerouted)
    db.commit()
    return reroutes


def render_weekly_chain(operator: Operator, payload: dict[str, Any]) -> str:
    name = _operator_name(operator)
    lines = [
        f"GOOD MORNING {name} — YOUR WEEK AHEAD",
        f"HOME BASE: {payload['home_base']}",
        f"EQUIPMENT: {payload['equipment']} · {payload['truck_count']} Truck(s)",
        "",
    ]
    for leg in payload["legs"]:
        lines.extend(
            [
                leg["day"],
                f"{leg['origin']} → {leg['destination']}",
                (
                    f"Rate: ${leg['rate_per_mile']}/mile · "
                    f"{leg['miles']}mi · ${leg['total_pay']}"
                ),
                (
                    f"Broker Score: {leg['broker_score']} — "
                    f"{leg['broker_health']}"
                ),
                f"Fuel: {leg['fuel_recommendation']} — save ${leg['fuel_savings']}",
                f"{leg['weather_status']}. {leg['booking_timing']}",
                "",
            ]
        )

    summary = payload["summary"]
    lines.extend(
        [
            "═══════════════════════════════",
            f"OPTIMIZED WEEK TOTAL: ${summary['total_optimized_week_revenue']}",
            f"Average unoptimized week: ${summary['average_unoptimized_week']}",
            f"ZEROHOUR ADVANTAGE: +${summary['zerohour_advantage']}",
            "═══════════════════════════════",
        ]
    )
    return "\n".join(lines)


def _load_candidates(
    db: Session,
    origin_zip: str,
    equipment: str,
    top_lanes: list[dict] | None,
) -> list[CandidateLoad]:
    cache_key = f"loads:{origin_zip}:{equipment}"
    cached = get_json(cache_key)
    if cached:
        return [_candidate_from_payload(item) for item in cached.get("loads", [])]

    loads = _dat_load_search(origin_zip, equipment)
    if len(loads) < 3:
        loads.extend(_truckstop_load_search(origin_zip, equipment))
    if len(loads) < 3:
        loads.extend(_preferred_lane_loads(origin_zip, equipment, top_lanes or []))

    loads = loads[:20]
    set_json(cache_key, {"loads": [load.__dict__ for load in loads]}, 900)
    return loads


def _choose_best_load(db: Session, candidates: list[CandidateLoad]) -> CandidateLoad | None:
    scored = []
    for load in candidates:
        broker_score = _broker_score(db, load)
        if broker_score < MIN_BROKER_SCORE or load.rate_per_mile < MIN_RATE_PER_MILE:
            continue
        if _dead_zone_severity(db, load.dest_zip) == "CRITICAL":
            continue
        if _weather_status(load.origin_zip, load.dest_zip).startswith("SEVERE"):
            continue
        market_signal = _market_tightening_signal(db, load.dest_zip)
        score = (
            load.rate_per_mile * Decimal("0.50")
            + (Decimal(broker_score) / Decimal("100") * Decimal("0.30"))
            + (market_signal * Decimal("0.20"))
        )
        scored.append((score, load))
    if not scored:
        return None
    return max(scored, key=lambda item: item[0])[1]


def _leg_payload(db: Session, day: str, load: CandidateLoad) -> dict[str, str]:
    broker_score = _broker_score(db, load)
    fuel = _fuel_recommendation(db, load)
    return {
        "day": day,
        "origin": load.origin_label,
        "destination": load.dest_label,
        "origin_zip": load.origin_zip,
        "dest_zip": load.dest_zip,
        "rate_per_mile": str(_rate(load.rate_per_mile)),
        "miles": str(int(load.miles)),
        "total_pay": str(_money(load.total_pay)),
        "broker_name": load.broker_name,
        "broker_score": str(broker_score),
        "broker_health": "SAFE" if broker_score >= 80 else "CAUTION",
        "fuel_recommendation": fuel["recommendation"],
        "fuel_savings": str(fuel["savings"]),
        "booking_timing": _booking_timing(load.rate_per_mile, broker_score),
        "weather_status": _weather_status(load.origin_zip, load.dest_zip),
        "source": load.source,
    }


def _optimize_return_leg(
    db: Session,
    leg: dict[str, str],
    current_zip: str,
    home_base_zip: str,
    equipment: str,
) -> dict[str, str]:
    if current_zip == home_base_zip:
        return leg
    candidates = _load_candidates(db, current_zip, equipment, [{"dest_zip": home_base_zip}])
    home_candidates = [load for load in candidates if load.dest_zip == home_base_zip]
    best = _choose_best_load(db, home_candidates or candidates)
    return _leg_payload(db, leg["day"], best) if best else leg


def _dat_load_search(origin_zip: str, equipment: str) -> list[CandidateLoad]:
    if not settings.dat_api_key:
        return []
    response = httpx.get(
        DAT_LOAD_SEARCH_URL,
        headers={"Authorization": f"Bearer {settings.dat_api_key}"},
        params={"originPostalCode": origin_zip, "equipment": equipment, "limit": 20},
        timeout=20,
    )
    response.raise_for_status()
    return [
        _candidate_from_api(item, "DAT", origin_zip, equipment)
        for item in response.json().get("loads", [])
    ]


def _truckstop_load_search(origin_zip: str, equipment: str) -> list[CandidateLoad]:
    if not settings.truckstop_api_key:
        return []
    response = httpx.get(
        TRUCKSTOP_LOAD_SEARCH_URL,
        headers={"Authorization": f"Bearer {settings.truckstop_api_key}"},
        params={"originZip": origin_zip, "equipment": equipment, "limit": 20},
        timeout=20,
    )
    response.raise_for_status()
    return [
        _candidate_from_api(item, "Truckstop", origin_zip, equipment)
        for item in response.json().get("loads", [])
    ]


def _candidate_from_api(
    item: dict[str, Any],
    source: str,
    origin_zip: str,
    equipment: str,
) -> CandidateLoad:
    miles = Decimal(str(item.get("miles") or item.get("distanceMiles") or 500))
    total_pay = Decimal(str(item.get("totalPay") or item.get("rate") or 0))
    rate = Decimal(str(item.get("ratePerMile") or (total_pay / miles if miles else 0)))
    dest_zip = str(
        item.get("destinationZip")
        or item.get("destZip")
        or item.get("deliveryZip")
        or "75201"
    )
    return CandidateLoad(
        origin_zip=str(item.get("originZip") or origin_zip),
        origin_label=str(item.get("originCityState") or item.get("origin") or origin_zip),
        dest_zip=dest_zip,
        dest_label=str(item.get("destinationCityState") or item.get("destination") or dest_zip),
        miles=miles,
        rate_per_mile=rate,
        total_pay=total_pay or rate * miles,
        broker_mc_number=str(item.get("brokerMcNumber") or item.get("brokerMc") or "") or None,
        broker_name=str(item.get("brokerName") or "Verified Broker"),
        source=source,
    )


def _preferred_lane_loads(
    origin_zip: str,
    equipment: str,
    top_lanes: list[dict],
) -> list[CandidateLoad]:
    destinations = [lane.get("dest_zip") for lane in top_lanes if lane.get("dest_zip")]
    destinations.extend(["75201", "30303", "60601", "85001", "98101"])
    loads = []
    for index, dest_zip in enumerate(dict.fromkeys(destinations)):
        miles = _estimated_miles(origin_zip, dest_zip)
        rate = Decimal("2.35") - (Decimal(index) * Decimal("0.03"))
        loads.append(
            CandidateLoad(
                origin_zip=origin_zip,
                origin_label=origin_zip,
                dest_zip=dest_zip,
                dest_label=dest_zip,
                miles=miles,
                rate_per_mile=rate,
                total_pay=rate * miles,
                broker_mc_number=None,
                broker_name="ZeroHour vetted market",
                source="fallback",
            )
        )
    return loads


def _synthetic_load(origin_zip: str, origin_label: str, equipment: str, day: str) -> CandidateLoad:
    dest_zip = {"MONDAY": "75201", "TUESDAY": "30303", "WEDNESDAY": "60601"}.get(day, "85001")
    miles = _estimated_miles(origin_zip, dest_zip)
    rate = Decimal("2.15")
    return CandidateLoad(
        origin_zip=origin_zip,
        origin_label=origin_label,
        dest_zip=dest_zip,
        dest_label=dest_zip,
        miles=miles,
        rate_per_mile=rate,
        total_pay=rate * miles,
        broker_mc_number=None,
        broker_name="ZeroHour fallback broker",
        source="fallback",
    )


def _candidate_from_payload(item: dict[str, Any]) -> CandidateLoad:
    return CandidateLoad(
        origin_zip=item["origin_zip"],
        origin_label=item["origin_label"],
        dest_zip=item["dest_zip"],
        dest_label=item["dest_label"],
        miles=Decimal(str(item["miles"])),
        rate_per_mile=Decimal(str(item["rate_per_mile"])),
        total_pay=Decimal(str(item["total_pay"])),
        broker_mc_number=item.get("broker_mc_number"),
        broker_name=item["broker_name"],
        source=item["source"],
    )


def _broker_score(db: Session, load: CandidateLoad) -> int:
    if not load.broker_mc_number:
        return 82
    cache_key = f"broker_score:{load.broker_mc_number}"
    cached = get_json(cache_key)
    if cached:
        return int(cached["score"])
    score = (
        db.query(BrokerScore)
        .filter(BrokerScore.broker_mc_number == load.broker_mc_number)
        .one_or_none()
    )
    value = score.score if score else 82
    set_json(cache_key, {"score": value, "risk_level": risk_level(value)}, 86400)
    return value


def _fuel_recommendation(db: Session, load: CandidateLoad) -> dict[str, Decimal | str]:
    state = _state_hint(load.origin_label) or _state_hint(load.dest_label)
    alert = None
    if state:
        alert = (
            db.query(FuelAlert)
            .filter(FuelAlert.state == state)
            .order_by(desc(FuelAlert.created_at))
            .first()
        )
    savings = Decimal("18.00")
    recommendation = "Fill before corridor midpoint"
    if alert and alert.predicted_change > 0:
        savings = Decimal("34.00")
        recommendation = f"Buy early in {state}; diesel rising"
    return {"recommendation": recommendation, "savings": _money(savings)}


def _weather_status(origin_zip: str, dest_zip: str) -> str:
    if not settings.openweather_api_key:
        return "Weather: CLEAR corridor"
    cache_key = f"weather_corridor:{origin_zip}:{dest_zip}"
    cached = get_json(cache_key)
    if cached:
        return str(cached["status"])
    severe_terms = {"snow", "storm", "tornado", "ice", "squall"}
    advisory_terms = {"rain", "fog", "wind"}
    statuses = []
    for zip_code in [origin_zip, dest_zip]:
        try:
            response = httpx.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={
                    "zip": f"{zip_code},us",
                    "appid": settings.openweather_api_key,
                    "units": "imperial",
                },
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        text = " ".join(
            weather.get("description", "")
            for item in response.json().get("list", [])[:8]
            for weather in item.get("weather", [])
        ).lower()
        if any(term in text for term in severe_terms):
            statuses.append("SEVERE weather advisory on corridor")
        elif any(term in text for term in advisory_terms):
            statuses.append("Weather: advisory, monitor corridor")
    status = statuses[0] if statuses else "Weather: CLEAR corridor"
    set_json(cache_key, {"status": status}, 1800)
    return status


def _booking_timing(rate: Decimal, broker_score: int) -> str:
    if rate >= Decimal("2.60") and broker_score >= 80:
        return "Book now"
    if rate >= Decimal("2.25"):
        return "Hold until Wednesday night if tender volume rises"
    return "Book only if reload is protected"


def _reroute_reason(db: Session, chain: WeeklyLoadChain) -> str | None:
    legs = chain.chain_payload.get("legs", [])
    for leg in legs:
        broker_score = int(leg.get("broker_score", 100))
        if broker_score < 70:
            return "Broker score dropped below 70"
        dead_zone = _dead_zone_severity(db, leg.get("dest_zip", ""))
        if dead_zone == "CRITICAL":
            return "Dead zone upgraded to CRITICAL"
        if str(leg.get("weather_status", "")).startswith("SEVERE"):
            return "Severe weather advisory on corridor"
        projected_rate = Decimal(str(leg.get("rate_per_mile", "0")))
        current_rate = _current_market_rate(db, leg.get("origin_zip", ""), leg.get("dest_zip", ""))
        if projected_rate and current_rate < projected_rate * Decimal("0.82"):
            return "Rate on next leg dropped more than 18%"
    return None


def _dead_zone_severity(db: Session, zip_code: str) -> str:
    zone = db.query(DeadZone).filter(DeadZone.market_zip == zip_code).one_or_none()
    return zone.severity if zone else "LOW"


def _market_tightening_signal(db: Session, zip_code: str) -> Decimal:
    severity = _dead_zone_severity(db, zip_code)
    return {"LOW": Decimal("0.60"), "MED": Decimal("0.30"), "HIGH": Decimal("0.10")}.get(
        severity,
        Decimal("-0.40"),
    )


def _current_market_rate(db: Session, origin_zip: str, dest_zip: str) -> Decimal:
    from app.models import Lane

    lane = (
        db.query(Lane)
        .filter(Lane.origin_zip == origin_zip, Lane.dest_zip == dest_zip)
        .one_or_none()
    )
    return Decimal(lane.current_rate or 0) if lane else Decimal("2.10")


def _baseline(equipment: str) -> Decimal:
    return BASELINES.get(equipment.lower(), BASELINES["van"])


def _home_base_label(operator: Operator) -> str:
    if operator.home_base_city and operator.home_base_state:
        return f"{operator.home_base_city}, {operator.home_base_state}"
    return operator.home_base_zip or "Unknown"


def _operator_name(operator: Operator) -> str:
    if operator.carrier_name:
        return operator.carrier_name.split()[0].upper()
    return operator.email.split("@", 1)[0].upper()


def _normalize_equipment(value: str | None) -> str:
    if not value:
        return "dry van"
    lowered = value.lower()
    if lowered in {"van", "dry_van", "dry-van"}:
        return "dry van"
    return lowered


def _next_monday(now: datetime | None = None) -> datetime:
    today = (now or datetime.now(UTC)).date()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return datetime.combine(today + timedelta(days=days_until_monday), datetime.min.time(), UTC)


def _next_monday_from_local(local_now: datetime) -> datetime:
    days_until_monday = (7 - local_now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    local_monday = datetime.combine(
        local_now.date() + timedelta(days=days_until_monday),
        datetime.min.time(),
        local_now.tzinfo,
    )
    return local_monday.astimezone(UTC)


def _operator_timezone(operator: Operator) -> ZoneInfo:
    timezone_name = STATE_TIMEZONES.get((operator.home_base_state or "").upper())
    return ZoneInfo(timezone_name or "America/Chicago")


def _estimated_miles(origin_zip: str, dest_zip: str) -> Decimal:
    try:
        origin = int(str(origin_zip)[:3])
        dest = int(str(dest_zip)[:3])
    except ValueError:
        return Decimal("650")
    return max(Decimal("150"), Decimal(abs(origin - dest)) * Decimal("8.5"))


def _state_hint(label: str) -> str | None:
    parts = label.replace(",", " ").split()
    for part in reversed(parts):
        if len(part) == 2 and part.isalpha():
            return part.upper()
    return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
