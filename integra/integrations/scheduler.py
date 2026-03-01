"""Async scheduler for periodic health data interrogation via Telegram."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
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
from integra.integrations.questionnaire_ui import QuestionnaireUI

logger = logging.getLogger(__name__)

# Module-level UI instance — set from app.py after provider init
_questionnaire_ui: QuestionnaireUI | None = None

# Module-level router for advisor dispatch — set from app.py after provider init
_advisor_router: object | None = None  # ChannelRouter, typed as object to avoid circular import


def set_questionnaire_ui(ui: QuestionnaireUI) -> None:
    """Set the questionnaire UI instance (called from app lifespan)."""
    global _questionnaire_ui  # noqa: PLW0603
    _questionnaire_ui = ui


def set_advisor_router(router: object) -> None:
    """Set the ChannelRouter for advisor dispatch (called from app lifespan)."""
    global _advisor_router  # noqa: PLW0603
    _advisor_router = router


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

ON_DEMAND_DIARY = Questionnaire(
    title="Diary Entry",
    questions=[
        Question(
            text="What's on your mind? (free text)",
            field_name="content",
            question_type=QuestionType.TEXT,
        ),
        Question(
            text="Mood right now?",
            field_name="mood",
            question_type=QuestionType.SELECTION,
            options=["great", "good", "neutral", "low", "rough"],
        ),
        Question(
            text="Any substance today? (name or 'none')",
            field_name="substance",
            question_type=QuestionType.TEXT,
            required=False,
            default="none",
        ),
        Question(
            text="Anything you want to flag?",
            field_name="notes",
            question_type=QuestionType.TEXT,
            required=False,
            default="",
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


AnswerHandler = Callable[[dict[str, str]], Awaitable[None]]


async def _handle_supplement_check(answers: dict[str, str]) -> None:
    """Process supplement check questionnaire answers."""
    if answers.get("taken") == "No":
        logger.info("User skipped morning supplements.")
        return
    await collect_supplement_stack(
        name=answers.get("supplements", "morning stack"),
        dose="1",
        unit="serving",
        notes=f"Compliance: {answers.get('taken', '')}. {answers.get('notes', '')}",
    )


async def _handle_intake_log(answers: dict[str, str]) -> None:
    """Process intake log questionnaire answers."""
    substance = answers.get("substance", "")
    if not substance or substance.lower() in ("none", "no", "n/a"):
        logger.info("No intake reported for evening log.")
        return
    category = answers.get("category", "supplement")
    await log_drug_intake(
        substance=substance,
        amount=answers.get("amount", "0"),
        unit=answers.get("unit", "mg"),
        category=category,
    )
    if category == "addiction-therapy" and _questionnaire_ui is not None:
        from integra.integrations.halt import run_halt_check

        await run_halt_check(substance=substance, ui=_questionnaire_ui, config=settings)


async def _handle_diary_entry(answers: dict[str, str]) -> None:
    """Store on-demand diary answers in the data lake, then run advisor."""
    from integra.data.collectors import collect_diary

    await collect_diary(answers=answers)

    if _advisor_router is not None:
        from integra.integrations.advisor import run_advisor
        from integra.integrations.channels.router import ChannelRouter

        if isinstance(_advisor_router, ChannelRouter):
            await run_advisor(answers, _advisor_router, settings)


_ANSWER_HANDLERS: dict[str, AnswerHandler] = {
    "supplement_check": _handle_supplement_check,
    "intake_log": _handle_intake_log,
    "diary_entry": _handle_diary_entry,
}


def register_answer_handler(name: str, handler: AnswerHandler) -> None:
    """Register a new answer handler for scheduled questionnaires."""
    _ANSWER_HANDLERS[name] = handler


async def _process_answers(handler_name: str, answers: dict[str, str]) -> None:
    """Process questionnaire answers through the registered handler."""
    handler = _ANSWER_HANDLERS.get(handler_name)
    if handler is None:
        logger.error("Unknown answer handler: %s", handler_name)
        return
    await handler(answers)


class Scheduler:
    """Async scheduler that runs questionnaires at configured times."""

    def __init__(self, schedules: list[ScheduleEntry] | None = None) -> None:
        self.schedules = schedules or _default_schedules()
        self._task: asyncio.Task[None] | None = None
        self._active_questionnaire: asyncio.Task[None] | None = None
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

    async def interrupt_current(self) -> bool:
        """Cancel any running questionnaire task. Returns True if cancelled."""
        if self._active_questionnaire is not None and not self._active_questionnaire.done():
            self._active_questionnaire.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._active_questionnaire
            self._active_questionnaire = None
            return True
        return False

    async def _run_entry(self, entry: ScheduleEntry) -> None:
        """Run a single schedule entry questionnaire."""
        if _questionnaire_ui is None:
            logger.error("No questionnaire UI set — skipping %s", entry.name)
            return
        answers = await run_questionnaire(entry.questionnaire, ui=_questionnaire_ui)
        await _process_answers(entry.handler_name, answers)

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
                    self._active_questionnaire = asyncio.create_task(self._run_entry(entry))
                    try:
                        await self._active_questionnaire
                    except asyncio.CancelledError:
                        logger.info("Questionnaire %s was interrupted", entry.name)
                    except Exception:
                        logger.exception("Error in scheduled questionnaire %s", entry.name)
                    finally:
                        self._active_questionnaire = None

            await asyncio.sleep(30)

    async def trigger_now(self, schedule_name: str) -> dict[str, str] | None:
        """Manually trigger a scheduled questionnaire (for testing/on-demand)."""
        matched: ScheduleEntry | None = None
        for entry in self.schedules:
            if entry.name == schedule_name:
                matched = entry
                break
        if matched is None:
            logger.error("Unknown schedule: %s", schedule_name)
            return None
        if _questionnaire_ui is None:
            logger.error("No questionnaire UI set — cannot trigger %s", schedule_name)
            return None
        answers: dict[str, str] = {}

        async def _capture(e: ScheduleEntry) -> None:
            nonlocal answers
            answers = await run_questionnaire(e.questionnaire, ui=_questionnaire_ui)
            await _process_answers(e.handler_name, answers)

        self._active_questionnaire = asyncio.create_task(_capture(matched))
        try:
            await self._active_questionnaire
        except asyncio.CancelledError:
            logger.info("Questionnaire %s was interrupted", schedule_name)
        finally:
            self._active_questionnaire = None
        return answers if answers else None
