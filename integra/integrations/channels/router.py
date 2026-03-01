"""Channel router — dispatches messages to providers based on sensitivity."""

from __future__ import annotations

import logging

from integra.integrations.channels.base import (
    CommunicationProvider,
    Sensitivity,
)

logger = logging.getLogger(__name__)


class ChannelRouter:
    """Routes messages to the appropriate provider based on sensitivity.

    Currently: single provider (Telegram). Stage 3B adds WhatsApp.
    Routing logic: sensitivity → provider with matching capability + priority.
    """

    def __init__(self) -> None:
        self._providers: dict[str, CommunicationProvider] = {}
        self._sensitivity_map: dict[Sensitivity, str] = {}

    def register(
        self,
        provider: CommunicationProvider,
        sensitivity_levels: list[Sensitivity] | None = None,
    ) -> None:
        """Register a provider for given sensitivity levels."""
        self._providers[provider.name] = provider
        levels = sensitivity_levels or list(Sensitivity)
        for level in levels:
            # First registered provider for a level wins (priority by order)
            if level not in self._sensitivity_map:
                self._sensitivity_map[level] = provider.name

    def get_provider(
        self,
        sensitivity: Sensitivity = Sensitivity.NORMAL,
    ) -> CommunicationProvider:
        """Get the provider for a sensitivity level."""
        name = self._sensitivity_map.get(sensitivity)
        if name is None or name not in self._providers:
            # Fallback to any available provider
            if not self._providers:
                msg = "No communication providers registered"
                raise RuntimeError(msg)
            name = next(iter(self._providers))
            logger.warning(
                "No provider for sensitivity=%s, falling back to %s",
                sensitivity,
                name,
            )
        return self._providers[name]

    @property
    def default(self) -> CommunicationProvider:
        """Get the default provider (first registered)."""
        if not self._providers:
            msg = "No communication providers registered"
            raise RuntimeError(msg)
        return next(iter(self._providers.values()))

    async def send_message(
        self,
        text: str,
        sensitivity: Sensitivity = Sensitivity.NORMAL,
        parse_mode: str | None = None,
    ) -> object:
        """Route a message to the appropriate provider."""
        provider = self.get_provider(sensitivity)
        return await provider.send_message(text, parse_mode=parse_mode)

    async def ask_confirmation(
        self,
        description: str,
        sensitivity: Sensitivity = Sensitivity.CRITICAL,
    ) -> str:
        """Route a confirmation request."""
        provider = self.get_provider(sensitivity)
        return await provider.ask_confirmation(description)

    async def notify(
        self,
        message: str,
        sensitivity: Sensitivity = Sensitivity.NORMAL,
    ) -> str:
        """Route a notification."""
        provider = self.get_provider(sensitivity)
        return await provider.notify(message)
