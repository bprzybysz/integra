"""Tests for integra.data.cc_history."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pyrage
import pyrage.x25519
import pytest

from integra.core.config import Settings
from integra.data.cc_history import (
    _extract_from_archive,
    _extract_prompts_from_jsonl,
    analyze_cc_productivity,
    ingest_cc_history,
)
from integra.data.encryption import encrypt_record


@pytest.fixture
def age_keypair() -> tuple[str, str]:
    identity = pyrage.x25519.Identity.generate()
    return str(identity.to_public()), str(identity)


@pytest.fixture
def test_config(tmp_path: Path, age_keypair: tuple[str, str]) -> Settings:
    pub, priv = age_keypair
    return Settings(
        age_recipient=pub,
        age_identity=priv,
        data_raw_path=tmp_path / "raw",
        data_lake_path=tmp_path / "lake",
        data_audit_path=tmp_path / "audit",
    )


class TestExtractPromptsFromJsonl:
    def test_parses_valid_jsonl(self) -> None:
        content = '{"role": "user", "text": "hello"}\n{"role": "assistant", "text": "hi"}\n'
        records = _extract_prompts_from_jsonl(content)
        assert len(records) == 2
        assert records[0]["role"] == "user"

    def test_skips_invalid_lines(self) -> None:
        content = '{"valid": true}\nnot json\n{"also": "valid"}\n'
        records = _extract_prompts_from_jsonl(content)
        assert len(records) == 2

    def test_empty_content(self) -> None:
        assert _extract_prompts_from_jsonl("") == []


class TestExtractFromArchive:
    def test_extracts_jsonl_from_zip(self, tmp_path: Path) -> None:
        archive = tmp_path / "test.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("sessions.jsonl", '{"timestamp": "2026-01-01T10:00:00"}\n')
        records = _extract_from_archive(archive)
        assert len(records) == 1
        assert records[0]["timestamp"] == "2026-01-01T10:00:00"

    def test_extracts_json_from_zip(self, tmp_path: Path) -> None:
        archive = tmp_path / "test.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("data.json", json.dumps([{"a": 1}, {"b": 2}]))
        records = _extract_from_archive(archive)
        assert len(records) == 2


class TestIngestCcHistory:
    async def test_ingests_archive(self, tmp_path: Path, test_config: Settings) -> None:
        archive = tmp_path / "cc.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("session.jsonl", '{"timestamp": "2026-01-01T10:00:00", "prompt": "test"}\n')

        result_json = await ingest_cc_history(str(archive), config=test_config)
        result = json.loads(result_json)
        assert result["records_ingested"] == 1
        assert result["files_processed"] == 1
        assert result["errors"] == []

        # Verify files in lake
        lake_dir = test_config.data_lake_path / "cc_history"
        assert len(list(lake_dir.glob("*.age"))) == 1

    async def test_missing_archive(self, test_config: Settings) -> None:
        result_json = await ingest_cc_history("/nonexistent/archive.zip", config=test_config)
        result = json.loads(result_json)
        assert "error" in result

    async def test_empty_archive(self, tmp_path: Path, test_config: Settings) -> None:
        archive = tmp_path / "empty.zip"
        with zipfile.ZipFile(archive, "w"):
            pass
        result_json = await ingest_cc_history(str(archive), config=test_config)
        result = json.loads(result_json)
        assert result["records_ingested"] == 0


class TestAnalyzeCcProductivity:
    async def test_empty_data(self, test_config: Settings) -> None:
        result_json = await analyze_cc_productivity(config=test_config)
        result = json.loads(result_json)
        assert result["total_sessions"] == 0
        assert result["total_intake_events"] == 0

    async def test_with_data(self, test_config: Settings) -> None:
        # Populate lake with test data
        cc_dir = test_config.data_lake_path / "cc_history"
        cc_dir.mkdir(parents=True)
        intake_dir = test_config.data_lake_path / "intake"
        intake_dir.mkdir(parents=True)

        cc_record = {"timestamp": "2026-01-01T10:00:00", "prompt": "test"}
        encrypted = encrypt_record(cc_record, test_config.age_recipient)
        (cc_dir / "test_0.age").write_bytes(encrypted)

        intake_record = {"substance": "caffeine", "amount": "200", "unit": "mg", "timestamp": "2026-01-01T09:00:00"}
        encrypted2 = encrypt_record(intake_record, test_config.age_recipient)
        (intake_dir / "test_0.age").write_bytes(encrypted2)

        result_json = await analyze_cc_productivity(config=test_config)
        result = json.loads(result_json)
        assert result["total_sessions"] == 1
        assert result["total_intake_events"] == 1
        assert result["substances_summary"]["caffeine"] == 1
