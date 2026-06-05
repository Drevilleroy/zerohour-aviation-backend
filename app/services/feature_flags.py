from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import FeatureFlag, KillSwitch


def is_feature_enabled(db: Session, key: str, default: bool = False) -> bool:
    flag = db.get(FeatureFlag, key)
    return flag.enabled if flag else default


def is_kill_switch_enabled(db: Session, key: str, default: bool = False) -> bool:
    switch = db.get(KillSwitch, key)
    return switch.enabled if switch else default

