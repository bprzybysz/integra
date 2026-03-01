"""Tests for integra.integrations.scheduler."""

from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock, patch

from integra.integrations.scheduler import (
    _ANSWER_HANDLERS,
    MORNING_SUPPLEMENT_CHECK,
    ON_DEMAND_DIARY,
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

        mock_ui = AsyncMock()
        with (
            patch("integra.integrations.scheduler._questionnaire_ui", mock_ui),
            patch(
                "integra.integrations.scheduler.collect_supplement_stack",
                new_callable=AsyncMock,
            ) as mock_collect,
        ):
            mock_collect.return_value = '{"status": "stored"}'
            result = await scheduler.trigger_now("test_check")

        assert result is not None
        assert result["taken"] == "Yes - all"


class TestOnDemandDiary:
    def test_on_demand_diary_questionnaire_defined(self) -> None:
        assert len(ON_DEMAND_DIARY.questions) == 4
        field_names = {q.field_name for q in ON_DEMAND_DIARY.questions}
        assert field_names == {"content", "mood", "substance", "notes"}

    async def test_interrupt_current_no_active(self) -> None:
        scheduler = Scheduler(schedules=[])
        result = await scheduler.interrupt_current()
        assert result is False

    def test_diary_handler_registered(self) -> None:
        assert "diary_entry" in _ANSWER_HANDLERS


# ---------------------------------------------------------------------------
# Issue #27: Scheduler timing
# ---------------------------------------------------------------------------


class TestSchedulerLoop:
    """Issue #27 — scheduler timing, fired_today reset, duplicate times.

    Strategy: call scheduler._loop() directly as a coroutine rather than via
    start() (which spawns a background task). This avoids asyncio scheduling
    races and gives deterministic control. We set scheduler._running=False from
    inside fake_now to stop the loop after the desired number of ticks.
    asyncio.sleep is mocked so the 30-second sleep returns immediately.
    """

    # Test 1: _loop() fires a questionnaire when datetime.now() matches trigger time.
    # NOTE: scheduler._loop() calls datetime.now().astimezone() — the .astimezone()
    # converts UTC to local time. To avoid timezone-dependent failures, we use naive
    # datetimes (no tzinfo) which .astimezone() treats as local, keeping hour/minute intact.
    @patch("integra.integrations.scheduler.asyncio.sleep", new_callable=AsyncMock)
    @patch("integra.integrations.scheduler.run_questionnaire", new_callable=AsyncMock)
    async def test_loop_fires_at_matching_time(
        self,
        mock_run: AsyncMock,
        mock_sleep: AsyncMock,
    ) -> None:
        mock_run.return_value = {"taken": "Yes - all", "supplements": "all"}

        entry = ScheduleEntry(
            name="morning_test",
            trigger_time=time(8, 30),
            questionnaire=MORNING_SUPPLEMENT_CHECK,
            handler_name="supplement_check",
        )
        scheduler = Scheduler(schedules=[entry])
        scheduler._running = True

        call_count = 0

        def fake_now(*_args: object, **_kwargs: object) -> datetime:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Naive local datetime at 08:30 — astimezone() keeps 08:30 local
                return datetime(2026, 1, 1, 8, 30, 0)
            scheduler._running = False
            return datetime(2026, 1, 1, 8, 31, 0)

        mock_ui = AsyncMock()
        with (
            patch("integra.integrations.scheduler.datetime") as mock_dt,
            patch("integra.integrations.scheduler._questionnaire_ui", mock_ui),
            patch(
                "integra.integrations.scheduler.collect_supplement_stack",
                new_callable=AsyncMock,
            ) as mock_collect,
        ):
            mock_dt.now.side_effect = fake_now
            mock_collect.return_value = '{"status": "stored"}'
            await scheduler._loop()

        mock_run.assert_called_once()

    # Test 2: fired_today resets at midnight.
    # At 00:00: midnight reset clears fired_today, then entry matches → fires once.
    # At 00:01: no match, no additional fire.
    @patch("integra.integrations.scheduler.asyncio.sleep", new_callable=AsyncMock)
    @patch("integra.integrations.scheduler.run_questionnaire", new_callable=AsyncMock)
    async def test_fired_today_resets_at_midnight(
        self,
        mock_run: AsyncMock,
        mock_sleep: AsyncMock,
    ) -> None:
        mock_run.return_value = {"taken": "Yes - all", "supplements": "all"}

        entry = ScheduleEntry(
            name="midnight_test",
            trigger_time=time(0, 0),
            questionnaire=MORNING_SUPPLEMENT_CHECK,
            handler_name="supplement_check",
        )
        scheduler = Scheduler(schedules=[entry])
        scheduler._running = True

        tick = 0

        def fake_now(*_args: object, **_kwargs: object) -> datetime:
            nonlocal tick
            tick += 1
            if tick == 1:
                return datetime(2026, 1, 1, 0, 0, 0)  # midnight — fires
            if tick == 2:
                return datetime(2026, 1, 1, 0, 1, 0)  # 00:01 — no match
            scheduler._running = False
            return datetime(2026, 1, 1, 0, 2, 0)

        mock_ui = AsyncMock()
        with (
            patch("integra.integrations.scheduler.datetime") as mock_dt,
            patch("integra.integrations.scheduler._questionnaire_ui", mock_ui),
            patch(
                "integra.integrations.scheduler.collect_supplement_stack",
                new_callable=AsyncMock,
            ) as mock_collect,
        ):
            mock_dt.now.side_effect = fake_now
            mock_collect.return_value = '{"status": "stored"}'
            await scheduler._loop()

        assert mock_run.call_count == 1

    # Test 3: two entries at same trigger time, different names — both fire independently.
    @patch("integra.integrations.scheduler.asyncio.sleep", new_callable=AsyncMock)
    @patch("integra.integrations.scheduler.run_questionnaire", new_callable=AsyncMock)
    async def test_duplicate_schedule_times_both_fire(
        self,
        mock_run: AsyncMock,
        mock_sleep: AsyncMock,
    ) -> None:
        mock_run.return_value = {"taken": "Yes - all", "supplements": "all"}

        entry_a = ScheduleEntry(
            name="check_a",
            trigger_time=time(9, 0),
            questionnaire=MORNING_SUPPLEMENT_CHECK,
            handler_name="supplement_check",
        )
        entry_b = ScheduleEntry(
            name="check_b",
            trigger_time=time(9, 0),
            questionnaire=MORNING_SUPPLEMENT_CHECK,
            handler_name="supplement_check",
        )
        scheduler = Scheduler(schedules=[entry_a, entry_b])
        scheduler._running = True

        tick = 0

        def fake_now(*_args: object, **_kwargs: object) -> datetime:
            nonlocal tick
            tick += 1
            if tick == 1:
                return datetime(2026, 1, 1, 9, 0, 0)  # 09:00 — both fire
            scheduler._running = False
            return datetime(2026, 1, 1, 9, 1, 0)

        mock_ui = AsyncMock()
        with (
            patch("integra.integrations.scheduler.datetime") as mock_dt,
            patch("integra.integrations.scheduler._questionnaire_ui", mock_ui),
            patch(
                "integra.integrations.scheduler.collect_supplement_stack",
                new_callable=AsyncMock,
            ) as mock_collect,
        ):
            mock_dt.now.side_effect = fake_now
            mock_collect.return_value = '{"status": "stored"}'
            await scheduler._loop()

        # check_a and check_b have distinct names — both fire once at 09:00
        assert mock_run.call_count == 2
