from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/creators", tags=["creators"])


@router.get("/{creator_code}/analytics")
def creator_analytics(creator_code: str) -> dict:
    return {
        "creator_code": creator_code,
        "quality_metrics": [
            "trial_completion_rate",
            "dre_completion_rate",
            "paid_conversion",
            "annual_plan_adoption",
            "churn",
            "letter_usage",
            "revenue",
        ],
    }

