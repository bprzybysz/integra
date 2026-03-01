"""Tests for integra.data.quota — quota decay state computation."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from integra.core.config import Settings
from integra.data.quota import SUBSTANCE_QUOTAS, get_quota_state


def _make_config() -> Settings:
    return Settings(
        age_recipient="age1fake",
        age_identity="AGE-SECRET-KEY-1FAKE",
        data_lake_path=__import__("pathlib").Path("/tmp/test_quota_lake"),
        data_audit_path=__import__("pathlib").Path("/tmp/test_quota_audit"),
        data_raw_path=__import__("pathlib").Path("/tmp/test_quota_raw"),
    )


def _make_record(
    substance: str,
    amount: str,
    timestamp: str,
) -> dict[str, object]:
    return {
        "substance": substance,
        "amount": amount,
        "unit": "g",
        "timestamp": timestamp,
        "category": "addiction-therapy",
        "notes": "",
    }


# ── 1. Under quota ──────────────────────────────────────────────────────────


async def test_under_quota_status_and_no_flags() -> None:
    """Under quota: status=under, coaching_flag=False, penance_triggered=False."""
    # thc quota_week_0=14.0; 3 units used this week → under
    ref = date(2026, 3, 2)  # Monday ISO week 10
    week_start_iso = "2026-03-02T10:00:00+00:00"
    records = [_make_record("thc", "3", week_start_iso)]

    with patch(
        "integra.data.quota.query_data",
        new=AsyncMock(return_value=json.dumps(records)),
    ):
        state = await get_quota_state("thc", _make_config(), reference_date=ref)

    assert state is not None
    assert state["status"] == "under"
    assert state["coaching_flag"] is False
    assert state["penance_triggered"] is False
    assert state["units_used"] == pytest.approx(3.0)
    assert state["week_n"] == 0
    assert state["current_quota"] == pytest.approx(14.0)


# ── 2. Over quota ────────────────────────────────────────────────────────────


async def test_over_quota_coaching_flag() -> None:
    """Over quota: status=over, coaching_flag=True."""
    # k quota_week_0=5.0; 7 units used → over
    ref = date(2026, 3, 2)
    week_start_iso = "2026-03-02T10:00:00+00:00"
    records = [_make_record("k", "7", week_start_iso)]

    with patch(
        "integra.data.quota.query_data",
        new=AsyncMock(return_value=json.dumps(records)),
    ):
        state = await get_quota_state("k", _make_config(), reference_date=ref)

    assert state is not None
    assert state["status"] == "over"
    assert state["coaching_flag"] is True
    assert state["penance_triggered"] is False
    assert state["units_used"] == pytest.approx(7.0)


# ── 3. Zero quota + use → penance_triggered ──────────────────────────────────


async def test_zero_quota_penance_triggered() -> None:
    """Zero-quota substance with use → status=zero_relapse, penance_triggered=True."""
    # Simulate x with quota_week_0=2.0, decay_factor=0.80
    # After enough weeks the quota rounds to 0 — we patch SUBSTANCE_QUOTAS to force it
    ref = date(2026, 3, 2)
    week_start_iso = "2026-03-02T10:00:00+00:00"
    # Earliest record 50 weeks ago to drive quota to ~0
    earliest_iso = "2025-03-03T10:00:00+00:00"
    records = [
        _make_record("x", "0", earliest_iso),  # anchor to set week_n high
        _make_record("x", "1", week_start_iso),  # current week use
    ]

    # Patch SUBSTANCE_QUOTAS so current_quota evaluates to 0 for test control
    patched_quotas = {
        **SUBSTANCE_QUOTAS,
        "x": {"quota_week_0": 0.0, "decay_factor": 0.80},
    }
    with (
        patch("integra.data.quota.SUBSTANCE_QUOTAS", patched_quotas),
        patch(
            "integra.data.quota.query_data",
            new=AsyncMock(return_value=json.dumps(records)),
        ),
    ):
        state = await get_quota_state("x", _make_config(), reference_date=ref)

    assert state is not None
    assert state["status"] == "zero_relapse"
    assert state["penance_triggered"] is True
    assert state["units_used"] == pytest.approx(1.0)


# ── 4. Unknown substance → None ──────────────────────────────────────────────


async def test_unknown_substance_returns_none() -> None:
    """Unknown substance not in SUBSTANCE_QUOTAS returns None."""
    with patch(
        "integra.data.quota.query_data",
        new=AsyncMock(return_value=json.dumps([])),
    ):
        state = await get_quota_state("heroin", _make_config())

    assert state is None


# ── 5. No records yet ────────────────────────────────────────────────────────


async def test_no_records_returns_zero_week_and_under() -> None:
    """No records for substance: week_n=0, units_used=0.0, status=under."""
    ref = date(2026, 3, 2)

    with patch(
        "integra.data.quota.query_data",
        new=AsyncMock(return_value=json.dumps([])),
    ):
        state = await get_quota_state("3-cmc", _make_config(), reference_date=ref)

    assert state is not None
    assert state["week_n"] == 0
    assert state["units_used"] == pytest.approx(0.0)
    assert state["status"] == "under"
    assert state["coaching_flag"] is False
    assert state["penance_triggered"] is False
    assert state["current_quota"] == pytest.approx(SUBSTANCE_QUOTAS["3-cmc"]["quota_week_0"])
