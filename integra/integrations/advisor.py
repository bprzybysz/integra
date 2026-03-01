"""Daily log advisor — computes AdvisorState and dispatches coaching."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from integra.core.config import Settings
from integra.data.quota import get_quota_state
from integra.data.schemas import AdvisorState
from integra.data.streaks import check_milestone, get_streak_state

if TYPE_CHECKING:
    from integra.integrations.channels.router import ChannelRouter

logger = logging.getLogger(__name__)

_SUBSTANCES = ["3-cmc", "k", "x", "thc"]
_HABITS = ["exercise", "supplements", "sleep_target", "coding_drill"]

_ADDICTION_MILESTONES = (7, 14, 30, 60, 90)

_STATE_EMOJI: dict[str, str] = {
    AdvisorState.THRIVING: "✅",
    AdvisorState.HOLDING: "⚠️",
    AdvisorState.STRUGGLING: "🔴",
}


async def compute_advisor_state(config: Settings) -> AdvisorState:
    """Read quota + streak state from lake, compute AdvisorState."""
    # Check quota violations
    for substance in _SUBSTANCES:
        qs = await get_quota_state(substance, config)
        if qs is not None and qs["coaching_flag"]:
            return AdvisorState.STRUGGLING

    # Count at-risk habits
    at_risk_count = 0
    for habit in _HABITS:
        ss = await get_streak_state(habit, config)
        if ss["at_risk"]:
            at_risk_count += 1

    if at_risk_count >= 3:
        return AdvisorState.STRUGGLING
    if at_risk_count >= 1:
        return AdvisorState.HOLDING
    return AdvisorState.THRIVING


def apply_coaching_rules(answers: dict[str, str], state: AdvisorState) -> list[str]:
    """Apply 10 ADHD-aware coaching rules. Returns list of coaching message lines."""
    messages: list[str] = []
    notes = answers.get("notes", "").lower()

    # Rule 1: Sleep <6h or broken 2+ days
    sleep_raw = answers.get("sleep_hours", "")
    sleep_broken = answers.get("sleep_broken_days", "")
    try:
        sleep_hours = float(sleep_raw)
    except (ValueError, TypeError):
        sleep_hours = 8.0
    try:
        broken_days = int(sleep_broken)
    except (ValueError, TypeError):
        broken_days = 0

    if sleep_hours < 6 or broken_days >= 2:
        messages.append("Cut pomodoros 50% today, prioritize a nap first.")

    # Rule 2: Mood low or rough
    mood = answers.get("mood", "").lower()
    if mood in ("low", "rough"):
        messages.append("No study pressure today. Gym if energy allows.")

    # Rule 3: 3+ days no exercise
    no_exercise_days_raw = answers.get("days_no_exercise", "")
    try:
        no_exercise_days = int(no_exercise_days_raw)
    except (ValueError, TypeError):
        no_exercise_days = 0
    if no_exercise_days >= 3:
        messages.append("Push some movement today — even a walk counts.")

    # Rule 4: IBS flare
    if "ibs" in notes:
        messages.append("Bland diet, shorter pomodoros, skip coffee.")

    # Rule 5: Pomodoros >6 on low sleep
    pomo_raw = answers.get("pomodoros", "")
    try:
        pomodoros = int(pomo_raw)
    except (ValueError, TypeError):
        pomodoros = 0
    if pomodoros > 6 and sleep_hours < 6:
        messages.append("You're overdriving on low sleep — ease off.")

    # Rule 6: freeze or pivot in notes
    if "freeze" in notes or "pivot" in notes:
        messages.append("Switch to an easier task, warm-up first.")

    # Rule 7: adhd or scatter in notes
    if "adhd" in notes or "scatter" in notes:
        messages.append("Check Medikinet timing, single-task mode.")

    # Rule 8: Mood low in afternoon + energy low
    time_of_day = answers.get("time_of_day", "").lower()
    energy = answers.get("energy", "").lower()
    if mood == "low" and time_of_day == "afternoon" and energy == "low":
        messages.append("Shift hard work to morning tomorrow.")

    # Rule 9: All habits streak >= 3 (use state as proxy — THRIVING)
    all_streak_raw = answers.get("min_streak_days", "")
    try:
        min_streak = int(all_streak_raw)
    except (ValueError, TypeError):
        min_streak = 0
    if min_streak >= 3 or state == AdvisorState.THRIVING:
        messages.append("3+ good days — safe to increase intensity.")

    # Rule 10: deadline in notes
    if "deadline" in notes:
        messages.append("Shift priorities to deadline-critical work.")

    return messages


async def check_milestones(config: Settings) -> list[str]:
    """Return celebration messages for any milestone hit today."""
    celebrations: list[str] = []

    for habit in _HABITS:
        ss = await get_streak_state(habit, config)
        hit = check_milestone(ss["streak_days"])
        if hit is not None:
            celebrations.append(f"🎯 Milestone: {hit}-day {habit} streak!")

    # Addiction-therapy clean milestones: check consecutive weeks with units_used == 0
    for substance in _SUBSTANCES:
        qs = await get_quota_state(substance, config)
        if qs is None:
            continue
        # Use week_n as a proxy for consecutive clean weeks when units_used == 0
        if qs["units_used"] == 0 and qs["week_n"] > 0:
            clean_days = qs["week_n"] * 7
            for milestone in _ADDICTION_MILESTONES:
                if clean_days == milestone:
                    celebrations.append(f"🏆 {milestone}d clean — {substance} addiction therapy milestone!")

    return celebrations


async def run_advisor(
    answers: dict[str, str],
    router: ChannelRouter,
    config: Settings,
) -> None:
    """Full advisor cycle: compute state, apply rules, check milestones, notify."""
    state = await compute_advisor_state(config)
    coaching_lines = apply_coaching_rules(answers, state)
    milestone_msgs = await check_milestones(config)

    emoji = _STATE_EMOJI.get(state, "")
    state_label = state.value.upper()
    parts: list[str] = [f"*Advisor: {state_label}* {emoji}"]

    if coaching_lines:
        parts.append("")
        for line in coaching_lines:
            parts.append(f"• {line}")

    if milestone_msgs:
        parts.append("")
        for msg in milestone_msgs:
            parts.append(msg)

    message = "\n".join(parts)
    await router.notify(message)
    logger.info("Advisor cycle complete: state=%s rules=%d", state, len(coaching_lines))
