"""Questionnaire data structures and runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from integra.integrations.questionnaire_ui import QuestionnaireUI

logger = logging.getLogger(__name__)


class QuestionType(StrEnum):
    """Supported question input types."""

    TEXT = "text"
    NUMERIC = "numeric"
    SELECTION = "selection"
    TIME = "time"


@dataclass
class Question:
    """A single question in a questionnaire."""

    text: str
    field_name: str
    question_type: QuestionType = QuestionType.TEXT
    options: list[str] = field(default_factory=list)
    required: bool = True
    default: str = ""


@dataclass
class Questionnaire:
    """An ordered list of questions to collect structured data."""

    title: str
    questions: list[Question]


async def run_questionnaire(
    questionnaire: Questionnaire,
    ui: QuestionnaireUI,
) -> dict[str, str]:
    """Run a questionnaire via the given UI, collecting answers sequentially.

    Args:
        questionnaire: The questionnaire to run.
        ui: The QuestionnaireUI backend to use for interaction.

    Returns:
        Dict mapping field_name -> answer string.
    """
    answers: dict[str, str] = {}

    await ui.send_status(f"📋 *{questionnaire.title}*", parse_mode="Markdown")

    for question in questionnaire.questions:
        if question.question_type == QuestionType.SELECTION:
            answer = await ui.ask_selection(question)
        else:
            answer = await ui.ask_text(question)
        answers[question.field_name] = answer

    await ui.send_status("✅ Questionnaire complete. Data recorded.")
    return answers
