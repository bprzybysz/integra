"""Data ingestion pipeline: raw/ -> encrypt -> lake/ -> audit -> delete raw."""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from integra.core.config import Settings
from integra.data.audit import write_audit_entry
from integra.data.encryption import encrypt_record

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB per file


@dataclass
class IngestResult:
    """Summary of an ingestion run."""

    files_processed: int = 0
    records_ingested: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_json_file(path: Path) -> list[dict[str, Any]]:
    """Parse a JSON file, returning a list of records."""
    with path.open("r", encoding="utf-8") as f:
        data: Any = json.load(f)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    msg = f"Unsupported JSON structure in {path}"
    raise ValueError(msg)


def _parse_csv_file(path: Path) -> list[dict[str, Any]]:
    """Parse a CSV file, returning a list of dicts (one per row)."""
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


DataParser = Callable[[Path], list[dict[str, Any]]]

_PARSERS: dict[str, DataParser] = {
    ".json": _parse_json_file,
    ".csv": _parse_csv_file,
}


def register_parser(suffix: str, parser: DataParser) -> None:
    """Register a new file parser for a given suffix."""
    _PARSERS[suffix.lower()] = parser


def _parse_file(path: Path) -> list[dict[str, Any]]:
    """Dispatch to the right parser based on suffix."""
    suffix = path.suffix.lower()
    parser = _PARSERS.get(suffix)
    if parser is None:
        msg = f"Unsupported file type: {suffix}"
        raise ValueError(msg)
    return parser(path)


def _determine_category(file_path: Path, raw_root: Path) -> str:
    """Category is the immediate parent directory name relative to raw_root."""
    try:
        rel = file_path.parent.relative_to(raw_root)
        parts = rel.parts
        if parts:
            return parts[0]
    except ValueError:
        pass
    return "uncategorized"


async def ingest_from_landing_zone(config: Settings) -> IngestResult:
    """Scan data/raw/, encrypt each record, store in data/lake/, audit, delete raw."""
    result = IngestResult()
    raw_root = config.data_raw_path
    lake_root = config.data_lake_path
    audit_file = config.data_audit_path / "ingest.jsonl"

    if not raw_root.exists():
        logger.info("Landing zone %s does not exist; nothing to ingest.", raw_root)
        return result

    files = [p for p in raw_root.rglob("*") if p.is_file()]
    if not files:
        logger.info("Landing zone is empty.")
        return result

    for file_path in files:
        try:
            # Security: enforce file size limit before parsing
            file_size = file_path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                error_msg = f"File too large ({file_size} bytes, max {MAX_FILE_SIZE}): {file_path}"
                logger.warning(error_msg)
                result.errors.append(error_msg)
                continue

            records = _parse_file(file_path)
            category = _determine_category(file_path, raw_root)
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

            for i, record in enumerate(records):
                encrypted = encrypt_record(record, config.age_recipient)
                dest_dir = lake_root / category
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_name = f"{ts}_{file_path.stem}_{i}.age"
                dest_file = dest_dir / dest_name
                dest_file.write_bytes(encrypted)
                result.records_ingested += 1

            write_audit_entry(
                audit_file,
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "action": "ingest",
                    "file": str(file_path),
                    "category": category,
                    "records": len(records),
                },
            )

            file_path.unlink()
            result.files_processed += 1
            logger.info("Ingested %s (%d records) -> %s", file_path.name, len(records), category)

        except Exception as exc:
            error_msg = f"Error processing {file_path}: {exc}"
            logger.error(error_msg)
            result.errors.append(error_msg)

    return result
