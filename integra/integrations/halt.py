"""HALT questionnaire for addiction-therapy intake events."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from integra.core.config import Settings, settings
from integra.data.collectors import _store_record
from integra.data.schemas import TriggerContext, make_trigger_context
from integra.integrations.questionnaire import (
    Question,
    Questionnaire,
    QuestionType,
    run_questionnaire,
)

if TYPE_CHECKING:
    from integra.integrations.questionnaire_ui import QuestionnaireUI

logger = logging.getLogger(__name__)

HALT_QUESTIONNAIRE = Questionnaire(
    title="HALT Check",
    questions=[
        Question(
            text="Are you Hungry right now?",
            field_name="hungry",
            question_type=QuestionType.SELECTION,
            options=["Yes", "No"],
        ),
        Question(
            text="Are you Angry or frustrated?",
            field_name="angry",
            question_type=QuestionType.SELECTION,
            options=["Yes", "No"],
        ),
        Question(
            text="Are you feeling Lonely?",
            field_name="lonely",
            question_type=QuestionType.SELECTION,
            options=["Yes", "No"],
        ),
        Question(
            text="Are you Tired?",
            field_name="tired",
            question_type=QuestionType.SELECTION,
            options=["Yes", "No"],
        ),
        Question(
            text="Craving intensity (1-10)?",
            field_name="craving_intensity",
            question_type=QuestionType.TEXT,
        ),
        Question(
            text="Any notes about the situation?",
            field_name="situation_notes",
            question_type=QuestionType.TEXT,
            required=False,
            default="",
        ),
    ],
)


def _parse_craving_intensity(raw: str) -> int:
    """Parse craving intensity from text answer, clamp to 1-10, default 5."""
    try:
        value = int(raw.strip())
    except (ValueError, AttributeError):
        return 5
    return max(1, min(10, value))


async def run_halt_check(
    substance: str,
    ui: QuestionnaireUI,
    config: Settings = settings,
) -> TriggerContext:
    """Run HALT questionnaire and store TriggerContext record in lake.

    Returns the TriggerContext. Stores under category 'halt_context'.
    craving_intensity: parse int from answer, clamp to 1-10. Default 5 if unparseable.
    hungry/angry/lonely/tired: True if answer == "Yes".
    """
    answers = await run_questionnaire(HALT_QUESTIONNAIRE, ui=ui)

    ctx = make_trigger_context(
        hungry=answers.get("hungry") == "Yes",
        angry=answers.get("angry") == "Yes",
        lonely=answers.get("lonely") == "Yes",
        tired=answers.get("tired") == "Yes",
        craving_intensity=_parse_craving_intensity(answers.get("craving_intensity", "5")),
        situation_notes=answers.get("situation_notes", ""),
        substance=substance,
    )

    _store_record(dict(ctx), "halt_context", config)
    logger.info("Stored HALT context for substance: %s", substance)
    return ctx
