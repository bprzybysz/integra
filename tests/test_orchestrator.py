"""Tests for integra.core.orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic.types

from integra.core.orchestrator import MAX_TOOL_ROUNDS, run_conversation


def _make_text_response(text: str) -> MagicMock:
    """Create a mock Messages response with a single text block."""
    block = MagicMock(spec=anthropic.types.TextBlock)
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def _make_tool_use_response(tool_name: str, tool_input: dict[str, object], tool_id: str = "tu_1") -> MagicMock:
    """Create a mock Messages response with a tool_use block."""
    block = MagicMock(spec=anthropic.types.ToolUseBlock)
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    block.id = tool_id
    response = MagicMock()
    response.content = [block]
    return response


class TestRunConversation:
    @patch("integra.core.orchestrator.anthropic.AsyncAnthropic")
    async def test_simple_text_response(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_text_response("Hello!"))

        result = await run_conversation("Hi")
        assert result == "Hello!"

    @patch("integra.core.orchestrator.dispatch_tool", new_callable=AsyncMock)
    @patch("integra.core.orchestrator.anthropic.AsyncAnthropic")
    async def test_tool_use_loop(self, mock_client_cls: MagicMock, mock_dispatch: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        # First call returns tool_use, second returns text
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response("notify_user", {"message": "done"}),
                _make_text_response("Notified."),
            ]
        )
        mock_dispatch.return_value = "OK"

        result = await run_conversation("Notify me")
        assert result == "Notified."
        mock_dispatch.assert_called_once()

    @patch("integra.core.orchestrator.dispatch_tool", new_callable=AsyncMock)
    @patch("integra.core.orchestrator.anthropic.AsyncAnthropic")
    async def test_max_rounds_exceeded(self, mock_client_cls: MagicMock, mock_dispatch: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        # Always return tool_use to exhaust rounds
        mock_client.messages.create = AsyncMock(
            return_value=_make_tool_use_response("notify_user", {"message": "loop"})
        )
        mock_dispatch.return_value = "OK"

        result = await run_conversation("loop forever")
        assert "maximum" in result.lower()
        assert mock_client.messages.create.call_count == MAX_TOOL_ROUNDS
