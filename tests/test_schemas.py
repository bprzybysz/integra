"""Tests for integra.data.schemas."""

from integra.data.schemas import (
    FrequencyUnit,
    SubstanceCategory,
    make_addiction_therapy_record,
    make_dietary_record,
    make_intake_record,
    make_supplement_record,
)


class TestMakeSupplementRecord:
    def test_creates_record_with_defaults(self) -> None:
        rec = make_supplement_record(name="Vitamin D", dose="5000", unit="IU")
        assert rec["name"] == "Vitamin D"
        assert rec["dose"] == "5000"
        assert rec["frequency"] == FrequencyUnit.DAILY
        assert rec["category"] == SubstanceCategory.SUPPLEMENT

    def test_creates_medication_record(self) -> None:
        rec = make_supplement_record(
            name="Metformin",
            dose="500",
            unit="mg",
            category=SubstanceCategory.MEDICATION,
            frequency=FrequencyUnit.TWICE_DAILY,
            time_of_day="morning,evening",
        )
        assert rec["category"] == "medication"
        assert rec["frequency"] == "twice_daily"

    def test_empty_notes_default(self) -> None:
        rec = make_supplement_record(name="Zinc", dose="25", unit="mg")
        assert rec["notes"] == ""


class TestMakeIntakeRecord:
    def test_creates_with_auto_timestamp(self) -> None:
        rec = make_intake_record(substance="3-CMC", amount="50", unit="mg")
        assert rec["substance"] == "3-CMC"
        assert rec["timestamp"] != ""

    def test_explicit_timestamp(self) -> None:
        rec = make_intake_record(substance="K", amount="100", unit="mg", timestamp="2026-02-28T10:00:00+01:00")
        assert rec["timestamp"] == "2026-02-28T10:00:00+01:00"

    def test_addiction_therapy_category(self) -> None:
        rec = make_intake_record(
            substance="3-CMC",
            amount="25",
            unit="mg",
            category=SubstanceCategory.ADDICTION_THERAPY,
        )
        assert rec["category"] == "addiction-therapy"


class TestMakeDietaryRecord:
    def test_creates_meal(self) -> None:
        rec = make_dietary_record(meal_type="lunch", items="Chicken, rice, broccoli")
        assert rec["meal_type"] == "lunch"
        assert "Chicken" in rec["items"]
        assert rec["timestamp"] != ""

    def test_snack_with_notes(self) -> None:
        rec = make_dietary_record(meal_type="snack", items="Almonds", notes="30g")
        assert rec["notes"] == "30g"


class TestMakeAddictionTherapyRecord:
    def test_creates_with_quota(self) -> None:
        rec = make_addiction_therapy_record(substance="3-CMC", amount="50", unit="mg", daily_quota="100")
        assert rec["daily_quota"] == "100"
        assert rec["substance"] == "3-CMC"

    def test_empty_quota_default(self) -> None:
        rec = make_addiction_therapy_record(substance="K", amount="25", unit="mg")
        assert rec["daily_quota"] == ""
