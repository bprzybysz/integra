"""Tests for integra/data/streaks.py — streak tracking derived from lake records."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from integra.data.streaks import (
    STREAK_HABITS,
    check_milestone,
    compute_multiplier,
    get_streak_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_records(dates: list[date]) -> str:
    """Serialize a list of dates as query_data JSON output."""
    import json

    return json.dumps([{"habit": "exercise", "timestamp": d.isoformat()} for d in dates])


TODAY = date(2026, 3, 1)


def _dates_back(n: int, start: date = TODAY) -> list[date]:
    """Return n consecutive dates ending at start (inclusive)."""
    return [start - timedelta(days=i) for i in range(n)]


# ---------------------------------------------------------------------------
# compute_multiplier unit tests
# ---------------------------------------------------------------------------


def test_compute_multiplier_day_1() -> None:
    assert compute_multiplier(1) == pytest.approx(1.01)


def test_compute_multiplier_day_50_capped() -> None:
    assert compute_multiplier(50) == pytest.approx(1.5)


def test_compute_multiplier_day_100_capped() -> None:
    assert compute_multiplier(100) == pytest.approx(1.5)


def test_compute_multiplier_day_0() -> None:
    assert compute_multiplier(0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# check_milestone unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("days,expected", [(7, 7), (30, 30), (50, 50), (100, 100)])
def test_check_milestone_hits(days: int, expected: int) -> None:
    assert check_milestone(days) == expected


@pytest.mark.parametrize("days", [0, 1, 6, 8, 29, 31, 49, 51, 99, 101])
def test_check_milestone_miss(days: int) -> None:
    assert check_milestone(days) is None


# ---------------------------------------------------------------------------
# STREAK_HABITS constant
# ---------------------------------------------------------------------------


def test_streak_habits_content() -> None:
    assert set(STREAK_HABITS) == {"exercise", "supplements", "sleep_target", "coding_drill"}


# ---------------------------------------------------------------------------
# get_streak_state — integration-style (query_data mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streak_zero_no_records() -> None:
    """Streak of 0 when no lake records exist."""
    import json

    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value=json.dumps([])),
    ):
        state = await get_streak_state("exercise", today=TODAY)

    assert state["streak_days"] == 0
    assert state["multiplier"] == pytest.approx(1.0)
    assert state["grace_total_earned"] == 0
    assert state["grace_consumed"] == 0
    assert state["grace_available"] == 0
    assert state["at_risk"] is False
    assert state["milestone_hit"] is None


@pytest.mark.asyncio
async def test_streak_seven_days() -> None:
    """Streak of 7 → multiplier=1.07, grace_earned=1, milestone_hit=7."""
    records = _make_records(_dates_back(7))

    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value=records),
    ):
        state = await get_streak_state("exercise", today=TODAY)

    assert state["streak_days"] == 7
    assert state["multiplier"] == pytest.approx(1.07)
    assert state["grace_total_earned"] == 1
    assert state["milestone_hit"] == 7
    assert state["at_risk"] is False  # completed today


@pytest.mark.asyncio
async def test_streak_fifty_capped() -> None:
    """Streak of 50 → multiplier capped at 1.50, milestone_hit=50."""
    records = _make_records(_dates_back(50))

    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value=records),
    ):
        state = await get_streak_state("exercise", today=TODAY)

    assert state["streak_days"] == 50
    assert state["multiplier"] == pytest.approx(1.5)
    assert state["milestone_hit"] == 50
    assert state["at_risk"] is False


@pytest.mark.asyncio
async def test_at_risk_streak_ge_7_not_done_today() -> None:
    """at_risk=True when streak >= 7 and today has no record."""
    # 7-day streak ending yesterday (not today)
    yesterday = TODAY - timedelta(days=1)
    records = _make_records(_dates_back(7, start=yesterday))

    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value=records),
    ):
        state = await get_streak_state("exercise", today=TODAY)

    assert state["at_risk"] is True
    assert state["streak_days"] >= 7


@pytest.mark.asyncio
async def test_at_risk_false_below_7() -> None:
    """at_risk=False when streak < 7, even if not done today."""
    yesterday = TODAY - timedelta(days=1)
    records = _make_records(_dates_back(5, start=yesterday))

    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value=records),
    ):
        state = await get_streak_state("exercise", today=TODAY)

    assert state["at_risk"] is False


@pytest.mark.asyncio
async def test_grace_day_preserves_streak() -> None:
    """1-day gap consumed from grace; streak is preserved."""
    import json

    # 14-day streak: days 0..6 present, day 7 missing (gap), days 8..14 present
    # = total 14 records with a 1-day gap at day 7
    present_dates = [TODAY - timedelta(days=i) for i in range(7)]  # days 0-6
    present_dates += [TODAY - timedelta(days=i) for i in range(8, 15)]  # days 8-14

    records_json = json.dumps([{"habit": "exercise", "timestamp": d.isoformat()} for d in present_dates])

    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value=records_json),
    ):
        state = await get_streak_state("exercise", today=TODAY)

    # streak should bridge the 1-day gap via grace
    assert state["streak_days"] >= 14
    assert state["grace_consumed"] >= 1


@pytest.mark.asyncio
async def test_grace_not_available_breaks_streak() -> None:
    """A 1-day gap with no grace budget breaks the streak."""
    import json

    # Only 3 days present (not enough for grace), then gap
    present_dates = [TODAY - timedelta(days=i) for i in range(3)]
    # Days 4+ would extend but there is a gap at day 3 and zero grace earned

    records_json = json.dumps([{"habit": "exercise", "timestamp": d.isoformat()} for d in present_dates])

    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value=records_json),
    ):
        state = await get_streak_state("exercise", today=TODAY)

    assert state["streak_days"] == 3
    assert state["grace_consumed"] == 0


@pytest.mark.asyncio
async def test_invalid_json_returns_zero_streak() -> None:
    """Malformed JSON from query_data yields a zero streak, not an exception."""
    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value="not-json"),
    ):
        state = await get_streak_state("exercise", today=TODAY)

    assert state["streak_days"] == 0


@pytest.mark.asyncio
async def test_habit_field_forwarded_correctly() -> None:
    """get_streak_state forwards the habit name in the returned StreakState."""
    import json

    with patch(
        "integra.data.streaks.query_data",
        new=AsyncMock(return_value=json.dumps([])),
    ):
        state = await get_streak_state("supplements", today=TODAY)

    assert state["habit"] == "supplements"
