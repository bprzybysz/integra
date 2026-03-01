"""Tests for integra.core.orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic.types
import pytest

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

    # Issue #26 — test 1: response with both text AND tool_use block in same message
    @patch("integra.core.orchestrator.dispatch_tool", new_callable=AsyncMock)
    @patch("integra.core.orchestrator.anthropic.AsyncAnthropic")
    async def test_mixed_text_and_tool_use_blocks(self, mock_client_cls: MagicMock, mock_dispatch: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        # First response: text block + tool_use block together
        text_block = MagicMock(spec=anthropic.types.TextBlock)
        text_block.type = "text"
        text_block.text = "Let me notify you."

        tool_block = MagicMock(spec=anthropic.types.ToolUseBlock)
        tool_block.type = "tool_use"
        tool_block.name = "notify_user"
        tool_block.input = {"message": "done"}
        tool_block.id = "tu_mix_1"

        mixed_response = MagicMock()
        mixed_response.content = [text_block, tool_block]

        # Second response: pure text (loop terminates)
        second_response = _make_text_response("Done.")

        mock_client.messages.create = AsyncMock(side_effect=[mixed_response, second_response])
        mock_dispatch.return_value = "OK"

        result = await run_conversation("notify me with text")
        # Loop must complete and return the final text
        assert result == "Done."
        # dispatch was called once for the tool_use block
        mock_dispatch.assert_called_once()

    # Issue #26 — test 2: exception raised during dispatch_tool() propagates from orchestrator.
    # Note: run_conversation does NOT wrap dispatch_tool in try/except — exceptions propagate.
    # The graceful error handling is inside dispatch_tool itself (registry.py), not the loop.
    # This test documents the actual behaviour: unhandled exceptions from dispatch bubble up.
    @patch("integra.core.orchestrator.dispatch_tool", new_callable=AsyncMock)
    @patch("integra.core.orchestrator.anthropic.AsyncAnthropic")
    async def test_dispatch_exception_propagates(
        self, mock_client_cls: MagicMock, mock_dispatch: AsyncMock
    ) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        # Mock dispatch to raise — this simulates an unexpected error in the dispatch layer
        mock_dispatch.side_effect = RuntimeError("handler blew up")

        mock_client.messages.create = AsyncMock(
            return_value=_make_tool_use_response("notify_user", {"message": "hi"})
        )

        # The orchestrator does NOT suppress RuntimeError from dispatch_tool;
        # it propagates to the caller.
        with pytest.raises(RuntimeError, match="handler blew up"):
            await run_conversation("trigger error")

    # Issue #26 — test 3: tool with empty input dict {} → dispatched without error
    @patch("integra.core.orchestrator.dispatch_tool", new_callable=AsyncMock)
    @patch("integra.core.orchestrator.anthropic.AsyncAnthropic")
    async def test_empty_tool_input_dispatched(self, mock_client_cls: MagicMock, mock_dispatch: AsyncMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_tool_use_response("analyze_cc_productivity", {}, tool_id="tu_empty"),
                _make_text_response("Analysis done."),
            ]
        )
        mock_dispatch.return_value = "result data"

        result = await run_conversation("analyze productivity")
        assert result == "Analysis done."
        # dispatch was called with empty input_data
        mock_dispatch.assert_called_once_with(
            name="analyze_cc_productivity",
            input_data={},
            confirm_fn=None,
        )
