"""Privacy-preserving plug-in contract for aggregated health outcomes."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class HealthObservation(BaseModel):
    """One aggregated ward-day count; individual records are deliberately unsupported."""

    ward_id: str = Field(min_length=1, max_length=160)
    observation_date: date
    outcome_type: Literal["all_cause_mortality", "heat_illness_admission"]
    count: int = Field(ge=0)
    source_name: str = Field(min_length=2, max_length=200)
    source_vintage: str = Field(min_length=2, max_length=100)
    aggregation_note: str = Field(min_length=2, max_length=300)

    @model_validator(mode="after")
    def require_aggregate_description(self) -> "HealthObservation":
        text = self.aggregation_note.lower()
        if not any(word in text for word in ("aggregate", "ward", "daily", "day")):
            raise ValueError("aggregation_note must explain the ward/day aggregation")
        return self


class HealthObservationBatch(BaseModel):
    """Bounded import batch for an approved municipal or hospital dataset."""

    licence_or_agreement: str = Field(min_length=2, max_length=300)
    observations: list[HealthObservation] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def reject_duplicate_keys(self) -> "HealthObservationBatch":
        keys = [(item.ward_id, item.observation_date, item.outcome_type) for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("batch contains duplicate ward/date/outcome rows")
        return self
