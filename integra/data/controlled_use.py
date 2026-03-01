"""Rules engine for controlled-use substances (BCD)."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timedelta
from typing import TypedDict
from zoneinfo import ZoneInfo

from integra.data.schemas import ControlledUseRecord, make_controlled_use_record

logger = logging.getLogger(__name__)


class _SubstanceCfg(TypedDict):
    daily_ceiling: int
    work_hours_start: int
    work_hours_end: int
    cooldown_hours: int
    ruliade: str


CONTROLLED_USE_CONFIG: dict[str, _SubstanceCfg] = {
    "bcd": {
        "daily_ceiling": 4,  # units per day
        "work_hours_start": 9,  # 09:00 local time
        "work_hours_end": 17,  # 17:00 local time
        "cooldown_hours": 2,  # minimum hours between uses
        "ruliade": ("not during work hours (09-17 CET), 2h cooldown between uses, skip if HALT score > 3"),
    }
}


def _is_work_hours(
    ts: datetime,
    tz: ZoneInfo,
    work_start: int,
    work_end: int,
) -> bool:
    """Return True if ts falls within work hours in the given timezone."""
    local_ts = ts.astimezone(tz)
    return work_start <= local_ts.hour < work_end


def _cooldown_violated(
    ts: datetime,
    recent_records: list[ControlledUseRecord],
    cooldown_hours: int,
) -> bool:
    """Return True if any recent record is within the cooldown window."""
    cutoff = ts - timedelta(hours=cooldown_hours)
    for record in recent_records:
        try:
            rec_ts = datetime.fromisoformat(record["timestamp"])
        except (ValueError, KeyError):
            continue
        if rec_ts >= cutoff:
            return True
    return False


def _today_total(
    ts: datetime,
    tz: ZoneInfo,
    recent_records: list[ControlledUseRecord],
) -> float:
    """Sum today's numeric amounts from recent_records (same local date as ts)."""
    local_date = ts.astimezone(tz).date()
    total = 0.0
    for record in recent_records:
        try:
            rec_ts = datetime.fromisoformat(record["timestamp"])
        except (ValueError, KeyError):
            continue
        if rec_ts.astimezone(tz).date() == local_date:
            with contextlib.suppress(ValueError, TypeError):
                total += float(record["amount"])
    return total


def evaluate_controlled_use(
    substance: str,
    amount: str,
    unit: str,
    timestamp: datetime,
    recent_records: list[ControlledUseRecord],
    timezone_str: str = "Europe/Warsaw",
) -> tuple[ControlledUseRecord, bool, str | None]:
    """Evaluate a controlled-use intake event against all rules.

    Returns: (record, coaching_needed, coaching_message | None)
    - work_hours_violation: timestamp falls in work hours in user's timezone
    - cooldown_violation: last record < cooldown_hours ago
    - daily_ceiling_exceeded: sum(today's amounts) > daily_ceiling
    coaching_needed=True if any violation.
    """
    key = substance.lower()
    cfg = CONTROLLED_USE_CONFIG.get(key)

    if cfg is None:
        # Unknown substance — store plain record with no violations
        record = make_controlled_use_record(
            substance=substance,
            amount=amount,
            unit=unit,
        )
        return record, False, None

    tz = ZoneInfo(timezone_str)
    work_start: int = cfg["work_hours_start"]
    work_end: int = cfg["work_hours_end"]
    cooldown_hours: int = cfg["cooldown_hours"]
    daily_ceiling: int = cfg["daily_ceiling"]
    ruliade: str = cfg["ruliade"]

    work_hours_violation = _is_work_hours(timestamp, tz, work_start, work_end)
    cooldown_violation = _cooldown_violated(timestamp, recent_records, cooldown_hours)

    # Ceiling check: today's existing total + new amount
    today_total = _today_total(timestamp, tz, recent_records)
    try:
        new_amount = float(amount)
    except ValueError:
        new_amount = 0.0
    daily_ceiling_exceeded = (today_total + new_amount) > daily_ceiling

    record = make_controlled_use_record(
        substance=substance,
        amount=amount,
        unit=unit,
        work_hours_violation=work_hours_violation,
        cooldown_violation=cooldown_violation,
        daily_ceiling_exceeded=daily_ceiling_exceeded,
        ruliade=ruliade,
        timestamp=timestamp.isoformat(),
    )

    coaching_needed = work_hours_violation or cooldown_violation or daily_ceiling_exceeded

    coaching_message: str | None = None
    if coaching_needed:
        violations: list[str] = []
        if work_hours_violation:
            violations.append(f"work hours ({work_start:02d}:00-{work_end:02d}:00)")
        if cooldown_violation:
            violations.append(f"cooldown ({cooldown_hours}h not elapsed)")
        if daily_ceiling_exceeded:
            violations.append(f"daily ceiling ({daily_ceiling} units)")
        coaching_message = (
            f"Controlled-use rule violation for {substance}: " + ", ".join(violations) + f". Rules: {ruliade}"
        )

    return record, coaching_needed, coaching_message
