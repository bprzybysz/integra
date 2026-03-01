"""Penance system — triggered on zero-quota relapse."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from integra.core.config import Settings
from integra.data.collectors import _store_record
from integra.data.schemas import DiaryType, PenanceSeverity, make_diary_record
from integra.integrations.questionnaire import (
    Question,
    Questionnaire,
    QuestionType,
    run_questionnaire,
)
from integra.integrations.questionnaire_ui import QuestionnaireUI

if TYPE_CHECKING:
    from integra.integrations.channels.router import ChannelRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity computation
# ---------------------------------------------------------------------------


def compute_severity(units_over: float, relapse_count_this_week: int) -> PenanceSeverity:
    """Compute penance severity from units over quota and weekly relapse count.

    MINOR: 0 < units_over <= 1 and relapse_count_this_week < 3
    STANDARD: 1 < units_over <= 3 and relapse_count_this_week < 3
    ESCALATED: units_over > 3 OR relapse_count_this_week >= 3
    """
    if relapse_count_this_week >= 3 or units_over > 3:
        return PenanceSeverity.ESCALATED
    if units_over <= 1:
        return PenanceSeverity.MINOR
    return PenanceSeverity.STANDARD


# ---------------------------------------------------------------------------
# Questionnaires
# ---------------------------------------------------------------------------

PENANCE_QUESTIONNAIRES: dict[str, Questionnaire] = {
    PenanceSeverity.MINOR: Questionnaire(
        title="Violation Diary (Minor)",
        questions=[
            Question(
                text="What happened?",
                field_name="what",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="What triggered it?",
                field_name="trigger",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="Key takeaway?",
                field_name="takeaway",
                question_type=QuestionType.TEXT,
            ),
        ],
    ),
    PenanceSeverity.STANDARD: Questionnaire(
        title="Violation Diary (Standard)",
        questions=[
            Question(
                text="What happened?",
                field_name="what",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="What triggered it?",
                field_name="trigger",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="Key takeaway?",
                field_name="takeaway",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="Mood at the time?",
                field_name="mood",
                question_type=QuestionType.SELECTION,
                options=["great", "good", "neutral", "low", "rough"],
            ),
            Question(
                text="What alternative action could you have taken?",
                field_name="alternative_action",
                question_type=QuestionType.TEXT,
            ),
        ],
    ),
    PenanceSeverity.ESCALATED: Questionnaire(
        title="Violation Diary (Escalated)",
        questions=[
            Question(
                text="What happened?",
                field_name="what",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="What triggered it?",
                field_name="trigger",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="Key takeaway?",
                field_name="takeaway",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="Mood at the time?",
                field_name="mood",
                question_type=QuestionType.SELECTION,
                options=["great", "good", "neutral", "low", "rough"],
            ),
            Question(
                text="What alternative action could you have taken?",
                field_name="alternative_action",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="HALT review — which factors were present (hungry/angry/lonely/tired)?",
                field_name="halt_review",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="Commitment going forward?",
                field_name="commitment",
                question_type=QuestionType.TEXT,
            ),
            Question(
                text="Coping plan for next craving?",
                field_name="coping_plan",
                question_type=QuestionType.TEXT,
            ),
        ],
    ),
}

PENANCE_CREDITS: dict[str, float] = {
    PenanceSeverity.MINOR: 0.5,
    PenanceSeverity.STANDARD: 0.5,
    PenanceSeverity.ESCALATED: 0.3,
}

# ---------------------------------------------------------------------------
# Record helpers
# ---------------------------------------------------------------------------


def _make_penance_diary_record(
    substance: str,
    severity: PenanceSeverity,
    answers: dict[str, str],
    penance_credit: float,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a DiaryRecord dict for a penance violation diary."""
    qa_pairs = [{"q": k, "a": v} for k, v in answers.items()]
    record = make_diary_record(
        diary_type=DiaryType.VIOLATION,
        severity=str(severity),
        substance=substance,
        questions_asked=len(qa_pairs),
        answers=json.dumps(qa_pairs),
        penance_credit=penance_credit,
        timestamp=timestamp,
    )
    return dict(record)


# ---------------------------------------------------------------------------
# Main trigger function
# ---------------------------------------------------------------------------


async def trigger_penance(
    substance: str,
    units_over: float,
    relapse_count_this_week: int,
    ui: QuestionnaireUI,
    router: ChannelRouter,
    config: Settings,
) -> dict[str, Any]:
    """Run violation diary questionnaire and store penance record.

    For ESCALATED severity: send HIL confirmation via router.ask_confirmation()
    before starting diary. If denied, return a minimal record with penance_credit=0.
    """
    severity = compute_severity(units_over, relapse_count_this_week)
    credit = PENANCE_CREDITS[severity]
    ts = datetime.now(UTC).isoformat()

    if severity == PenanceSeverity.ESCALATED:
        confirmation = await router.ask_confirmation(
            f"Escalated violation detected for {substance} "
            f"({units_over:.1f} units over, {relapse_count_this_week} relapses this week). "
            "Start violation diary?"
        )
        if "APPROVED" not in confirmation.upper():
            logger.warning("Escalated penance diary denied for %s", substance)
            denied_record: dict[str, Any] = _make_penance_diary_record(
                substance=substance,
                severity=severity,
                answers={"denied": "HIL confirmation denied"},
                penance_credit=0.0,
                timestamp=ts,
            )
            _store_record(denied_record, "diary", config)
            return denied_record

    questionnaire = PENANCE_QUESTIONNAIRES[severity]
    answers = await run_questionnaire(questionnaire, ui)

    record = _make_penance_diary_record(
        substance=substance,
        severity=severity,
        answers=answers,
        penance_credit=credit,
        timestamp=ts,
    )
    _store_record(record, "diary", config)

    logger.info(
        "Stored penance diary: substance=%s severity=%s credit=%.1f",
        substance,
        severity,
        credit,
    )
    return record
