"""Tests for integra.integrations.channels.base ABC and types."""

from __future__ import annotations

from integra.integrations.channels.base import (
    Capability,
    ConfirmationResult,
    MessageRef,
    ProviderConfig,
    Sensitivity,
)


class TestCapability:
    def test_all_values_present(self) -> None:
        assert len(Capability) == 5
        names = {c.name for c in Capability}
        assert "SEND_MESSAGE" in names
        assert "ASK_CONFIRMATION" in names
        assert "SEND_SELECTION" in names
        assert "RICH_TEXT" in names
        assert "INLINE_KEYBOARD" in names


class TestSensitivity:
    def test_all_values_present(self) -> None:
        assert len(Sensitivity) == 3
        values = {s.value for s in Sensitivity}
        assert "normal" in values
        assert "sensitive" in values
        assert "critical" in values


class TestConfirmationResult:
    def test_approved(self) -> None:
        assert ConfirmationResult.APPROVED.value == "APPROVED"

    def test_denied(self) -> None:
        assert ConfirmationResult.DENIED.value == "DENIED"

    def test_timed_out_contains_denied(self) -> None:
        assert "DENIED" in ConfirmationResult.TIMED_OUT.value


class TestMessageRef:
    def test_fields(self) -> None:
        ref = MessageRef(channel="telegram", message_id=42, chat_id=123)
        assert ref.channel == "telegram"
        assert ref.message_id == 42
        assert ref.chat_id == 123


class TestProviderConfig:
    def test_defaults(self) -> None:
        cfg = ProviderConfig(name="telegram")
        assert cfg.enabled is True
        assert cfg.priority == 0
        assert len(cfg.sensitivity_levels) == len(Sensitivity)

    def test_custom_values(self) -> None:
        cfg = ProviderConfig(
            name="whatsapp",
            enabled=False,
            priority=1,
            sensitivity_levels=[Sensitivity.SENSITIVE],
        )
        assert cfg.name == "whatsapp"
        assert cfg.enabled is False
        assert cfg.priority == 1
        assert cfg.sensitivity_levels == [Sensitivity.SENSITIVE]
