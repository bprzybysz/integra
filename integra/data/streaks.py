"""Streak tracking derived from lake records for healthy habits."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from integra.core.config import Settings
from integra.core.config import settings as default_settings
from integra.data.mcp_server import query_data
from integra.data.schemas import StreakState

logger = logging.getLogger(__name__)

STREAK_HABITS = ["exercise", "supplements", "sleep_target", "coding_drill"]

_MILESTONES = (7, 30, 50, 100)
_MAX_GRACE = 3
_MAX_MULTIPLIER = 1.5


def compute_multiplier(streak_days: int) -> float:
    """Return min(1.0 + 0.01 * streak_days, 1.50)."""
    return min(1.0 + 0.01 * streak_days, _MAX_MULTIPLIER)


def check_milestone(streak_days: int) -> int | None:
    """Return milestone value if streak_days is exactly a milestone, else None."""
    if streak_days in _MILESTONES:
        return streak_days
    return None


def _extract_dates(records: list[dict[str, object]]) -> list[date]:
    """Extract unique completion dates from lake records, sorted descending."""
    dates: set[date] = set()
    for rec in records:
        ts = rec.get("timestamp", "")
        if not isinstance(ts, str) or not ts:
            continue
        try:
            parsed = date.fromisoformat(ts[:10])
            dates.add(parsed)
        except ValueError:
            logger.debug("Unparseable timestamp: %s", ts)
    return sorted(dates, reverse=True)


def _count_bare_streak(date_set: set[date], start: date) -> int:
    """Count consecutive days backwards from start (no grace). Returns count."""
    streak = 0
    cursor = start
    while cursor in date_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _compute_streak_with_grace(
    date_set: set[date],
    start: date,
    grace_budget: int,
) -> tuple[int, int]:
    """Walk backwards from start, consuming grace for 1-day gaps.

    Returns (streak_days, grace_consumed).
    Grace is only used when a 1-day gap is detected and the next day has a record.
    A gap > 1 day always breaks the streak.
    """
    streak = 0
    grace_consumed = 0
    cursor = start

    while True:
        if cursor in date_set:
            streak += 1
            cursor -= timedelta(days=1)
        else:
            # cursor is absent — check for 1-day gap
            if grace_consumed < grace_budget and (cursor - timedelta(days=1)) in date_set:
                grace_consumed += 1
                cursor -= timedelta(days=1)
            else:
                break

    return streak, grace_consumed


async def get_streak_state(
    habit: str,
    config: Settings | None = None,
    today: date | None = None,
) -> StreakState:
    """Derive streak state from lake records for a healthy habit.

    Reads category='diary' records filtered by habit field, then computes
    consecutive-day streak backwards from today, consuming grace days as
    needed for single-day gaps.

    Grace budget is seeded from the bare (no-grace) streak of historical
    records ending at the most recent record date, so an absent today does
    not prevent grace from being applied to historical gaps.
    """
    cfg = config or default_settings
    reference_date = today or date.today()

    raw = await query_data(
        category="diary",
        filters={"habit": habit},
        config=cfg,
    )
    try:
        records: list[dict[str, object]] = json.loads(raw)
        if not isinstance(records, list):
            records = []
    except (json.JSONDecodeError, TypeError):
        records = []

    sorted_dates = _extract_dates(records)
    date_set = set(sorted_dates)

    completed_today = reference_date in date_set

    if not sorted_dates:
        return StreakState(
            habit=habit,
            streak_days=0,
            multiplier=compute_multiplier(0),
            grace_total_earned=0,
            grace_consumed=0,
            grace_available=0,
            at_risk=False,
            milestone_hit=None,
        )

    # Seed grace from the bare streak ending at the most recent record.
    # This allows grace to be available even when today has no record.
    latest_record = sorted_dates[0]
    bare_seed = _count_bare_streak(date_set, latest_record)
    grace_budget = min(bare_seed // 7, _MAX_GRACE)

    # Determine walk start: today if present, else today (gap will be handled).
    streak, grace_consumed = _compute_streak_with_grace(date_set, reference_date, grace_budget)

    grace_total_earned = streak // 7
    grace_available = min(max(grace_total_earned - grace_consumed, 0), _MAX_GRACE)
    at_risk = streak >= 7 and not completed_today

    return StreakState(
        habit=habit,
        streak_days=streak,
        multiplier=compute_multiplier(streak),
        grace_total_earned=grace_total_earned,
        grace_consumed=grace_consumed,
        grace_available=grace_available,
        at_risk=at_risk,
        milestone_hit=check_milestone(streak),
    )
