"""Tests for data ingestion and MCP query handlers."""

from __future__ import annotations

import json
from pathlib import Path

import pyrage.x25519
import pytest

from integra.core.config import Settings
from integra.data.encryption import decrypt_record, encrypt_record
from integra.data.ingestion import ingest_from_landing_zone
from integra.data.mcp_server import ingest_data, query_data


@pytest.fixture
def age_keypair() -> tuple[str, str]:
    identity = pyrage.x25519.Identity.generate()
    recipient = identity.to_public()
    return str(recipient), str(identity)


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


class TestEncryptDecryptRoundtrip:
    def test_roundtrip(self, age_keypair: tuple[str, str]) -> None:
        pub, priv = age_keypair
        record = {"key": "value", "num": 123}
        ct = encrypt_record(record, pub)
        assert decrypt_record(ct, priv) == record


class TestIngestion:
    async def test_ingest_json_files(self, test_config: Settings) -> None:
        raw = test_config.data_raw_path / "health"
        raw.mkdir(parents=True)
        (raw / "bp.json").write_text(json.dumps({"systolic": 120, "diastolic": 80}))

        result = await ingest_from_landing_zone(test_config)

        assert result.files_processed == 1
        assert result.records_ingested == 1
        assert result.errors == []
        assert not (raw / "bp.json").exists()  # raw file deleted
        lake_files = list((test_config.data_lake_path / "health").glob("*.age"))
        assert len(lake_files) == 1

    async def test_ingest_json_array(self, test_config: Settings) -> None:
        raw = test_config.data_raw_path / "meds"
        raw.mkdir(parents=True)
        records = [{"name": "aspirin"}, {"name": "ibuprofen"}]
        (raw / "meds.json").write_text(json.dumps(records))

        result = await ingest_from_landing_zone(test_config)

        assert result.files_processed == 1
        assert result.records_ingested == 2

    async def test_ingest_empty_landing_zone(self, test_config: Settings) -> None:
        test_config.data_raw_path.mkdir(parents=True)
        result = await ingest_from_landing_zone(test_config)
        assert result.files_processed == 0
        assert result.records_ingested == 0
        assert result.errors == []

    async def test_ingest_nonexistent_landing_zone(self, test_config: Settings) -> None:
        result = await ingest_from_landing_zone(test_config)
        assert result.files_processed == 0

    async def test_ingest_csv(self, test_config: Settings) -> None:
        raw = test_config.data_raw_path / "vitals"
        raw.mkdir(parents=True)
        (raw / "data.csv").write_text("hr,bp\n72,120/80\n65,110/70\n")

        result = await ingest_from_landing_zone(test_config)
        assert result.files_processed == 1
        assert result.records_ingested == 2


class TestIngestDataHandler:
    async def test_ingest_returns_json_status(self, test_config: Settings) -> None:
        test_config.data_raw_path.mkdir(parents=True)
        raw_str = await ingest_data(config=test_config)
        data = json.loads(raw_str)
        assert data["files_processed"] == 0
        assert data["records_ingested"] == 0


class TestQueryData:
    async def test_query_existing_category(self, test_config: Settings) -> None:
        # Pre-populate lake with encrypted data
        lake_dir = test_config.data_lake_path / "health"
        lake_dir.mkdir(parents=True)
        record = {"systolic": 120, "diastolic": 80}
        ct = encrypt_record(record, test_config.age_recipient)
        (lake_dir / "20260101T000000_bp_0.age").write_bytes(ct)

        raw = await query_data("health", config=test_config)
        results = json.loads(raw)
        assert len(results) == 1
        assert results[0]["systolic"] == 120

    async def test_query_with_filters(self, test_config: Settings) -> None:
        lake_dir = test_config.data_lake_path / "meds"
        lake_dir.mkdir(parents=True)
        for i, rec in enumerate([{"name": "aspirin"}, {"name": "ibuprofen"}]):
            ct = encrypt_record(rec, test_config.age_recipient)
            (lake_dir / f"20260101T000000_m_{i}.age").write_bytes(ct)

        raw = await query_data("meds", filters={"name": "aspirin"}, config=test_config)
        results = json.loads(raw)
        assert len(results) == 1
        assert results[0]["name"] == "aspirin"

    async def test_query_nonexistent_category(self, test_config: Settings) -> None:
        raw = await query_data("nonexistent", config=test_config)
        assert json.loads(raw) == []

    async def test_query_audited(self, test_config: Settings) -> None:
        await query_data("anything", config=test_config)
        audit_file = test_config.data_audit_path / "query.jsonl"
        assert audit_file.exists()
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["action"] == "query"
