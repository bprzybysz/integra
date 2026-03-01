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
    CONTROLLED_USE = "controlled-use"


class RewardCategory(StrEnum):
    """Reward task category for scoring and quota rules."""

    HEALTHY = "healthy"
    NEUTRAL = "neutral"
    QUOTA = "quota"
    ADDICTION_THERAPY = "addiction-therapy"
    CONTROLLED_USE = "controlled-use"


class AdvisorState(StrEnum):
    """Daily advisor state driving coaching tone."""

    STRUGGLING = "struggling"  # quota violation OR 3+ healthy misses
    HOLDING = "holding"  # no violations, 1-2 healthy misses
    THRIVING = "thriving"  # all healthy green + under-quota


class PenanceSeverity(StrEnum):
    """Graduated penance tiers for zero-quota relapse."""

    MINOR = "minor"  # 1 unit over → 20-min study
    STANDARD = "standard"  # 2-3 units → full gym/study session
    ESCALATED = "escalated"  # >3 units or 3rd relapse/week → gym + study + HIL


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
    week_number: int  # ISO week for quota window
    trigger_context: str  # JSON-serialized TriggerContext
    ruliade: str  # NL time rule for agent (e.g. "not during work hours, 2h cooldown")
    notes: str


class ControlledUseRecord(TypedDict):
    """Controlled-use substance tracking (stable ceiling + time rules)."""

    substance: str  # e.g. "BCD"
    amount: str
    unit: str
    timestamp: str  # ISO 8601
    daily_ceiling: str  # stable max per day (no decay)
    cooldown_hours: str  # min gap between uses
    work_hours_blocked: bool  # True = blocked 09-17 CET
    ruliade: str  # NL time rule for agent (e.g. "not during work hours, 2h cooldown")
    notes: str


class TriggerContext(TypedDict):
    """HALT trigger context for addiction-therapy intake events."""

    halt_hungry: bool
    halt_angry: bool
    halt_lonely: bool
    halt_tired: bool
    craving_intensity: int  # 1-10
    situation_notes: str


class PenanceRecord(TypedDict):
    """Penance task assigned on zero-quota relapse."""

    substance: str
    relapse_timestamp: str  # ISO 8601
    relapse_amount: str
    penance_severity: str  # PenanceSeverity value
    penance_description: str  # e.g. "30-min gym session"
    penance_gh_issue_id: str  # empty string until created
    penance_completed: bool
    penance_completed_at: str  # empty string until completed


class CravingDelayInterval(StrEnum):
    """Escalating postpone intervals for craving delay technique."""

    FIFTEEN_MIN = "15min"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    TWENTY_FOUR_HOURS = "24h"


class DiaryType(StrEnum):
    """Diary entry trigger type."""

    VIOLATION = "violation"  # triggered by quota violation
    ON_DEMAND = "on_demand"  # user-initiated via HIL


class CravingDelayRecord(TypedDict):
    """A craving delay event — user postpones use by escalating intervals."""

    substance: str
    interval: str  # CravingDelayInterval value
    started_at: str  # ISO 8601
    completed: bool  # True = waited full interval without using
    gave_in: bool  # True = used before interval expired
    gave_in_at: str  # ISO 8601, empty if completed
    notes: str


class ScheduledRewardRecord(TypedDict):
    """A recurring reward task with time-window rules."""

    name: str  # e.g. "sauna"
    days_of_week: list[int]  # ISO weekday (1=Mon, 7=Sun) e.g. [3, 5, 7]
    time_window_start: str  # HH:MM earliest allowed (e.g. "17:00")
    time_window_end: str  # HH:MM latest start (e.g. "19:35")
    leave_by: str  # HH:MM leave house deadline (e.g. "19:50")
    ruliade: str  # NL description for complex time rules agent interprets
    completed_at: str  # ISO 8601, empty if pending


class DiaryRecord(TypedDict):
    """A diary entry — violation-triggered or on-demand via HIL."""

    diary_type: str  # DiaryType value
    severity: str  # PenanceSeverity value (for violation) or "none" (on-demand)
    substance: str  # relevant substance, empty for on-demand
    questions_asked: int
    answers: str  # JSON-serialized list of Q&A pairs
    penance_credit: float  # 0.0 for on-demand, 0.3-0.5 for violation
    timestamp: str  # ISO 8601


