"""Tests for integra.integrations.scheduler."""

from __future__ import annotations

from datetime import time
from unittest.mock import AsyncMock, patch

from integra.integrations.scheduler import (
    MORNING_SUPPLEMENT_CHECK,
    ScheduleEntry,
    Scheduler,
    _process_answers,
)


class TestProcessAnswers:
    async def test_supplement_check_yes(self) -> None:
        with patch("integra.integrations.scheduler.collect_supplement_stack", new_callable=AsyncMock) as mock:
            mock.return_value = '{"status": "stored"}'
            await _process_answers("supplement_check", {"taken": "Yes - all", "supplements": "Vitamin D, Zinc"})
            mock.assert_called_once()

    async def test_supplement_check_no_skips(self) -> None:
        with patch("integra.integrations.scheduler.collect_supplement_stack", new_callable=AsyncMock) as mock:
            await _process_answers("supplement_check", {"taken": "No"})
            mock.assert_not_called()

    async def test_intake_log_records(self) -> None:
        with patch("integra.integrations.scheduler.log_drug_intake", new_callable=AsyncMock) as mock:
            mock.return_value = '{"status": "logged"}'
            await _process_answers(
                "intake_log",
                {
                    "substance": "Magnesium",
                    "amount": "400",
                    "unit": "mg",
                    "category": "supplement",
                },
            )
            mock.assert_called_once()

    async def test_intake_log_none_skips(self) -> None:
        with patch("integra.integrations.scheduler.log_drug_intake", new_callable=AsyncMock) as mock:
            await _process_answers("intake_log", {"substance": "none"})
            mock.assert_not_called()


class TestScheduler:
    async def test_start_and_stop(self) -> None:
        scheduler = Scheduler(schedules=[])
        await scheduler.start()
        assert scheduler._running is True
        await scheduler.stop()
        assert scheduler._running is False

    async def test_trigger_now_unknown(self) -> None:
        scheduler = Scheduler(schedules=[])
        result = await scheduler.trigger_now("nonexistent")
        assert result is None

    @patch("integra.integrations.scheduler.run_questionnaire", new_callable=AsyncMock)
    async def test_trigger_now_runs_questionnaire(self, mock_run: AsyncMock) -> None:
        mock_run.return_value = {"taken": "Yes - all", "supplements": "all"}

        entry = ScheduleEntry(
            name="test_check",
            trigger_time=time(8, 0),
            questionnaire=MORNING_SUPPLEMENT_CHECK,
            handler_name="supplement_check",
        )
        scheduler = Scheduler(schedules=[entry])

        with patch("integra.integrations.scheduler.collect_supplement_stack", new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = '{"status": "stored"}'
            result = await scheduler.trigger_now("test_check")

        assert result is not None
        assert result["taken"] == "Yes - all"
