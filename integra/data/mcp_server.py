"""MCP data gateway: ingest and query tool handlers."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from integra.core.config import Settings, settings
from integra.data.audit import write_audit_entry
from integra.data.encryption import decrypt_record
from integra.data.ingestion import ingest_from_landing_zone

logger = logging.getLogger(__name__)


def _matches_filters(record: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Check if a record matches all filter key-value pairs."""
    return all(record.get(k) == v for k, v in filters.items())


async def ingest_data(config: Settings | None = None, **kwargs: Any) -> str:
    """Trigger ingestion pipeline, return JSON status."""
    cfg = config or settings
    result = await ingest_from_landing_zone(cfg)
    return json.dumps(
        {
            "files_processed": result.files_processed,
            "records_ingested": result.records_ingested,
            "errors": result.errors,
        }
    )


async def query_data(
    category: str,
    filters: dict[str, Any] | None = None,
    config: Settings | None = None,
    **kwargs: Any,
) -> str:
    """Decrypt and query lake files in a category. Returns JSON array of matching records."""
    cfg = config or settings
    lake_dir = cfg.data_lake_path / category
    audit_file = cfg.data_audit_path / "query.jsonl"

    write_audit_entry(
        audit_file,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "query",
            "category": category,
            "filters": filters,
        },
    )

    if not lake_dir.exists():
        return json.dumps([])

    results: list[dict[str, Any]] = []
    for age_file in sorted(lake_dir.glob("*.age")):
        try:
            ciphertext = age_file.read_bytes()
            record = decrypt_record(ciphertext, cfg.age_identity)
            if filters and not _matches_filters(record, filters):
                continue
            results.append(record)
        except Exception as exc:
            logger.error("Failed to decrypt %s: %s", age_file, exc)

    return json.dumps(results, default=str)