class DailyLogSummary(TypedDict):
    """Advisor's daily assessment output."""

    date: str  # ISO date
    advisor_state: str  # AdvisorState value
    healthy_completed: int
    healthy_total: int
    streaks_at_risk: list[str]  # habit names with streak >= 7 not yet done
    quota_violations: list[str]  # substance names over quota
    zero_quota_relapses: int
    penance_tasks_pending: int
    coaching_message: str


def make_controlled_use_record(
    substance: str,
    amount: str,
    unit: str,
    daily_ceiling: str = "",
    cooldown_hours: str = "2",
    work_hours_blocked: bool = True,
    ruliade: str = "",
    notes: str = "",
    timestamp: str | None = None,
) -> ControlledUseRecord:
    """Create a controlled-use intake record."""
    return ControlledUseRecord(
        substance=substance,
        amount=amount,
        unit=unit,
        timestamp=timestamp or datetime.now().astimezone().isoformat(),
        daily_ceiling=daily_ceiling,
        cooldown_hours=cooldown_hours,
        work_hours_blocked=work_hours_blocked,
        ruliade=ruliade,
        notes=notes,
    )


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
    week_number: int = 0,
    trigger_context: str = "{}",
    ruliade: str = "",
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
        week_number=week_number,
        trigger_context=trigger_context,
        ruliade=ruliade,
        notes=notes,
    )


def make_trigger_context(
    halt_hungry: bool = False,
    halt_angry: bool = False,
    halt_lonely: bool = False,
    halt_tired: bool = False,
    craving_intensity: int = 0,
    situation_notes: str = "",
) -> TriggerContext:
    """Create a HALT trigger context for substance intake."""
    return TriggerContext(
        halt_hungry=halt_hungry,
        halt_angry=halt_angry,
        halt_lonely=halt_lonely,
        halt_tired=halt_tired,
        craving_intensity=craving_intensity,
        situation_notes=situation_notes,
    )


def make_craving_delay_record(
    substance: str,
    interval: str = CravingDelayInterval.FIFTEEN_MIN,
    notes: str = "",
    started_at: str | None = None,
) -> CravingDelayRecord:
    """Create a craving delay record."""
    return CravingDelayRecord(
        substance=substance,
        interval=interval,
        started_at=started_at or datetime.now().astimezone().isoformat(),
        completed=False,
        gave_in=False,
        gave_in_at="",
        notes=notes,
    )


def make_scheduled_reward_record(
    name: str,
    days_of_week: list[int],
    time_window_start: str = "17:00",
    time_window_end: str = "19:35",
    leave_by: str = "19:50",
    ruliade: str = "",
) -> ScheduledRewardRecord:
    """Create a scheduled reward record."""
    return ScheduledRewardRecord(
        name=name,
        days_of_week=days_of_week,
        time_window_start=time_window_start,
        time_window_end=time_window_end,
        leave_by=leave_by,
        ruliade=ruliade,
        completed_at="",
    )


def make_diary_record(
    diary_type: str = DiaryType.ON_DEMAND,
    severity: str = "none",
    substance: str = "",
    questions_asked: int = 0,
    answers: str = "[]",
    penance_credit: float = 0.0,
    timestamp: str | None = None,
) -> DiaryRecord:
    """Create a diary record (violation or on-demand)."""
    return DiaryRecord(
        diary_type=diary_type,
        severity=severity,
        substance=substance,
        questions_asked=questions_asked,
        answers=answers,
        penance_credit=penance_credit,
        timestamp=timestamp or datetime.now().astimezone().isoformat(),
    )


def make_penance_record(
    substance: str,
    relapse_amount: str,
    penance_severity: str = PenanceSeverity.MINOR,
    penance_description: str = "",
    relapse_timestamp: str | None = None,
) -> PenanceRecord:
    """Create a penance record for zero-quota relapse."""
    return PenanceRecord(
        substance=substance,
        relapse_timestamp=relapse_timestamp or datetime.now().astimezone().isoformat(),
        relapse_amount=relapse_amount,
        penance_severity=penance_severity,
        penance_description=penance_description,
        penance_gh_issue_id="",
        penance_completed=False,
        penance_completed_at="",
    )
