"""Claude Code history ingestion and productivity analysis."""

from __future__ import annotations

import json
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from integra.core.config import Settings, settings
from integra.data.audit import write_audit_entry
from integra.data.encryption import encrypt_record
from integra.data.ingestion import IngestResult

logger = logging.getLogger(__name__)


def _extract_prompts_from_jsonl(content: str) -> list[dict[str, Any]]:
    """Extract prompt records from JSONL content (one JSON object per line)."""
    records: list[dict[str, Any]] = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj: Any = json.loads(line)
            if isinstance(obj, dict):
                records.append(obj)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON line in history")
    return records


MAX_ZIP_MEMBER_SIZE = 100 * 1024 * 1024  # 100 MB per member
MAX_ZIP_TOTAL_SIZE = 500 * 1024 * 1024  # 500 MB total extracted


def _is_safe_zip_path(member_name: str) -> bool:
    """Reject zip members with path traversal components."""
    from pathlib import PurePosixPath

    p = PurePosixPath(member_name)
    return ".." not in p.parts and not p.is_absolute()


def _extract_from_archive(archive_path: Path) -> list[dict[str, Any]]:
    """Extract prompt records from a zip archive containing JSONL/JSON files.

    Security: validates member paths against traversal and enforces size limits.
    """
    all_records: list[dict[str, Any]] = []
    total_extracted = 0

    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue

            # Security: reject path traversal
            if not _is_safe_zip_path(name):
                logger.warning("Skipping unsafe zip member path: %s", name)
                continue

            # Security: enforce per-member size limit
            if info.file_size > MAX_ZIP_MEMBER_SIZE:
                logger.warning("Skipping oversized zip member %s (%d bytes)", name, info.file_size)
                continue

            # Security: enforce total extracted size limit
            total_extracted += info.file_size
            if total_extracted > MAX_ZIP_TOTAL_SIZE:
                logger.warning("Total extracted size exceeds limit, stopping extraction")
                break

            try:
                content = zf.read(name).decode("utf-8", errors="replace")
                if name.endswith(".jsonl"):
                    all_records.extend(_extract_prompts_from_jsonl(content))
                elif name.endswith(".json"):
                    data: Any = json.loads(content)
                    if isinstance(data, list):
                        all_records.extend(r for r in data if isinstance(r, dict))
                    elif isinstance(data, dict):
                        all_records.append(data)
            except Exception as exc:
                logger.error("Error reading %s from archive: %s", name, exc)

    return all_records


async def ingest_cc_history(
    archive_path: str,
    config: Settings | None = None,
    **kwargs: Any,
) -> str:
    """Ingest Claude Code session history from a zip archive.

    Args:
        archive_path: Path to the zip archive.
        config: Optional settings override.

    Returns:
        JSON string with ingestion results.
    """
    cfg = config or settings
    path = Path(archive_path)

    if not path.exists():
        return json.dumps({"error": f"Archive not found: {archive_path}"})

    result = IngestResult()

    try:
        records = _extract_from_archive(path)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        dest_dir = cfg.data_lake_path / "cc_history"
        dest_dir.mkdir(parents=True, exist_ok=True)

        for i, record in enumerate(records):
            encrypted = encrypt_record(record, cfg.age_recipient)
            dest_file = dest_dir / f"{ts}_cc_session_{i}.age"
            dest_file.write_bytes(encrypted)
            result.records_ingested += 1

        result.files_processed = 1

        write_audit_entry(
            cfg.data_audit_path / "ingest.jsonl",
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "ingest_cc_history",
                "archive": str(path),
                "records": result.records_ingested,
            },
        )
        logger.info("Ingested %d CC history records from %s", result.records_ingested, path)

    except Exception as exc:
        error_msg = f"Error ingesting CC history: {exc}"
        logger.error(error_msg)
        result.errors.append(error_msg)

    return json.dumps(
        {
            "files_processed": result.files_processed,
            "records_ingested": result.records_ingested,
            "errors": result.errors,
        }
    )


async def analyze_cc_productivity(
    config: Settings | None = None,
    **kwargs: Any,
) -> str:
    """Cross-reference CC session data with drug intake for productivity analysis.

    Returns JSON with session counts, substance overlap windows, and basic metrics.
    """
    from integra.data.mcp_server import query_data

    cfg = config or settings

    # Load CC history records
    cc_raw = await query_data(category="cc_history", config=cfg)
    cc_records: list[dict[str, Any]] = json.loads(cc_raw)

    # Load intake records
    intake_raw = await query_data(category="intake", config=cfg)
    intake_records: list[dict[str, Any]] = json.loads(intake_raw)

    # Basic analysis: count sessions, unique dates, substance usage
    session_count = len(cc_records)
    cc_timestamps = [r.get("timestamp", "") for r in cc_records if r.get("timestamp")]
    unique_dates = len({t[:10] for t in cc_timestamps if len(t) >= 10})

    substances_used: dict[str, int] = {}
    for intake in intake_records:
        sub = intake.get("substance", "unknown")
        substances_used[sub] = substances_used.get(sub, 0) + 1

    analysis = {
        "total_sessions": session_count,
        "unique_dates": unique_dates,
        "total_intake_events": len(intake_records),
        "substances_summary": substances_used,
        "analysis_timestamp": datetime.now(UTC).isoformat(),
    }

    write_audit_entry(
        cfg.data_audit_path / "query.jsonl",
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "analyze_cc_productivity",
            "sessions": session_count,
            "intake_events": len(intake_records),
        },
    )

    return json.dumps(analysis, default=str)
