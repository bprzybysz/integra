"""Communication channels package — ABC + provider implementations."""

from integra.integrations.channels.base import (
    Capability,
    CommunicationProvider,
    ConfirmationResult,
    MessageRef,
    Sensitivity,
)
from integra.integrations.channels.router import ChannelRouter
from integra.integrations.channels.telegram import TelegramProvider

__all__ = [
    "Capability",
    "ChannelRouter",
    "CommunicationProvider",
    "ConfirmationResult",
    "MessageRef",
    "Sensitivity",
    "TelegramProvider",
]
