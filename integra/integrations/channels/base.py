"""Abstract base for communication channels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum


class Capability(StrEnum):
    """What a channel can do."""

    SEND_MESSAGE = "send_message"
    ASK_CONFIRMATION = "ask_confirmation"
    SEND_SELECTION = "send_selection"
    RICH_TEXT = "rich_text"
    INLINE_KEYBOARD = "inline_keyboard"


class Sensitivity(StrEnum):
    """Message sensitivity level for routing decisions."""

    NORMAL = "normal"  # general notifications, reminders
    SENSITIVE = "sensitive"  # health data, substance logs
    CRITICAL = "critical"  # HIL confirmations, penance tasks


class ConfirmationResult(StrEnum):
    """Outcome of an ask_confirmation call."""

    APPROVED = "APPROVED"
    DENIED = "DENIED"
    TIMED_OUT = "DENIED (timed out after 5 minutes)"


@dataclass
class MessageRef:
    """Reference to a sent message for editing/tracking."""

    channel: str  # provider name (e.g. "telegram")
    message_id: int
    chat_id: int


class CommunicationProvider(ABC):
    """Abstract communication channel provider.

    Implementations: TelegramProvider (Stage 1), WhatsAppProvider (Stage 3B).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name (e.g. 'telegram')."""

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[Capability]:
        """Set of capabilities this provider supports."""

    @abstractmethod
    async def send_message(
        self,
        text: str,
        parse_mode: str | None = None,
    ) -> MessageRef:
        """Send a plain message to the user."""

    @abstractmethod
    async def ask_confirmation(self, description: str) -> str:
        """Send a confirmation prompt and wait for response.

        Returns ConfirmationResult value string.
        """

    @abstractmethod
    async def notify(self, message: str) -> str:
        """Send a notification. Returns status string."""

    @abstractmethod
    async def send_selection(
        self,
        text: str,
        options: list[str],
        field_name: str,
    ) -> MessageRef:
        """Send a selection prompt with options. Returns message ref."""

    def supports(self, capability: Capability) -> bool:
        """Check if this provider supports a capability."""
        return capability in self.capabilities

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider (called during app startup)."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean shutdown (called during app teardown)."""


@dataclass
class ProviderConfig:
    """Configuration for a communication provider."""

    name: str
    enabled: bool = True
    priority: int = 0  # lower = higher priority
    sensitivity_levels: list[Sensitivity] = field(
        default_factory=lambda: list(Sensitivity),
    )
