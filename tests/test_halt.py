"""Tests for integra.integrations.halt and HALT framework wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from integra.data.schemas import make_trigger_context
from integra.integrations.halt import (
    HALT_QUESTIONNAIRE,
    _parse_craving_intensity,
    run_halt_check,
)
from integra.integrations.questionnaire import QuestionType

# ---- HALT_QUESTIONNAIRE structure ----


class TestHaltQuestionnaire:
    def test_has_six_questions(self) -> None:
        assert len(HALT_QUESTIONNAIRE.questions) == 6

    def test_field_names(self) -> None:
        fields = [q.field_name for q in HALT_QUESTIONNAIRE.questions]
        assert fields == [
            "hungry",
            "angry",
            "lonely",
            "tired",
            "craving_intensity",
            "situation_notes",
        ]

    def test_first_four_are_selection(self) -> None:
        for q in HALT_QUESTIONNAIRE.questions[:4]:
            assert q.question_type == QuestionType.SELECTION
            assert q.options == ["Yes", "No"]

    def test_craving_intensity_is_text(self) -> None:
        q = HALT_QUESTIONNAIRE.questions[4]
        assert q.field_name == "craving_intensity"
        assert q.question_type == QuestionType.TEXT

    def test_situation_notes_optional(self) -> None:
        q = HALT_QUESTIONNAIRE.questions[5]
        assert q.field_name == "situation_notes"
        assert q.required is False
        assert q.default == ""

    def test_title(self) -> None:
        assert HALT_QUESTIONNAIRE.title == "HALT Check"


# ---- _parse_craving_intensity ----


class TestParseCravingIntensity:
    def test_valid_midrange(self) -> None:
        assert _parse_craving_intensity("7") == 7

    def test_clamps_above_10(self) -> None:
        assert _parse_craving_intensity("15") == 10

    def test_clamps_below_1(self) -> None:
        assert _parse_craving_intensity("0") == 1

    def test_negative_clamped_to_1(self) -> None:
        assert _parse_craving_intensity("-5") == 1

    def test_unparseable_returns_5(self) -> None:
        assert _parse_craving_intensity("abc") == 5

    def test_empty_returns_5(self) -> None:
        assert _parse_craving_intensity("") == 5

    def test_boundary_1(self) -> None:
        assert _parse_craving_intensity("1") == 1

    def test_boundary_10(self) -> None:
        assert _parse_craving_intensity("10") == 10

    def test_whitespace_stripped(self) -> None:
        assert _parse_craving_intensity("  8  ") == 8


# ---- run_halt_check ----


class TestRunHaltCheck:
    async def test_parses_yes_no_correctly(self) -> None:
        ui = AsyncMock()
        config = MagicMock()
        config.age_recipient = "age1test"
        config.data_lake_path = MagicMock()
        config.data_audit_path = MagicMock()

        with (
            patch(
                "integra.integrations.halt.run_questionnaire",
                new_callable=AsyncMock,
            ) as mock_run,
            patch("integra.integrations.halt._store_record") as mock_store,
        ):
            mock_run.return_value = {
                "hungry": "Yes",
                "angry": "No",
                "lonely": "Yes",
                "tired": "No",
                "craving_intensity": "7",
                "situation_notes": "test note",
            }
            ctx = await run_halt_check(substance="3-CMC", ui=ui, config=config)

        assert ctx["hungry"] is True
        assert ctx["angry"] is False
        assert ctx["lonely"] is True
        assert ctx["tired"] is False
        assert ctx["craving_intensity"] == 7
        assert ctx["situation_notes"] == "test note"
        assert ctx["substance"] == "3-CMC"
        mock_store.assert_called_once()
        call_args = mock_store.call_args
        assert call_args[0][1] == "halt_context"

    async def test_clamps_craving_intensity_high(self) -> None:
        ui = AsyncMock()
        config = MagicMock()

        with (
            patch(
                "integra.integrations.halt.run_questionnaire",
                new_callable=AsyncMock,
                return_value={
                    "hungry": "No",
                    "angry": "No",
                    "lonely": "No",
                    "tired": "No",
                    "craving_intensity": "15",
                    "situation_notes": "",
                },
            ),
            patch("integra.integrations.halt._store_record"),
        ):
            ctx = await run_halt_check(substance="K", ui=ui, config=config)

        assert ctx["craving_intensity"] == 10

    async def test_craving_intensity_unparseable_defaults_5(self) -> None:
        ui = AsyncMock()
        config = MagicMock()

        with (
            patch(
                "integra.integrations.halt.run_questionnaire",
                new_callable=AsyncMock,
                return_value={
                    "hungry": "No",
                    "angry": "No",
                    "lonely": "No",
                    "tired": "No",
                    "craving_intensity": "abc",
                    "situation_notes": "",
                },
            ),
            patch("integra.integrations.halt._store_record"),
        ):
            ctx = await run_halt_check(substance="K", ui=ui, config=config)

        assert ctx["craving_intensity"] == 5

    async def test_stores_record_under_halt_context(self) -> None:
        ui = AsyncMock()
        config = MagicMock()

        with (
            patch(
                "integra.integrations.halt.run_questionnaire",
                new_callable=AsyncMock,
                return_value={
                    "hungry": "Yes",
                    "angry": "Yes",
                    "lonely": "Yes",
                    "tired": "Yes",
                    "craving_intensity": "9",
                    "situation_notes": "all flags",
                },
            ),
            patch("integra.integrations.halt._store_record") as mock_store,
        ):
            await run_halt_check(substance="3-CMC", ui=ui, config=config)

        mock_store.assert_called_once()
        stored_record, category, _ = mock_store.call_args[0]
        assert category == "halt_context"
        assert stored_record["substance"] == "3-CMC"
        assert stored_record["hungry"] is True

    async def test_returns_trigger_context(self) -> None:
        ui = AsyncMock()
        config = MagicMock()

        with (
            patch(
                "integra.integrations.halt.run_questionnaire",
                new_callable=AsyncMock,
                return_value={
                    "hungry": "No",
                    "angry": "No",
                    "lonely": "No",
                    "tired": "No",
                    "craving_intensity": "3",
                    "situation_notes": "",
                },
            ),
            patch("integra.integrations.halt._store_record"),
        ):
            ctx = await run_halt_check(substance="subst", ui=ui, config=config)

        assert isinstance(ctx, dict)
        assert "timestamp" in ctx
        assert ctx["timestamp"] != ""


# ---- make_trigger_context ----


class TestMakeTriggerContextTimestamp:
    def test_timestamp_defaults_to_now_if_none(self) -> None:
        ctx = make_trigger_context()
        assert ctx["timestamp"] != ""
        # Should be parseable ISO format
        from datetime import datetime

        dt = datetime.fromisoformat(ctx["timestamp"])
        assert dt is not None

    def test_explicit_timestamp_preserved(self) -> None:
        ts = "2026-03-01T10:00:00+01:00"
        ctx = make_trigger_context(timestamp=ts)
        assert ctx["timestamp"] == ts

    def test_substance_field_present(self) -> None:
        ctx = make_trigger_context(substance="K/tip")
        assert ctx["substance"] == "K/tip"


# ---- Scheduler wiring ----


class TestSchedulerHaltWiring:
    async def test_handle_intake_log_calls_halt_for_addiction_therapy(self) -> None:
        mock_ui = AsyncMock()

        with (
            patch("integra.integrations.scheduler.log_drug_intake", new_callable=AsyncMock) as mock_log,
            patch("integra.integrations.scheduler._questionnaire_ui", mock_ui),
            patch("integra.integrations.halt.run_questionnaire", new_callable=AsyncMock) as mock_rq,
            patch("integra.integrations.halt._store_record"),
        ):
            mock_log.return_value = '{"status": "logged"}'
            mock_rq.return_value = {
                "hungry": "Yes",
                "angry": "No",
                "lonely": "No",
                "tired": "No",
                "craving_intensity": "6",
                "situation_notes": "",
            }

            from integra.integrations.scheduler import _handle_intake_log

            await _handle_intake_log(
                {
                    "substance": "3-CMC",
                    "amount": "50",
                    "unit": "mg",
                    "category": "addiction-therapy",
                }
            )

        mock_log.assert_called_once()
        mock_rq.assert_called_once()

    async def test_handle_intake_log_skips_halt_for_supplement(self) -> None:
        mock_ui = AsyncMock()

        with (
            patch("integra.integrations.scheduler.log_drug_intake", new_callable=AsyncMock) as mock_log,
            patch("integra.integrations.scheduler._questionnaire_ui", mock_ui),
            patch("integra.integrations.halt.run_questionnaire", new_callable=AsyncMock) as mock_rq,
            patch("integra.integrations.halt._store_record"),
        ):
            mock_log.return_value = '{"status": "logged"}'

            from integra.integrations.scheduler import _handle_intake_log

            await _handle_intake_log(
                {
                    "substance": "Magnesium",
                    "amount": "400",
                    "unit": "mg",
                    "category": "supplement",
                }
            )

        mock_log.assert_called_once()
        mock_rq.assert_not_called()

    async def test_handle_intake_log_skips_halt_when_ui_is_none(self) -> None:
        with (
            patch("integra.integrations.scheduler.log_drug_intake", new_callable=AsyncMock) as mock_log,
            patch("integra.integrations.scheduler._questionnaire_ui", None),
            patch("integra.integrations.halt.run_questionnaire", new_callable=AsyncMock) as mock_rq,
            patch("integra.integrations.halt._store_record"),
        ):
            mock_log.return_value = '{"status": "logged"}'

            from integra.integrations.scheduler import _handle_intake_log

            await _handle_intake_log(
                {
                    "substance": "3-CMC",
                    "amount": "50",
                    "unit": "mg",
                    "category": "addiction-therapy",
                }
            )

        mock_log.assert_called_once()
        mock_rq.assert_not_called()

    async def test_handle_intake_log_skips_halt_for_medication(self) -> None:
        mock_ui = AsyncMock()

        with (
            patch("integra.integrations.scheduler.log_drug_intake", new_callable=AsyncMock) as mock_log,
            patch("integra.integrations.scheduler._questionnaire_ui", mock_ui),
            patch("integra.integrations.halt.run_questionnaire", new_callable=AsyncMock) as mock_rq,
        ):
            mock_log.return_value = '{"status": "logged"}'

            from integra.integrations.scheduler import _handle_intake_log

            await _handle_intake_log(
                {
                    "substance": "Ritalin",
                    "amount": "10",
                    "unit": "mg",
                    "category": "medication",
                }
            )

        mock_log.assert_called_once()
        mock_rq.assert_not_called()
