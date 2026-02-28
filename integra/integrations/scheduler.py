"""Async scheduler for periodic health data interrogation via Telegram."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, time

from integra.core.config import settings
from integra.data.collectors import collect_supplement_stack, log_drug_intake
from integra.integrations.questionnaire import (
    Question,
    Questionnaire,
    QuestionType,
    run_questionnaire,
)

logger = logging.getLogger(__name__)


@dataclass
class ScheduleEntry:
    """A scheduled questionnaire trigger."""

    name: str
    trigger_time: time  # HH:MM local time
    questionnaire: Questionnaire
    handler_name: str  # "supplement_check" or "intake_log"


# --- Pre-built questionnaires ---

MORNING_SUPPLEMENT_CHECK = Questionnaire(
    title="Morning Supplement Check",
    questions=[
        Question(
            text="Did you take your morning supplements?",
            field_name="taken",
            question_type=QuestionType.SELECTION,
            options=["Yes - all", "Partial", "No"],
        ),
        Question(
            text="Which supplements did you take? (comma-separated)",
            field_name="supplements",
            question_type=QuestionType.TEXT,
            default="all",
        ),
        Question(
            text="Any notes?",
            field_name="notes",
            question_type=QuestionType.TEXT,
            required=False,
            default="",
        ),
    ],
)

EVENING_INTAKE_LOG = Questionnaire(
    title="Evening Intake Log",
    questions=[
        Question(
            text="Any substance intake today? (name)",
            field_name="substance",
            question_type=QuestionType.TEXT,
        ),
        Question(
            text="Amount?",
            field_name="amount",
            question_type=QuestionType.TEXT,
        ),
        Question(
            text="Unit?",
            field_name="unit",
            question_type=QuestionType.SELECTION,
            options=["mg", "g", "ml", "units"],
        ),
        Question(
            text="Category?",
            field_name="category",
            question_type=QuestionType.SELECTION,
            options=["supplement", "medication", "addiction-therapy"],
        ),
    ],
)


def _default_schedules() -> list[ScheduleEntry]:
    """Return the default schedule entries."""
    morning_h, morning_m = _parse_time(settings.schedule_morning)
    evening_h, evening_m = _parse_time(settings.schedule_evening)
    return [
        ScheduleEntry(
            name="morning_supplement_check",
            trigger_time=time(morning_h, morning_m),
            questionnaire=MORNING_SUPPLEMENT_CHECK,
            handler_name="supplement_check",
        ),
        ScheduleEntry(
            name="evening_intake_log",
            trigger_time=time(evening_h, evening_m),
            questionnaire=EVENING_INTAKE_LOG,
            handler_name="intake_log",
        ),
    ]


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string to (hour, minute)."""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


async def _process_answers(handler_name: str, answers: dict[str, str]) -> None:
    """Process questionnaire answers through the appropriate handler."""
    if handler_name == "supplement_check":
        if answers.get("taken") == "No":
            logger.info("User skipped morning supplements.")
            return
        await collect_supplement_stack(
            name=answers.get("supplements", "morning stack"),
            dose="1",
            unit="serving",
            notes=f"Compliance: {answers.get('taken', '')}. {answers.get('notes', '')}",
        )
    elif handler_name == "intake_log":
        substance = answers.get("substance", "")
        if not substance or substance.lower() in ("none", "no", "n/a"):
            logger.info("No intake reported for evening log.")
            return
        await log_drug_intake(
            substance=substance,
            amount=answers.get("amount", "0"),
            unit=answers.get("unit", "mg"),
            category=answers.get("category", "supplement"),
        )


class Scheduler:
    """Async scheduler that runs questionnaires at configured times."""

    def __init__(self, schedules: list[ScheduleEntry] | None = None) -> None:
        self.schedules = schedules or _default_schedules()
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler started with %d entries", len(self.schedules))

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        """Main scheduler loop — checks every 30 seconds."""
        fired_today: set[str] = set()
        while self._running:
            now = datetime.now().astimezone()
            current_time = now.time()

            # Reset fired set at midnight
            if current_time.hour == 0 and current_time.minute == 0:
                fired_today.clear()

            for entry in self.schedules:
                if entry.name in fired_today:
                    continue
                if current_time.hour == entry.trigger_time.hour and current_time.minute == entry.trigger_time.minute:
                    fired_today.add(entry.name)
                    logger.info("Triggering scheduled questionnaire: %s", entry.name)
                    try:
                        answers = await run_questionnaire(entry.questionnaire)
                        await _process_answers(entry.handler_name, answers)
                    except Exception:
                        logger.exception("Error in scheduled questionnaire %s", entry.name)

            await asyncio.sleep(30)

    async def trigger_now(self, schedule_name: str) -> dict[str, str] | None:
        """Manually trigger a scheduled questionnaire (for testing/on-demand)."""
        for entry in self.schedules:
            if entry.name == schedule_name:
                answers = await run_questionnaire(entry.questionnaire)
                await _process_answers(entry.handler_name, answers)
                return answers
        logger.error("Unknown schedule: %s", schedule_name)
        return None
