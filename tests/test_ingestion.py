"""Tests for integra.data.ingestion — edge cases (Issue #25)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from integra.data.ingestion import (
    IngestResult,
    _parse_csv_file,
    _parse_json_file,
    ingest_from_landing_zone,
)

# ---------------------------------------------------------------------------
# _parse_json_file — unit tests
# ---------------------------------------------------------------------------


class TestParseJsonFile:
    def test_valid_list(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('[{"a": 1}, {"b": 2}]')
        result = _parse_json_file(f)
        assert result == [{"a": 1}, {"b": 2}]

    def test_valid_dict_wrapped_in_list(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"key": "val"}')
        result = _parse_json_file(f)
        assert result == [{"key": "val"}]

    # Issue #25 — test 1: malformed JSON raises ValueError (wrapped by json.JSONDecodeError)
    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{not valid json{{{{")
        with pytest.raises(json.JSONDecodeError):
            _parse_json_file(f)

    # Issue #25 — test 3 (partial): empty JSON file is malformed, raises decode error
    def test_empty_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.json"
        f.write_text("")
        with pytest.raises(json.JSONDecodeError):
            _parse_json_file(f)

    def test_json_array_of_primitives_skipped(self, tmp_path: Path) -> None:
        """Non-dict items in a JSON list are filtered out (not crashes)."""
        f = tmp_path / "mixed.json"
        f.write_text('[{"a": 1}, "string", 42, null]')
        result = _parse_json_file(f)
        # Only dict items survive the filter
        assert result == [{"a": 1}]

    def test_json_scalar_raises_value_error(self, tmp_path: Path) -> None:
        """A bare scalar (not list/dict) raises ValueError."""
        f = tmp_path / "scalar.json"
        f.write_text('"just a string"')
        with pytest.raises(ValueError, match="Unsupported JSON structure"):
            _parse_json_file(f)


# ---------------------------------------------------------------------------
# _parse_csv_file — unit tests
# ---------------------------------------------------------------------------


class TestParseCsvFile:
    def test_valid_csv(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("name,dose\nVit D,5000\nZinc,25\n")
        result = _parse_csv_file(f)
        assert result == [{"name": "Vit D", "dose": "5000"}, {"name": "Zinc", "dose": "25"}]

    # Issue #25 — test 3 (empty CSV): returns empty list, no exception
    def test_empty_csv_returns_empty_list(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.csv"
        f.write_text("")
        result = _parse_csv_file(f)
        assert result == []

    def test_header_only_csv_returns_empty_list(self, tmp_path: Path) -> None:
        f = tmp_path / "header_only.csv"
        f.write_text("name,dose\n")
        result = _parse_csv_file(f)
        assert result == []


# ---------------------------------------------------------------------------
# ingest_from_landing_zone — integration-style tests with mocked dependencies
# ---------------------------------------------------------------------------


def _make_settings(tmp_path: Path) -> MagicMock:
    s = MagicMock()
    s.data_raw_path = tmp_path / "raw"
    s.data_lake_path = tmp_path / "lake"
    s.data_audit_path = tmp_path / "audit"
    s.age_recipient = "age1testrecipient"
    return s


class TestIngestFromLandingZone:
    @pytest.mark.asyncio
    async def test_missing_landing_zone_returns_empty(self, tmp_path: Path) -> None:
        config = _make_settings(tmp_path)
        # raw_path does NOT exist — should return empty result, not raise
        result = await ingest_from_landing_zone(config)
        assert isinstance(result, IngestResult)
        assert result.files_processed == 0
        assert result.records_ingested == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_empty_landing_zone_returns_empty(self, tmp_path: Path) -> None:
        config = _make_settings(tmp_path)
        config.data_raw_path.mkdir(parents=True)
        # No files — should return empty result
        result = await ingest_from_landing_zone(config)
        assert result.files_processed == 0
        assert result.records_ingested == 0

    # Issue #25 — test 1: malformed JSON file → error captured, no crash
    @pytest.mark.asyncio
    async def test_malformed_json_captured_in_errors(self, tmp_path: Path) -> None:
        config = _make_settings(tmp_path)
        raw = config.data_raw_path / "uncategorized"
        raw.mkdir(parents=True)
        config.data_audit_path.mkdir(parents=True)
        bad = raw / "bad.json"
        bad.write_text("{not valid json")

        with (
            patch("integra.data.ingestion.encrypt_record", return_value=b"encrypted"),
            patch("integra.data.ingestion.write_audit_entry"),
        ):
            result = await ingest_from_landing_zone(config)

        assert result.files_processed == 0
        assert len(result.errors) == 1
        assert "bad.json" in result.errors[0]

    # Issue #25 — test 2: unsupported file extension → error captured, no crash
    @pytest.mark.asyncio
    async def test_unsupported_extension_captured_in_errors(self, tmp_path: Path) -> None:
        config = _make_settings(tmp_path)
        raw = config.data_raw_path / "uncategorized"
        raw.mkdir(parents=True)
        config.data_audit_path.mkdir(parents=True)
        xyz = raw / "data.xyz"
        xyz.write_text("some data")

        with (
            patch("integra.data.ingestion.encrypt_record", return_value=b"encrypted"),
            patch("integra.data.ingestion.write_audit_entry"),
        ):
            result = await ingest_from_landing_zone(config)

        assert result.files_processed == 0
        assert len(result.errors) == 1
        assert "Unsupported file type" in result.errors[0] or "data.xyz" in result.errors[0]

    # Issue #25 — test 3: empty file → no exception, error captured or empty result
    @pytest.mark.asyncio
    async def test_empty_json_file_captured_in_errors(self, tmp_path: Path) -> None:
        config = _make_settings(tmp_path)
        raw = config.data_raw_path / "uncategorized"
        raw.mkdir(parents=True)
        config.data_audit_path.mkdir(parents=True)
        empty = raw / "empty.json"
        empty.write_text("")

        with (
            patch("integra.data.ingestion.encrypt_record", return_value=b"encrypted"),
            patch("integra.data.ingestion.write_audit_entry"),
        ):
            result = await ingest_from_landing_zone(config)

        # Empty JSON file raises JSONDecodeError — captured in errors, no crash
        assert result.files_processed == 0
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_empty_csv_file_processes_zero_records(self, tmp_path: Path) -> None:
        """Empty CSV (header only or blank) ingests successfully with 0 records."""
        config = _make_settings(tmp_path)
        raw = config.data_raw_path / "uncategorized"
        raw.mkdir(parents=True)
        config.data_audit_path.mkdir(parents=True)
        empty_csv = raw / "empty.csv"
        empty_csv.write_text("")

        with (
            patch("integra.data.ingestion.encrypt_record", return_value=b"encrypted"),
            patch("integra.data.ingestion.write_audit_entry"),
        ):
            result = await ingest_from_landing_zone(config)

        # Empty CSV yields 0 records but the file is "processed" with no errors
        assert result.errors == []
        assert result.records_ingested == 0

    @pytest.mark.asyncio
    async def test_file_too_large_captured_in_errors(self, tmp_path: Path) -> None:
        """File exceeding MAX_FILE_SIZE is rejected with an error, no crash."""
        config = _make_settings(tmp_path)
        raw = config.data_raw_path / "uncategorized"
        raw.mkdir(parents=True)
        big = raw / "big.json"
        big.write_text('{"x": 1}')

        with (
            patch("integra.data.ingestion.MAX_FILE_SIZE", 1),
            patch("integra.data.ingestion.encrypt_record", return_value=b"encrypted"),
            patch("integra.data.ingestion.write_audit_entry"),
        ):
            result = await ingest_from_landing_zone(config)

        assert result.files_processed == 0
        assert len(result.errors) == 1
        assert "too large" in result.errors[0]
