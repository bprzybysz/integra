"""Protocol for questionnaire interaction backends."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from integra.integrations.questionnaire import Question


class QuestionnaireUI(Protocol):
    """Protocol for questionnaire interaction backends."""

    async def send_status(self, text: str, parse_mode: str | None = None) -> None:
        """Send a status/header message."""
        ...

    async def ask_text(self, question: Question) -> str:
        """Ask a text/numeric/time question, return answer string."""
        ...

    async def ask_selection(self, question: Question) -> str:
        """Ask a selection question with options, return selected option."""
        ...
