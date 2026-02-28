"""Health data schemas for supplements, drug intake, and dietary logs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TypedDict


class SubstanceCategory(StrEnum):
    """Classification for substances."""

    SUPPLEMENT = "supplement"
    MEDICATION = "medication"
    ADDICTION_THERAPY = "addiction-therapy"


class FrequencyUnit(StrEnum):
    """Dosing frequency options."""

    DAILY = "daily"
    TWICE_DAILY = "twice_daily"
    WEEKLY = "weekly"
    AS_NEEDED = "as_needed"


class SupplementRecord(TypedDict):
    """A supplement or medication in the user's stack."""

    name: str
    dose: str
    unit: str
    frequency: str  # FrequencyUnit value
    time_of_day: str  # e.g. "morning", "evening", "08:00"
    category: str  # SubstanceCategory value
    notes: str


class IntakeRecord(TypedDict):
    """A single drug/substance intake event."""

    substance: str
    amount: str
    unit: str
    timestamp: str  # ISO 8601
    category: str  # SubstanceCategory value
    notes: str


class DietaryRecord(TypedDict):
    """A dietary intake log entry."""

    meal_type: str  # breakfast, lunch, dinner, snack
    items: str  # free-text description
    timestamp: str  # ISO 8601
    notes: str


class AddictionTherapyRecord(TypedDict):
    """Addiction-therapy substance tracking with quota support."""

    substance: str  # e.g. "3-CMC", "K/tip-touch"
    amount: str
    unit: str
    timestamp: str  # ISO 8601
    daily_quota: str  # target max per day (decreasing over time)
    notes: str


def make_supplement_record(
    name: str,
    dose: str,
    unit: str,
    frequency: str = FrequencyUnit.DAILY,
    time_of_day: str = "morning",
    category: str = SubstanceCategory.SUPPLEMENT,
    notes: str = "",
) -> SupplementRecord:
    """Create a validated supplement record."""
    return SupplementRecord(
        name=name,
        dose=dose,
        unit=unit,
        frequency=frequency,
        time_of_day=time_of_day,
        category=category,
        notes=notes,
    )


def make_intake_record(
    substance: str,
    amount: str,
    unit: str,
    category: str = SubstanceCategory.SUPPLEMENT,
    notes: str = "",
    timestamp: str | None = None,
) -> IntakeRecord:
    """Create a validated intake record with auto-timestamp."""
    return IntakeRecord(
        substance=substance,
        amount=amount,
        unit=unit,
        timestamp=timestamp or datetime.now().astimezone().isoformat(),
        category=category,
        notes=notes,
    )


def make_dietary_record(
    meal_type: str,
    items: str,
    notes: str = "",
    timestamp: str | None = None,
) -> DietaryRecord:
    """Create a validated dietary record."""
    return DietaryRecord(
        meal_type=meal_type,
        items=items,
        timestamp=timestamp or datetime.now().astimezone().isoformat(),
        notes=notes,
    )


def make_addiction_therapy_record(
    substance: str,
    amount: str,
    unit: str,
    daily_quota: str = "",
    notes: str = "",
    timestamp: str | None = None,
) -> AddictionTherapyRecord:
    """Create an addiction-therapy intake record."""
    return AddictionTherapyRecord(
        substance=substance,
        amount=amount,
        unit=unit,
        timestamp=timestamp or datetime.now().astimezone().isoformat(),
        daily_quota=daily_quota,
        notes=notes,
    )
