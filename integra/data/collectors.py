"""Tool handlers for health data collection via questionnaire + ingestion."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from integra.core.config import Settings, settings
from integra.data.audit import write_audit_entry
from integra.data.encryption import encrypt_record
from integra.data.schemas import (
    DiaryType,
    SubstanceCategory,
    make_addiction_therapy_record,
    make_diary_record,
    make_dietary_record,
    make_intake_record,
    make_supplement_record,
)

logger = logging.getLogger(__name__)


def _store_record(record: dict[str, Any], category: str, config: Settings) -> None:
    """Encrypt and store a single record in the data lake."""
    encrypted = encrypt_record(record, config.age_recipient)
    dest_dir = config.data_lake_path / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    dest_file = dest_dir / f"{ts}_{category}_0.age"
    # Avoid collisions by incrementing index
    idx = 0
    while dest_file.exists():
        idx += 1
        dest_file = dest_dir / f"{ts}_{category}_{idx}.age"
    dest_file.write_bytes(encrypted)

    write_audit_entry(
        config.data_audit_path / "ingest.jsonl",
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "collect",
            "category": category,
            "records": 1,
        },
    )


async def collect_supplement_stack(**kwargs: Any) -> str:
    """Collect a supplement/medication entry and store in data lake.

    Accepts fields: name, dose, unit, frequency, time_of_day, category, notes.
    """
    cfg: Settings = kwargs.pop("config", None) or settings
    name = str(kwargs.get("name", ""))
    dose = str(kwargs.get("dose", ""))
    unit = str(kwargs.get("unit", ""))
    frequency = str(kwargs.get("frequency", "daily"))
    time_of_day = str(kwargs.get("time_of_day", "morning"))
    category = str(kwargs.get("category", SubstanceCategory.SUPPLEMENT))
    notes = str(kwargs.get("notes", ""))

    if not name or not dose:
        return json.dumps({"error": "name and dose are required"})

    record = make_supplement_record(
        name=name,
        dose=dose,
        unit=unit,
        frequency=frequency,
        time_of_day=time_of_day,
        category=category,
        notes=notes,
    )
    _store_record(dict(record), "supplements", cfg)
    logger.info("Stored supplement: %s %s%s", name, dose, unit)
    return json.dumps({"status": "stored", "name": name, "dose": dose, "unit": unit})


async def log_drug_intake(**kwargs: Any) -> str:
    """Log a single drug/substance intake event.

    Accepts: substance, amount, unit, category, notes, timestamp.
    """
    cfg: Settings = kwargs.pop("config", None) or settings
    substance = str(kwargs.get("substance", ""))
    amount = str(kwargs.get("amount", ""))
    unit = str(kwargs.get("unit", ""))
    category = str(kwargs.get("category", SubstanceCategory.SUPPLEMENT))
    notes = str(kwargs.get("notes", ""))
    timestamp = kwargs.get("timestamp")

    if not substance or not amount:
        return json.dumps({"error": "substance and amount are required"})

    # Use addiction-therapy record for those substances
    if category == SubstanceCategory.ADDICTION_THERAPY:
        daily_quota = str(kwargs.get("daily_quota", ""))
        record: dict[str, Any] = dict(
            make_addiction_therapy_record(
                substance=substance,
                amount=amount,
                unit=unit,
                daily_quota=daily_quota,
                notes=notes,
                timestamp=str(timestamp) if timestamp else None,
            )
        )
        _store_record(record, "intake", cfg)
    else:
        record = dict(
            make_intake_record(
                substance=substance,
                amount=amount,
                unit=unit,
                category=category,
                notes=notes,
                timestamp=str(timestamp) if timestamp else None,
            )
        )
        _store_record(record, "intake", cfg)

    logger.info("Logged intake: %s %s%s", substance, amount, unit)
    return json.dumps({"status": "logged", "substance": substance, "amount": amount})


async def log_meal(**kwargs: Any) -> str:
    """Log a dietary intake entry.

    Accepts: meal_type, items, notes, timestamp.
    """
    cfg: Settings = kwargs.pop("config", None) or settings
    meal_type = str(kwargs.get("meal_type", ""))
    items = str(kwargs.get("items", ""))
    notes = str(kwargs.get("notes", ""))
    timestamp = kwargs.get("timestamp")

    if not meal_type or not items:
        return json.dumps({"error": "meal_type and items are required"})

    record = dict(
        make_dietary_record(
            meal_type=meal_type,
            items=items,
            notes=notes,
            timestamp=str(timestamp) if timestamp else None,
        )
    )
    _store_record(record, "dietary", cfg)
    logger.info("Logged meal: %s", meal_type)
    return json.dumps({"status": "logged", "meal_type": meal_type})


async def collect_diary(**kwargs: Any) -> str:
    """Store an on-demand diary entry in the data lake."""
    cfg: Settings = kwargs.pop("config", None) or settings
    answers_raw = kwargs.get("answers", {})
    answers: dict[str, str] = {str(k): str(v) for k, v in answers_raw.items()} if isinstance(answers_raw, dict) else {}
    qa_pairs = [{"q": k, "a": v} for k, v in answers.items()]
    record = make_diary_record(
        diary_type=DiaryType.ON_DEMAND,
        severity="none",
        substance=str(answers.get("substance", "")),
        questions_asked=len(qa_pairs),
        answers=json.dumps(qa_pairs),
        penance_credit=0.0,
    )
    _store_record(dict(record), "diary", cfg)
    logger.info("Stored on-demand diary entry (%d Q&As)", len(qa_pairs))
    return json.dumps({"status": "stored", "questions_asked": len(qa_pairs)})


async def query_health_data(**kwargs: Any) -> str:
    """Query health data across categories with optional date filtering.

    Accepts: category (supplements|intake|dietary), filters, date_from, date_to.
    """
    from integra.data.mcp_server import query_data

    cfg: Settings = kwargs.pop("config", None) or settings
    category = str(kwargs.get("category", "supplements"))
    filters = kwargs.get("filters")
    if isinstance(filters, dict):
        pass
    else:
        filters = None

    return await query_data(category=category, filters=filters, config=cfg)
