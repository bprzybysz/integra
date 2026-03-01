"""Quota decay computation for addiction-therapy substances."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from integra.core.config import Settings
from integra.data.mcp_server import query_data
from integra.data.schemas import QuotaState

logger = logging.getLogger(__name__)

SUBSTANCE_QUOTAS: dict[str, dict[str, float]] = {
    "3-cmc": {"quota_week_0": 10.0, "decay_factor": 0.85},
    "k": {"quota_week_0": 5.0, "decay_factor": 0.85},
    "x": {"quota_week_0": 2.0, "decay_factor": 0.80},
    "thc": {"quota_week_0": 14.0, "decay_factor": 0.90},
}


def _iso_week_start(d: date) -> date:
    """Return the Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


def _parse_timestamp(ts: str) -> datetime | None:
    """Parse an ISO 8601 timestamp string; return None on failure."""
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


async def get_quota_state(
    substance: str,
    config: Settings,
    reference_date: date | None = None,
) -> QuotaState | None:
    """Compute current quota state for a substance from lake records.

    Returns None if substance not in SUBSTANCE_QUOTAS.
    week_n = ISO weeks since earliest record for this substance.
    units_used = sum of AddictionTherapyRecord.amount for current ISO week.
    """
    substance_lower = substance.lower()
    if substance_lower not in SUBSTANCE_QUOTAS:
        return None

    params = SUBSTANCE_QUOTAS[substance_lower]
    quota_week_0 = params["quota_week_0"]
    decay_factor = params["decay_factor"]

    ref_date: date = reference_date or datetime.now(tz=UTC).date()
    current_week_start = _iso_week_start(ref_date)

    raw_json = await query_data(category="intake", config=config)
    try:
        all_records: list[dict[str, Any]] = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        all_records = []

    # Filter by substance (case-insensitive)
    substance_records: list[dict[str, Any]] = [
        r for r in all_records if isinstance(r.get("substance"), str) and r["substance"].lower() == substance_lower
    ]

    # Determine week_n from earliest record
    week_n = 0
    if substance_records:
        timestamps = [
            _parse_timestamp(r["timestamp"]) for r in substance_records if isinstance(r.get("timestamp"), str)
        ]
        valid_dates = [dt.date() for dt in timestamps if dt is not None]
        if valid_dates:
            earliest = min(valid_dates)
            earliest_week_start = _iso_week_start(earliest)
            delta_days = (current_week_start - earliest_week_start).days
            week_n = max(0, delta_days // 7)

    current_quota = quota_week_0 * (decay_factor**week_n)

    # Sum units_used for current ISO week
    units_used = 0.0
    for record in substance_records:
        ts = _parse_timestamp(record.get("timestamp", ""))
        if ts is None:
            continue
        record_week_start = _iso_week_start(ts.date())
        if record_week_start != current_week_start:
            continue
        try:
            units_used += float(record.get("amount", 0))
        except (ValueError, TypeError):
            logger.warning("Non-numeric amount in record: %s", record.get("amount"))

    # Determine status and flags
    coaching_flag = False
    penance_triggered = False

    if current_quota <= 0 and units_used > 0:
        status = "zero_relapse"
        penance_triggered = True
    elif units_used > current_quota:
        status = "over"
        coaching_flag = True
    elif units_used == current_quota:
        status = "at"
    else:
        status = "under"

    return QuotaState(
        substance=substance_lower,
        week_n=week_n,
        quota_week_0=quota_week_0,
        decay_factor=decay_factor,
        current_quota=current_quota,
        units_used=units_used,
        status=status,
        coaching_flag=coaching_flag,
        penance_triggered=penance_triggered,
    )
