"""Tests for on-demand diary collection."""

from __future__ import annotations

import json
from pathlib import Path

import pyrage.x25519
import pytest

from integra.core.config import Settings
from integra.data.collectors import collect_diary


@pytest.fixture
def test_config(tmp_path: Path) -> Settings:
    identity = pyrage.x25519.Identity.generate()
    return Settings(
        age_recipient=str(identity.to_public()),
        age_identity=str(identity),
        data_raw_path=tmp_path / "raw",
        data_lake_path=tmp_path / "lake",
        data_audit_path=tmp_path / "audit",
    )


class TestCollectDiary:
    async def test_stores_on_demand_diary(self, test_config: Settings) -> None:
        test_config.data_audit_path.mkdir(parents=True, exist_ok=True)
        result = await collect_diary(
            answers={"content": "feeling good", "mood": "great", "substance": "none", "notes": ""},
            config=test_config,
        )
        data = json.loads(result)
        assert data["status"] == "stored"
        assert data["questions_asked"] == 4
        # Verify file was created in diary category
        diary_dir = test_config.data_lake_path / "diary"
        assert diary_dir.exists()
        assert len(list(diary_dir.iterdir())) == 1

    async def test_empty_answers(self, test_config: Settings) -> None:
        test_config.data_audit_path.mkdir(parents=True, exist_ok=True)
        result = await collect_diary(answers={}, config=test_config)
        data = json.loads(result)
        assert data["questions_asked"] == 0

    async def test_substance_flows_to_record(self, test_config: Settings) -> None:
        test_config.data_audit_path.mkdir(parents=True, exist_ok=True)
        result = await collect_diary(
            answers={"substance": "3-CMC", "content": "struggled today"},
            config=test_config,
        )
        assert json.loads(result)["status"] == "stored"
