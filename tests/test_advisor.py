"""Tests for integra/integrations/advisor.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integra.core.config import Settings
from integra.data.schemas import AdvisorState, QuotaState, StreakState
from integra.integrations.advisor import (
    apply_coaching_rules,
    check_milestones,
    compute_advisor_state,
    run_advisor,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_settings() -> Settings:
    return Settings(
        anthropic_api_key="test",
        telegram_bot_token="test",
        telegram_admin_chat_id=1,
        age_recipient="",
        age_identity="",
        chat_api_key="test",
    )


def _quota_ok(substance: str) -> QuotaState:
    return QuotaState(
        substance=substance,
        week_n=1,
        quota_week_0=10.0,
        decay_factor=0.85,
        current_quota=8.5,
        units_used=0.0,
        status="under",
        coaching_flag=False,
        penance_triggered=False,
    )


def _quota_violation(substance: str) -> QuotaState:
    return QuotaState(
        substance=substance,
        week_n=1,
        quota_week_0=10.0,
        decay_factor=0.85,
        current_quota=8.5,
        units_used=12.0,
        status="over",
        coaching_flag=True,
        penance_triggered=False,
    )


def _streak_ok(habit: str, streak_days: int = 10, at_risk: bool = False) -> StreakState:
    return StreakState(
        habit=habit,
        streak_days=streak_days,
        multiplier=min(1.0 + 0.01 * streak_days, 1.5),
        grace_total_earned=streak_days // 7,
        grace_consumed=0,
        grace_available=min(streak_days // 7, 3),
        at_risk=at_risk,
        milestone_hit=None,
    )


def _streak_at_risk(habit: str) -> StreakState:
    return _streak_ok(habit, streak_days=8, at_risk=True)


# ---------------------------------------------------------------------------
# compute_advisor_state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_advisor_state_struggling_quota_violation() -> None:
    config = _make_settings()

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        if substance == "3-cmc":
            return _quota_violation(substance)
        return _quota_ok(substance)

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        return _streak_ok(habit)

    with (
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
    ):
        state = await compute_advisor_state(config)

    assert state == AdvisorState.STRUGGLING


@pytest.mark.asyncio
async def test_compute_advisor_state_struggling_three_at_risk() -> None:
    config = _make_settings()

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        return _quota_ok(substance)

    habits_at_risk = ["exercise", "supplements", "sleep_target"]

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        if habit in habits_at_risk:
            return _streak_at_risk(habit)
        return _streak_ok(habit)

    with (
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
    ):
        state = await compute_advisor_state(config)

    assert state == AdvisorState.STRUGGLING


@pytest.mark.asyncio
async def test_compute_advisor_state_holding_one_at_risk() -> None:
    config = _make_settings()

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        return _quota_ok(substance)

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        if habit == "exercise":
            return _streak_at_risk(habit)
        return _streak_ok(habit)

    with (
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
    ):
        state = await compute_advisor_state(config)

    assert state == AdvisorState.HOLDING


@pytest.mark.asyncio
async def test_compute_advisor_state_thriving() -> None:
    config = _make_settings()

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        return _quota_ok(substance)

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        return _streak_ok(habit)

    with (
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
    ):
        state = await compute_advisor_state(config)

    assert state == AdvisorState.THRIVING


# ---------------------------------------------------------------------------
# apply_coaching_rules — each rule fires
# ---------------------------------------------------------------------------


def test_rule1_low_sleep_hours() -> None:
    answers = {"sleep_hours": "5"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("pomodoros" in m or "nap" in m for m in msgs)


def test_rule1_broken_sleep() -> None:
    answers = {"sleep_broken_days": "3"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("nap" in m for m in msgs)


def test_rule2_mood_low() -> None:
    answers = {"mood": "low"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("study pressure" in m for m in msgs)


def test_rule2_mood_rough() -> None:
    answers = {"mood": "rough"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("study pressure" in m for m in msgs)


def test_rule3_no_exercise() -> None:
    answers = {"days_no_exercise": "4"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("movement" in m for m in msgs)


def test_rule4_ibs_flare() -> None:
    answers = {"notes": "had an ibs flare today"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("Bland diet" in m for m in msgs)


def test_rule5_pomodoros_on_low_sleep() -> None:
    answers = {"sleep_hours": "5", "pomodoros": "7"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("overdriving" in m for m in msgs)


def test_rule6_freeze_in_notes() -> None:
    answers = {"notes": "I hit a freeze and could not continue"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("easier task" in m for m in msgs)


def test_rule6_pivot_in_notes() -> None:
    answers = {"notes": "had to pivot the plan"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("easier task" in m for m in msgs)


def test_rule7_adhd_in_notes() -> None:
    answers = {"notes": "adhd is acting up"}
    msgs = apply_coaching_rules(answers, AdvisorState.STRUGGLING)
    assert any("Medikinet" in m for m in msgs)


def test_rule7_scatter_in_notes() -> None:
    answers = {"notes": "feeling scatter brained"}
    msgs = apply_coaching_rules(answers, AdvisorState.STRUGGLING)
    assert any("single-task" in m for m in msgs)


def test_rule8_low_afternoon_low_energy() -> None:
    answers = {"mood": "low", "time_of_day": "afternoon", "energy": "low"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("morning tomorrow" in m for m in msgs)


def test_rule9_thriving_state() -> None:
    answers: dict[str, str] = {}
    msgs = apply_coaching_rules(answers, AdvisorState.THRIVING)
    assert any("intensity" in m for m in msgs)


def test_rule9_min_streak_days() -> None:
    answers = {"min_streak_days": "5"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("intensity" in m for m in msgs)


def test_rule10_deadline_in_notes() -> None:
    answers = {"notes": "have a deadline tomorrow"}
    msgs = apply_coaching_rules(answers, AdvisorState.HOLDING)
    assert any("deadline-critical" in m for m in msgs)


def test_no_rules_fire_on_empty_answers() -> None:
    # Only rule 9 fires (THRIVING state)
    msgs = apply_coaching_rules({}, AdvisorState.HOLDING)
    # No THRIVING → rule 9 via state doesn't fire, check rule 9 via min_streak_days=0 also no
    # Nothing should fire except none for HOLDING with empty answers
    assert not any("Medikinet" in m for m in msgs)
    assert not any("nap" in m for m in msgs)


# ---------------------------------------------------------------------------
# check_milestones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_milestones_habit_milestone() -> None:
    config = _make_settings()

    def make_milestone_streak(habit: str) -> StreakState:
        return StreakState(
            habit=habit,
            streak_days=30,
            multiplier=1.3,
            grace_total_earned=4,
            grace_consumed=0,
            grace_available=3,
            at_risk=False,
            milestone_hit=30,
        )

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        return make_milestone_streak(habit)

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        return _quota_ok(substance)

    with (
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
    ):
        msgs = await check_milestones(config)

    assert any("30-day" in m for m in msgs)
    assert any("exercise" in m for m in msgs)


@pytest.mark.asyncio
async def test_check_milestones_none_when_no_milestones() -> None:
    config = _make_settings()

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        return _streak_ok(habit, streak_days=5)

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        # week_n=0 means no weeks tracked yet → no clean-day milestone possible
        return QuotaState(
            substance=substance,
            week_n=0,
            quota_week_0=10.0,
            decay_factor=0.85,
            current_quota=10.0,
            units_used=3.0,
            status="under",
            coaching_flag=False,
            penance_triggered=False,
        )

    with (
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
    ):
        msgs = await check_milestones(config)

    assert msgs == []


@pytest.mark.asyncio
async def test_check_milestones_addiction_clean() -> None:
    config = _make_settings()

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        return _streak_ok(habit, streak_days=5)

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        # 3-cmc: week_n=1 (7 clean days) with units_used=0
        if substance == "3-cmc":
            return QuotaState(
                substance=substance,
                week_n=1,
                quota_week_0=10.0,
                decay_factor=0.85,
                current_quota=8.5,
                units_used=0.0,
                status="under",
                coaching_flag=False,
                penance_triggered=False,
            )
        return _quota_ok(substance)

    with (
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
    ):
        msgs = await check_milestones(config)

    assert any("7d clean" in m and "3-cmc" in m for m in msgs)


# ---------------------------------------------------------------------------
# run_advisor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_advisor_sends_message() -> None:
    config = _make_settings()
    router = MagicMock()
    router.notify = AsyncMock(return_value="ok")

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        return _quota_ok(substance)

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        return _streak_ok(habit)

    with (
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
    ):
        await run_advisor({"mood": "low"}, router, config)

    router.notify.assert_called_once()
    call_args = router.notify.call_args[0][0]
    assert "THRIVING" in call_args or "HOLDING" in call_args or "STRUGGLING" in call_args


@pytest.mark.asyncio
async def test_run_advisor_struggling_message_contains_emoji() -> None:
    config = _make_settings()
    router = MagicMock()
    router.notify = AsyncMock(return_value="ok")

    async def fake_quota(substance: str, config: Settings, reference_date: object = None) -> QuotaState:
        if substance == "3-cmc":
            return _quota_violation(substance)
        return _quota_ok(substance)

    async def fake_streak(habit: str, config: Settings | None = None, today: object = None) -> StreakState:
        return _streak_ok(habit)

    with (
        patch("integra.integrations.advisor.get_quota_state", side_effect=fake_quota),
        patch("integra.integrations.advisor.get_streak_state", side_effect=fake_streak),
    ):
        await run_advisor({}, router, config)

    call_args = router.notify.call_args[0][0]
    assert "🔴" in call_args
    assert "STRUGGLING" in call_args
