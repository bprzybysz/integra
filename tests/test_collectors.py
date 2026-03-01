"""Tests for integra.data.collectors — supplement, intake, meal, query handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pyrage
import pytest

from integra.core.config import Settings
from integra.data.collectors import (
    collect_supplement_stack,
    log_drug_intake,
    log_meal,
    query_health_data,
)
from integra.data.encryption import decrypt_record
from integra.data.schemas import SubstanceCategory


def _make_config(tmp_path: Path) -> Settings:
    identity = pyrage.x25519.Identity.generate()
    return Settings(
        age_recipient=str(identity.to_public()),
        age_identity=str(identity),
        data_lake_path=tmp_path / "lake",
        data_audit_path=tmp_path / "audit",
        data_raw_path=tmp_path / "raw",
    )


@pytest.fixture
def dummy_age_key() -> tuple[str, str]:
    identity = pyrage.x25519.Identity.generate()
    return str(identity.to_public()), str(identity)


# ── collect_supplement_stack ─────────────────────────────────────


class TestCollectSupplementStack:
    async def test_stores_encrypted_record(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await collect_supplement_stack(name="Vitamin D", dose="5000", unit="IU", config=cfg))
        assert result["status"] == "stored"
        lake = cfg.data_lake_path / "supplements"
        files = list(lake.glob("*.age"))
        assert len(files) == 1
        record = decrypt_record(files[0].read_bytes(), cfg.age_identity)
        assert record["name"] == "Vitamin D"
        assert record["dose"] == "5000"

    async def test_missing_name_returns_error(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await collect_supplement_stack(dose="100", config=cfg))
        assert "error" in result

    async def test_missing_dose_returns_error(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await collect_supplement_stack(name="Zinc", config=cfg))
        assert "error" in result

    async def test_writes_audit_entry(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        await collect_supplement_stack(name="Magnesium", dose="400", unit="mg", config=cfg)
        audit_file = cfg.data_audit_path / "ingest.jsonl"
        assert audit_file.exists()
        entry = json.loads(audit_file.read_text().strip())
        assert entry["action"] == "collect"
        assert entry["category"] == "supplements"


# ── _store_record collision handling ─────────────────────────────


class TestStoreRecordCollision:
    async def test_increments_index_on_collision(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        await collect_supplement_stack(name="A", dose="1", unit="mg", config=cfg)
        await collect_supplement_stack(name="B", dose="2", unit="mg", config=cfg)
        files = sorted((cfg.data_lake_path / "supplements").glob("*.age"))
        assert len(files) == 2
        names = {f.stem.split("_")[-1] for f in files}
        assert "0" in names
        assert "1" in names


# ── log_drug_intake ──────────────────────────────────────────────


class TestLogDrugIntake:
    async def test_logs_normal_intake(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await log_drug_intake(substance="Caffeine", amount="200", unit="mg", config=cfg))
        assert result["status"] == "logged"
        files = list((cfg.data_lake_path / "intake").glob("*.age"))
        assert len(files) == 1

    async def test_logs_addiction_therapy(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(
            await log_drug_intake(
                substance="Nicotine",
                amount="3",
                unit="pouches",
                category=SubstanceCategory.ADDICTION_THERAPY,
                daily_quota="6",
                config=cfg,
            )
        )
        assert result["status"] == "logged"
        files = list((cfg.data_lake_path / "intake").glob("*.age"))
        record = decrypt_record(files[0].read_bytes(), cfg.age_identity)
        assert record["daily_quota"] == "6"

    async def test_missing_substance_returns_error(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await log_drug_intake(amount="10", config=cfg))
        assert "error" in result

    async def test_missing_amount_returns_error(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await log_drug_intake(substance="Caffeine", config=cfg))
        assert "error" in result


# ── log_meal ─────────────────────────────────────────────────────


class TestLogMeal:
    async def test_logs_meal(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await log_meal(meal_type="lunch", items="chicken, rice", config=cfg))
        assert result["status"] == "logged"
        files = list((cfg.data_lake_path / "dietary").glob("*.age"))
        assert len(files) == 1

    async def test_missing_meal_type_returns_error(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await log_meal(items="salad", config=cfg))
        assert "error" in result

    async def test_missing_items_returns_error(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        result = json.loads(await log_meal(meal_type="dinner", config=cfg))
        assert "error" in result


# ── query_health_data ────────────────────────────────────────────


class TestQueryHealthData:
    async def test_delegates_to_mcp_query(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        with patch(
            "integra.data.mcp_server.query_data",
            new_callable=AsyncMock,
            return_value="[]",
        ) as mock_query:
            result = await query_health_data(category="supplements", config=cfg)
            mock_query.assert_called_once()
            assert result == "[]"

    async def test_passes_filters(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        with patch(
            "integra.data.mcp_server.query_data",
            new_callable=AsyncMock,
            return_value="[]",
        ) as mock_query:
            await query_health_data(
                category="intake",
                filters={"substance": "Caffeine"},
                config=cfg,
            )
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["filters"] == {"substance": "Caffeine"}

    async def test_non_dict_filters_ignored(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        with patch(
            "integra.data.mcp_server.query_data",
            new_callable=AsyncMock,
            return_value="[]",
        ) as mock_query:
            await query_health_data(category="intake", filters="bad", config=cfg)
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["filters"] is None


# ---------------------------------------------------------------------------
# IncomingRequest tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_request_happy_path(tmp_path: Path, dummy_age_key: tuple[str, str]) -> None:
    from integra.data.collectors import store_request

    recipient, _ = dummy_age_key
    cfg = Settings(
        age_recipient=recipient,
        data_lake_path=tmp_path / "lake",
        data_audit_path=tmp_path / "audit",
    )
    result_json = await store_request(
        config=cfg,
        sender_id=12345,
        sender_name="Mom",
        text="buy milk please",
    )
    result = json.loads(result_json)
    assert result["status"] == "stored"
    assert "request_id" in result
    assert (tmp_path / "lake" / "requests").exists()


@pytest.mark.asyncio
async def test_store_request_missing_text(tmp_path: Path, dummy_age_key: tuple[str, str]) -> None:
    from integra.data.collectors import store_request

    recipient, _ = dummy_age_key
    cfg = Settings(
        age_recipient=recipient,
        data_lake_path=tmp_path / "lake",
        data_audit_path=tmp_path / "audit",
    )
    result_json = await store_request(config=cfg, sender_id=1, sender_name="X", text="")
    result = json.loads(result_json)
    assert "error" in result


@pytest.mark.asyncio
async def test_upsert_request(tmp_path: Path, dummy_age_key: tuple[str, str]) -> None:
    from integra.data.collectors import upsert_request

    recipient, _ = dummy_age_key
    cfg = Settings(
        age_recipient=recipient,
        data_lake_path=tmp_path / "lake",
        data_audit_path=tmp_path / "audit",
    )
    result_json = await upsert_request(config=cfg, request_id="12345_999", status="acknowledged")
    result = json.loads(result_json)
    assert result["status"] == "updated"
    assert result["new_status"] == "acknowledged"


@pytest.mark.asyncio
async def test_delete_request(tmp_path: Path, dummy_age_key: tuple[str, str]) -> None:
    from integra.data.collectors import delete_request

    recipient, _ = dummy_age_key
    cfg = Settings(
        age_recipient=recipient,
        data_lake_path=tmp_path / "lake",
        data_audit_path=tmp_path / "audit",
    )
    result_json = await delete_request(config=cfg, request_id="12345_999")
    result = json.loads(result_json)
    assert result["status"] == "deleted"
