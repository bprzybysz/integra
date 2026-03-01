"""Tests for integra.integrations.channels.router (ChannelRouter)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from integra.integrations.channels.base import (
    Capability,
    CommunicationProvider,
    MessageRef,
    Sensitivity,
)
from integra.integrations.channels.router import ChannelRouter


class FakeProvider(CommunicationProvider):
    """Minimal concrete provider for testing."""

    def __init__(self, name: str = "fake") -> None:
        self._name = name
        self.send_message_mock = AsyncMock(
            return_value=MessageRef(channel=name, message_id=1, chat_id=0),
        )
        self.ask_confirmation_mock = AsyncMock(return_value="APPROVED")
        self.notify_mock = AsyncMock(return_value="Sent.")
        self.send_selection_mock = AsyncMock(
            return_value=MessageRef(channel=name, message_id=2, chat_id=0),
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset(Capability)

    async def send_message(self, text: str, parse_mode: str | None = None) -> MessageRef:
        result: MessageRef = await self.send_message_mock(text, parse_mode=parse_mode)
        return result

    async def ask_confirmation(self, description: str) -> str:
        result: str = await self.ask_confirmation_mock(description)
        return result

    async def notify(self, message: str) -> str:
        result: str = await self.notify_mock(message)
        return result

    async def send_selection(self, text: str, options: list[str], field_name: str) -> MessageRef:
        result: MessageRef = await self.send_selection_mock(text, options, field_name)
        return result

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class TestChannelRouter:
    def test_register_and_get_provider(self) -> None:
        router = ChannelRouter()
        provider = FakeProvider("test")
        router.register(provider)
        assert router.get_provider(Sensitivity.NORMAL) is provider

    def test_default_returns_first_registered(self) -> None:
        router = ChannelRouter()
        p1 = FakeProvider("first")
        p2 = FakeProvider("second")
        router.register(p1)
        router.register(p2)
        assert router.default is p1

    def test_no_providers_raises(self) -> None:
        router = ChannelRouter()
        with pytest.raises(RuntimeError, match="No communication providers"):
            router.get_provider()

    def test_no_providers_default_raises(self) -> None:
        router = ChannelRouter()
        with pytest.raises(RuntimeError, match="No communication providers"):
            _ = router.default

    def test_sensitivity_routing(self) -> None:
        router = ChannelRouter()
        normal_provider = FakeProvider("normal")
        critical_provider = FakeProvider("critical")
        router.register(normal_provider, sensitivity_levels=[Sensitivity.NORMAL])
        router.register(critical_provider, sensitivity_levels=[Sensitivity.CRITICAL])
        assert router.get_provider(Sensitivity.NORMAL) is normal_provider
        assert router.get_provider(Sensitivity.CRITICAL) is critical_provider

    def test_fallback_on_unknown_sensitivity(self) -> None:
        router = ChannelRouter()
        provider = FakeProvider("only")
        router.register(provider, sensitivity_levels=[Sensitivity.NORMAL])
        # SENSITIVE not registered — falls back to first available
        result = router.get_provider(Sensitivity.SENSITIVE)
        assert result is provider

    @pytest.mark.asyncio
    async def test_send_message_routes(self) -> None:
        router = ChannelRouter()
        provider = FakeProvider("test")
        router.register(provider)
        await router.send_message("hello")
        provider.send_message_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ask_confirmation_routes(self) -> None:
        router = ChannelRouter()
        provider = FakeProvider("test")
        router.register(provider)
        result = await router.ask_confirmation("approve?")
        assert result == "APPROVED"
        provider.ask_confirmation_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_routes(self) -> None:
        router = ChannelRouter()
        provider = FakeProvider("test")
        router.register(provider)
        result = await router.notify("msg")
        assert result == "Sent."
        provider.notify_mock.assert_awaited_once()
