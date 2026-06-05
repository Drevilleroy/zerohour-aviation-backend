from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class NormalizedSignal:
    zip_code: str
    signal_type: str
    source: str
    subject_hash: str
    event_date: date | None
    confidence: Decimal
    payload: dict

    def as_upsert_kwargs(self) -> dict:
        return {
            "zip_code": self.zip_code,
            "signal_type": self.signal_type,
            "source": self.source,
            "subject_hash": self.subject_hash,
            "event_date": self.event_date,
            "confidence": self.confidence,
            "payload": self.payload,
            "address_hash": self.payload.get("address_hash"),
        }


class IngestionAdapter(ABC):
    source_name: str

    @abstractmethod
    async def fetch_zip(self, zip_code: str) -> list[NormalizedSignal]:
        """Fetch and normalize records for a ZIP code."""
