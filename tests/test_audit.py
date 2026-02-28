"""Tests for integra.data.audit — audit log helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from integra.data.audit import write_audit_entry


class TestWriteAuditEntry:
    def test_creates_file_and_writes_entry(self, tmp_path: Path) -> None:
        audit_file = tmp_path / "audit" / "test.jsonl"
        write_audit_entry(audit_file, {"action": "test", "count": 1})
        assert audit_file.exists()
        entry = json.loads(audit_file.read_text().strip())
        assert entry["action"] == "test"
        assert entry["count"] == 1

    def test_appends_multiple_entries(self, tmp_path: Path) -> None:
        audit_file = tmp_path / "log.jsonl"
        write_audit_entry(audit_file, {"n": 1})
        write_audit_entry(audit_file, {"n": 2})
        write_audit_entry(audit_file, {"n": 3})
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[2])["n"] == 3

    def test_handles_datetime_serialization(self, tmp_path: Path) -> None:
        audit_file = tmp_path / "dt.jsonl"
        now = datetime.now(UTC)
        write_audit_entry(audit_file, {"ts": now})
        entry = json.loads(audit_file.read_text().strip())
        assert str(now) in entry["ts"]

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        audit_file = tmp_path / "deep" / "nested" / "dir" / "audit.jsonl"
        write_audit_entry(audit_file, {"ok": True})
        assert audit_file.exists()
