"""Tests for integra.data.schemas."""

import json

from integra.data.schemas import (
    AdvisorState,
    FrequencyUnit,
    PenanceSeverity,
    RewardCategory,
    SubstanceCategory,
    make_addiction_therapy_record,
    make_controlled_use_record,
    make_dietary_record,
    make_intake_record,
    make_penance_record,
    make_supplement_record,
    make_trigger_context,
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

    def test_new_fields_defaults(self) -> None:
        rec = make_addiction_therapy_record(substance="K", amount="1", unit="touch")
        assert rec["week_number"] == 0
        assert rec["trigger_context"] == "{}"

    def test_with_trigger_context(self) -> None:
        ctx = make_trigger_context(lonely=True, craving_intensity=7)
        rec = make_addiction_therapy_record(
            substance="3-CMC",
            amount="50",
            unit="mg",
            trigger_context=json.dumps(ctx),
            week_number=9,
        )
        assert rec["week_number"] == 9
        parsed = json.loads(rec["trigger_context"])
        assert parsed["lonely"] is True
        assert parsed["craving_intensity"] == 7


class TestRewardCategory:
    def test_all_categories_exist(self) -> None:
        assert RewardCategory.HEALTHY.value == "healthy"
        assert RewardCategory.NEUTRAL.value == "neutral"
        assert RewardCategory.QUOTA.value == "quota"
        assert RewardCategory.ADDICTION_THERAPY.value == "addiction-therapy"
        assert RewardCategory.CONTROLLED_USE.value == "controlled-use"

    def test_controlled_use_in_substance_category(self) -> None:
        assert SubstanceCategory.CONTROLLED_USE.value == "controlled-use"


class TestMakeControlledUseRecord:
    def test_creates_with_defaults(self) -> None:
        rec = make_controlled_use_record(substance="BCD", amount="3", unit="clouds")
        assert rec["substance"] == "BCD"
        assert rec["work_hours_violation"] is False
        assert rec["cooldown_violation"] is False
        assert rec["daily_ceiling_exceeded"] is False
        assert rec["timestamp"] != ""

    def test_explicit_values(self) -> None:
        rec = make_controlled_use_record(
            substance="BCD",
            amount="5",
            unit="clouds",
            work_hours_violation=True,
            cooldown_violation=True,
            daily_ceiling_exceeded=True,
            ruliade="not during work hours",
            timestamp="2026-03-01T20:00:00+01:00",
        )
        assert rec["work_hours_violation"] is True
        assert rec["cooldown_violation"] is True
        assert rec["daily_ceiling_exceeded"] is True
        assert rec["timestamp"] == "2026-03-01T20:00:00+01:00"

    def test_no_violations_default(self) -> None:
        rec = make_controlled_use_record(substance="BCD", amount="1", unit="clouds")
        assert rec["work_hours_violation"] is False
        assert rec["daily_ceiling_exceeded"] is False


class TestAdvisorState:
    def test_all_states(self) -> None:
        assert AdvisorState.STRUGGLING.value == "struggling"
        assert AdvisorState.HOLDING.value == "holding"
        assert AdvisorState.THRIVING.value == "thriving"


class TestPenanceSeverity:
    def test_all_severities(self) -> None:
        assert PenanceSeverity.MINOR.value == "minor"
        assert PenanceSeverity.STANDARD.value == "standard"
        assert PenanceSeverity.ESCALATED.value == "escalated"


class TestMakeTriggerContext:
    def test_defaults(self) -> None:
        ctx = make_trigger_context()
        assert ctx["hungry"] is False
        assert ctx["angry"] is False
        assert ctx["lonely"] is False
        assert ctx["tired"] is False
        assert ctx["craving_intensity"] == 0
        assert ctx["situation_notes"] == ""
        assert ctx["substance"] == ""
        assert ctx["timestamp"] != ""

    def test_halt_flags(self) -> None:
        ctx = make_trigger_context(hungry=True, tired=True, craving_intensity=8)
        assert ctx["hungry"] is True
        assert ctx["tired"] is True
        assert ctx["craving_intensity"] == 8

    def test_with_situation_notes(self) -> None:
        ctx = make_trigger_context(situation_notes="late night, alone")
        assert ctx["situation_notes"] == "late night, alone"

    def test_explicit_timestamp(self) -> None:
        ts = "2026-03-01T20:00:00+01:00"
        ctx = make_trigger_context(timestamp=ts)
        assert ctx["timestamp"] == ts

    def test_substance_field(self) -> None:
        ctx = make_trigger_context(substance="3-CMC")
        assert ctx["substance"] == "3-CMC"


class TestMakePenanceRecord:
    def test_creates_with_defaults(self) -> None:
        rec = make_penance_record(substance="3-CMC", relapse_amount="50mg")
        assert rec["substance"] == "3-CMC"
        assert rec["penance_severity"] == "minor"
        assert rec["penance_gh_issue_id"] == ""
        assert rec["penance_completed"] is False
        assert rec["penance_completed_at"] == ""
        assert rec["relapse_timestamp"] != ""

    def test_escalated_severity(self) -> None:
        rec = make_penance_record(
            substance="K",
            relapse_amount="5 touches",
            penance_severity=PenanceSeverity.ESCALATED,
            penance_description="gym + 1h study block",
        )
        assert rec["penance_severity"] == "escalated"
        assert rec["penance_description"] == "gym + 1h study block"

    def test_explicit_timestamp(self) -> None:
        rec = make_penance_record(
            substance="THC",
            relapse_amount="3 clouds",
            relapse_timestamp="2026-03-01T22:00:00+01:00",
        )
        assert rec["relapse_timestamp"] == "2026-03-01T22:00:00+01:00"
