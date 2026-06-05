from __future__ import annotations

from app.db.session import SessionLocal
from app.models import FeatureFlag, KillSwitch

FEATURE_FLAGS = {
    "direct_mail": False,
    "signal_claiming": True,
    "elite_tier_features": False,
    "creator_attribution": True,
    "collaboration_layer": False,
    "mortgage_team_layer": False,
    "investor_layer": False,
}

KILL_SWITCHES = {
    "pause_ingestion": False,
    "pause_notifications": False,
    "pause_direct_mail": False,
    "pause_creator_signups": False,
    "pause_provisioning_queue": False,
    "force_cached_mode": False,
    "disable_expensive_providers": False,
}


def main() -> None:
    db = SessionLocal()
    try:
        for key, enabled in FEATURE_FLAGS.items():
            db.merge(
                FeatureFlag(
                    key=key,
                    enabled=enabled,
                    description=f"Operational rollout flag for {key}.",
                    rules={},
                )
            )
        for key, enabled in KILL_SWITCHES.items():
            db.merge(KillSwitch(key=key, enabled=enabled, reason="seed default"))
        db.commit()
        print("Seeded feature flags and kill switches.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

