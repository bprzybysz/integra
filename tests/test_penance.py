"""Tests for integra/integrations/penance.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integra.core.config import Settings
from integra.data.schemas import DiaryType, PenanceSeverity
from integra.integrations.penance import (
    PENANCE_CREDITS,
    PENANCE_QUESTIONNAIRES,
    compute_severity,
    trigger_penance,
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


# ---------------------------------------------------------------------------
# compute_severity
# ---------------------------------------------------------------------------


def test_compute_severity_minor() -> None:
    assert compute_severity(1.0, 0) == PenanceSeverity.MINOR
    assert compute_severity(0.5, 2) == PenanceSeverity.MINOR


def test_compute_severity_standard() -> None:
    assert compute_severity(2.0, 0) == PenanceSeverity.STANDARD
    assert compute_severity(3.0, 1) == PenanceSeverity.STANDARD


def test_compute_severity_escalated_units_over() -> None:
    assert compute_severity(3.1, 0) == PenanceSeverity.ESCALATED
    assert compute_severity(10.0, 0) == PenanceSeverity.ESCALATED


def test_compute_severity_escalated_relapse_count() -> None:
    assert compute_severity(0.5, 3) == PenanceSeverity.ESCALATED
    assert compute_severity(1.0, 5) == PenanceSeverity.ESCALATED


def test_compute_severity_boundary_standard_not_escalated() -> None:
    # Exactly 3 units → STANDARD (not ESCALATED, rule is > 3)
    assert compute_severity(3.0, 2) == PenanceSeverity.STANDARD


# ---------------------------------------------------------------------------
# PENANCE_QUESTIONNAIRES structure
# ---------------------------------------------------------------------------


def test_minor_questionnaire_has_3_questions() -> None:
    q = PENANCE_QUESTIONNAIRES[PenanceSeverity.MINOR]
    assert len(q.questions) == 3


def test_standard_questionnaire_has_5_questions() -> None:
    q = PENANCE_QUESTIONNAIRES[PenanceSeverity.STANDARD]
    assert len(q.questions) == 5


def test_escalated_questionnaire_has_8_questions() -> None:
    q = PENANCE_QUESTIONNAIRES[PenanceSeverity.ESCALATED]
    assert len(q.questions) == 8


def test_standard_questionnaire_has_mood_selection() -> None:
    from integra.integrations.questionnaire import QuestionType

    q = PENANCE_QUESTIONNAIRES[PenanceSeverity.STANDARD]
    mood_q = next(qn for qn in q.questions if qn.field_name == "mood")
    assert mood_q.question_type == QuestionType.SELECTION
    assert "low" in mood_q.options


def test_escalated_questionnaire_has_coping_plan() -> None:
    q = PENANCE_QUESTIONNAIRES[PenanceSeverity.ESCALATED]
    field_names = [qn.field_name for qn in q.questions]
    assert "coping_plan" in field_names
    assert "halt_review" in field_names
    assert "commitment" in field_names


# ---------------------------------------------------------------------------
# PENANCE_CREDITS
# ---------------------------------------------------------------------------


def test_penance_credits_values() -> None:
    assert PENANCE_CREDITS[PenanceSeverity.MINOR] == 0.5
    assert PENANCE_CREDITS[PenanceSeverity.STANDARD] == 0.5
    assert PENANCE_CREDITS[PenanceSeverity.ESCALATED] == 0.3


# ---------------------------------------------------------------------------
# trigger_penance — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_penance_minor_runs_diary() -> None:
    config = _make_settings()
    ui = MagicMock()
    router = MagicMock()
    fake_answers = {"what": "slipped", "trigger": "stress", "takeaway": "avoid triggers"}

    with (
        patch("integra.integrations.penance.run_questionnaire", AsyncMock(return_value=fake_answers)),
        patch("integra.integrations.penance._store_record") as mock_store,
    ):
        record = await trigger_penance(
            substance="3-cmc",
            units_over=0.8,
            relapse_count_this_week=1,
            ui=ui,
            router=router,
            config=config,
        )

    assert record["penance_credit"] == 0.5
    assert record["severity"] == PenanceSeverity.MINOR
    assert record["diary_type"] == DiaryType.VIOLATION
    assert record["substance"] == "3-cmc"
    mock_store.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_penance_standard_runs_diary() -> None:
    config = _make_settings()
    ui = MagicMock()
    router = MagicMock()
    fake_answers = {
        "what": "slipped",
        "trigger": "stress",
        "takeaway": "take a walk",
        "mood": "low",
        "alternative_action": "delay",
    }

    with (
        patch("integra.integrations.penance.run_questionnaire", AsyncMock(return_value=fake_answers)),
        patch("integra.integrations.penance._store_record") as mock_store,
    ):
        record = await trigger_penance(
            substance="k",
            units_over=2.5,
            relapse_count_this_week=1,
            ui=ui,
            router=router,
            config=config,
        )

    assert record["penance_credit"] == 0.5
    assert record["severity"] == PenanceSeverity.STANDARD
    mock_store.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_penance_escalated_approved() -> None:
    config = _make_settings()
    ui = MagicMock()
    router = MagicMock()
    router.ask_confirmation = AsyncMock(return_value="APPROVED")
    fake_answers = {
        "what": "heavy use",
        "trigger": "party",
        "takeaway": "stay home",
        "mood": "rough",
        "alternative_action": "call a friend",
        "halt_review": "lonely, tired",
        "commitment": "no use this week",
        "coping_plan": "delay 15 min",
    }

    with (
        patch("integra.integrations.penance.run_questionnaire", AsyncMock(return_value=fake_answers)),
        patch("integra.integrations.penance._store_record") as mock_store,
    ):
        record = await trigger_penance(
            substance="x",
            units_over=4.0,
            relapse_count_this_week=0,
            ui=ui,
            router=router,
            config=config,
        )

    assert record["penance_credit"] == 0.3
    assert record["severity"] == PenanceSeverity.ESCALATED
    router.ask_confirmation.assert_called_once()
    mock_store.assert_called_once()


# ---------------------------------------------------------------------------
# trigger_penance — HIL gate denied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_penance_escalated_denied_returns_zero_credit() -> None:
    config = _make_settings()
    ui = MagicMock()
    router = MagicMock()
    router.ask_confirmation = AsyncMock(return_value="DENIED by user")

    with (
        patch("integra.integrations.penance.run_questionnaire") as mock_q,
        patch("integra.integrations.penance._store_record") as mock_store,
    ):
        record = await trigger_penance(
            substance="x",
            units_over=5.0,
            relapse_count_this_week=0,
            ui=ui,
            router=router,
            config=config,
        )

    # Questionnaire should NOT have been called
    mock_q.assert_not_called()
    # Record still stored (denial record)
    mock_store.assert_called_once()
    assert record["penance_credit"] == 0.0
    assert record["severity"] == PenanceSeverity.ESCALATED


@pytest.mark.asyncio
async def test_trigger_penance_escalated_third_relapse_asks_hil() -> None:
    config = _make_settings()
    ui = MagicMock()
    router = MagicMock()
    router.ask_confirmation = AsyncMock(return_value="APPROVED")
    fake_answers = {
        "what": "a",
        "trigger": "b",
        "takeaway": "c",
        "mood": "neutral",
        "alternative_action": "d",
        "halt_review": "e",
        "commitment": "f",
        "coping_plan": "g",
    }

    with (
        patch("integra.integrations.penance.run_questionnaire", AsyncMock(return_value=fake_answers)),
        patch("integra.integrations.penance._store_record"),
    ):
        record = await trigger_penance(
            substance="3-cmc",
            units_over=0.5,
            relapse_count_this_week=3,  # 3rd relapse → ESCALATED
            ui=ui,
            router=router,
            config=config,
        )

    router.ask_confirmation.assert_called_once()
    assert record["severity"] == PenanceSeverity.ESCALATED


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_compute_severity_exactly_one_unit_is_minor() -> None:
    # units_over == 1.0 → MINOR (boundary: <= 1)
    assert compute_severity(1.0, 0) == PenanceSeverity.MINOR


def test_compute_severity_just_over_one_is_standard() -> None:
    # units_over == 1.01 → STANDARD
    assert compute_severity(1.01, 0) == PenanceSeverity.STANDARD


def test_compute_severity_exactly_three_not_escalated() -> None:
    # units_over == 3.0, relapse < 3 → STANDARD (boundary: <= 3)
    assert compute_severity(3.0, 2) == PenanceSeverity.STANDARD


def test_questionnaire_field_names_cover_required_fields() -> None:
    """All 3 base fields present in every questionnaire."""
    base_fields = {"what", "trigger", "takeaway"}
    for severity, questionnaire in PENANCE_QUESTIONNAIRES.items():
        field_names = {q.field_name for q in questionnaire.questions}
        assert base_fields.issubset(field_names), f"Missing base fields in {severity}"
