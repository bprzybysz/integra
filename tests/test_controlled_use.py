"""Tests for integra/data/controlled_use.py and collectors.py CONTROLLED_USE branch."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from integra.data.controlled_use import (
    CONTROLLED_USE_CONFIG,
    evaluate_controlled_use,
)
from integra.data.schemas import ControlledUseRecord, make_controlled_use_record

TZ = ZoneInfo("Europe/Warsaw")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ts(hour: int, minute: int = 0) -> datetime:
    """Return an aware datetime at the given hour in Europe/Warsaw on a weekday."""
    # 2026-03-02 is a Monday — use a fixed date so DST is deterministic
    return datetime(2026, 3, 2, hour, minute, tzinfo=TZ)


def _make_record(
    substance: str = "bcd",
    amount: str = "1",
    ts: datetime | None = None,
) -> ControlledUseRecord:
    return make_controlled_use_record(
        substance=substance,
        amount=amount,
        unit="unit",
        timestamp=(ts or _make_ts(20)).isoformat(),
    )


# ---------------------------------------------------------------------------
# 1. Clean use — no violations
# ---------------------------------------------------------------------------


def test_clean_use_no_violations() -> None:
    """Under ceiling, outside work hours, cooldown OK → no violations."""
    ts = _make_ts(20)  # 20:00 — outside work hours
    recent: list[ControlledUseRecord] = [
        _make_record(ts=_make_ts(17, 30)),  # 2.5h ago
    ]
    record, coaching_needed, msg = evaluate_controlled_use(
        substance="bcd",
        amount="1",
        unit="unit",
        timestamp=ts,
        recent_records=recent,
        timezone_str="Europe/Warsaw",
    )
    assert not record["work_hours_violation"]
    assert not record["cooldown_violation"]
    assert not record["daily_ceiling_exceeded"]
    assert coaching_needed is False
    assert msg is None


# ---------------------------------------------------------------------------
# 2. Work-hours violation (10:00 CET)
# ---------------------------------------------------------------------------


def test_work_hours_violation() -> None:
    """Use at 10:00 local time triggers work_hours_violation."""
    ts = _make_ts(10)  # inside 09-17
    record, coaching_needed, msg = evaluate_controlled_use(
        substance="bcd",
        amount="1",
        unit="unit",
        timestamp=ts,
        recent_records=[],
        timezone_str="Europe/Warsaw",
    )
    assert record["work_hours_violation"] is True
    assert coaching_needed is True
    assert msg is not None
    assert "work hours" in msg


# ---------------------------------------------------------------------------
# 3. Cooldown violation (< 2h since last use)
# ---------------------------------------------------------------------------


def test_cooldown_violation() -> None:
    """Use within 2h of previous use triggers cooldown_violation."""
    ts = _make_ts(20)
    recent: list[ControlledUseRecord] = [
        _make_record(ts=ts - timedelta(hours=1)),  # only 1h ago
    ]
    record, coaching_needed, msg = evaluate_controlled_use(
        substance="bcd",
        amount="1",
        unit="unit",
        timestamp=ts,
        recent_records=recent,
        timezone_str="Europe/Warsaw",
    )
    assert record["cooldown_violation"] is True
    assert coaching_needed is True
    assert msg is not None
    assert "cooldown" in msg


# ---------------------------------------------------------------------------
# 4. Daily ceiling exceeded (5th use)
# ---------------------------------------------------------------------------


def test_daily_ceiling_exceeded() -> None:
    """5th use on the same day (ceiling=4) triggers daily_ceiling_exceeded."""
    ts = _make_ts(20)
    # 4 prior uses today, each 1 unit — adding 1 more = 5 > 4
    prior_ts = _make_ts(19) - timedelta(hours=3)
    recent: list[ControlledUseRecord] = [
        _make_record(ts=prior_ts - timedelta(hours=i * 0.1), amount="1") for i in range(4)
    ]
    record, coaching_needed, msg = evaluate_controlled_use(
        substance="bcd",
        amount="1",
        unit="unit",
        timestamp=ts,
        recent_records=recent,
        timezone_str="Europe/Warsaw",
    )
    assert record["daily_ceiling_exceeded"] is True
    assert coaching_needed is True
    assert msg is not None
    assert "ceiling" in msg


# ---------------------------------------------------------------------------
# 5. Multiple violations in one record
# ---------------------------------------------------------------------------


def test_multiple_violations() -> None:
    """Work hours + cooldown + ceiling can all fire together."""
    ts = _make_ts(10)  # inside work hours
    prior_ts = _make_ts(9, 30)  # 30 min ago → cooldown violated
    # 4 prior units today → +1 exceeds ceiling
    recent: list[ControlledUseRecord] = [
        _make_record(ts=prior_ts - timedelta(hours=i * 0.05), amount="1") for i in range(4)
    ]
    # Override the newest one to be within cooldown
    recent[-1] = _make_record(ts=prior_ts, amount="1")

    record, coaching_needed, msg = evaluate_controlled_use(
        substance="bcd",
        amount="1",
        unit="unit",
        timestamp=ts,
        recent_records=recent,
        timezone_str="Europe/Warsaw",
    )
    assert record["work_hours_violation"] is True
    assert record["cooldown_violation"] is True
    assert record["daily_ceiling_exceeded"] is True
    assert coaching_needed is True
    assert msg is not None


# ---------------------------------------------------------------------------
# 6. Unknown substance → no rules, plain record, no coaching
# ---------------------------------------------------------------------------


def test_unknown_substance_no_rules() -> None:
    """Unknown substance not in CONTROLLED_USE_CONFIG → no violations, no coaching."""
    ts = _make_ts(10)  # work hours — doesn't matter for unknown substance
    record, coaching_needed, msg = evaluate_controlled_use(
        substance="unknown_xyz",
        amount="99",
        unit="unit",
        timestamp=ts,
        recent_records=[],
        timezone_str="Europe/Warsaw",
    )
    assert not record["work_hours_violation"]
    assert not record["cooldown_violation"]
    assert not record["daily_ceiling_exceeded"]
    assert coaching_needed is False
    assert msg is None


# ---------------------------------------------------------------------------
# 7. Collector integration — log_drug_intake with CONTROLLED_USE (clean)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collector_log_drug_intake_controlled_use_clean() -> None:
    """log_drug_intake with CONTROLLED_USE stores record, returns no violations."""
    mock_cfg = MagicMock()
    mock_cfg.age_recipient = "test-recipient"
    mock_cfg.data_lake_path = MagicMock()
    mock_cfg.data_audit_path = MagicMock()
    mock_cfg.timezone = "Europe/Warsaw"

    ts = _make_ts(20).isoformat()

    with (
        patch("integra.data.collectors._store_record") as mock_store,
        patch(
            "integra.data.mcp_server.query_data",
            new=AsyncMock(return_value=json.dumps([])),
        ),
        patch(
            "integra.data.controlled_use.evaluate_controlled_use",
            wraps=evaluate_controlled_use,
        ),
    ):
        from integra.data.collectors import log_drug_intake

        result_raw = await log_drug_intake(
            substance="bcd",
            amount="1",
            unit="unit",
            category="controlled-use",
            timestamp=ts,
            config=mock_cfg,
        )

    result: dict[str, Any] = json.loads(result_raw)
    assert result["status"] == "logged"
    assert result["violations"] == []
    mock_store.assert_called_once()


# ---------------------------------------------------------------------------
# 8. Collector integration — log_drug_intake with CONTROLLED_USE (work hours)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collector_log_drug_intake_controlled_use_violation() -> None:
    """log_drug_intake at 10:00 returns work_hours_violation."""
    mock_cfg = MagicMock()
    mock_cfg.age_recipient = "test-recipient"
    mock_cfg.data_lake_path = MagicMock()
    mock_cfg.data_audit_path = MagicMock()
    mock_cfg.timezone = "Europe/Warsaw"

    ts = _make_ts(10).isoformat()

    with (
        patch("integra.data.collectors._store_record"),
        patch(
            "integra.data.mcp_server.query_data",
            new=AsyncMock(return_value=json.dumps([])),
        ),
    ):
        from integra.data.collectors import log_drug_intake

        result_raw = await log_drug_intake(
            substance="bcd",
            amount="1",
            unit="unit",
            category="controlled-use",
            timestamp=ts,
            config=mock_cfg,
        )

    result: dict[str, Any] = json.loads(result_raw)
    assert result["status"] == "logged"
    assert "work_hours_violation" in result["violations"]


# ---------------------------------------------------------------------------
# 9. Unknown substance via collector → falls through to plain IntakeRecord
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collector_unknown_substance_falls_through_to_intake() -> None:
    """Unknown substance in CONTROLLED_USE category → stores with no violations."""
    mock_cfg = MagicMock()
    mock_cfg.age_recipient = "test-recipient"
    mock_cfg.data_lake_path = MagicMock()
    mock_cfg.data_audit_path = MagicMock()
    mock_cfg.timezone = "Europe/Warsaw"

    ts = _make_ts(10).isoformat()  # work hours — no config → no violation

    with (
        patch("integra.data.collectors._store_record") as mock_store,
        patch(
            "integra.data.mcp_server.query_data",
            new=AsyncMock(return_value=json.dumps([])),
        ),
    ):
        from integra.data.collectors import log_drug_intake

        result_raw = await log_drug_intake(
            substance="unknown_substance_xyz",
            amount="1",
            unit="unit",
            category="controlled-use",
            timestamp=ts,
            config=mock_cfg,
        )

    result: dict[str, Any] = json.loads(result_raw)
    assert result["status"] == "logged"
    assert result["violations"] == []
    mock_store.assert_called_once()


# ---------------------------------------------------------------------------
# Smoke test: CONTROLLED_USE_CONFIG has expected keys
# ---------------------------------------------------------------------------


def test_config_structure() -> None:
    assert "bcd" in CONTROLLED_USE_CONFIG
    bcd = CONTROLLED_USE_CONFIG["bcd"]
    assert bcd["daily_ceiling"] == 4
    assert bcd["cooldown_hours"] == 2
