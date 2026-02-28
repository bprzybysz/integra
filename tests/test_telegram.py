"""Tests for integra.integrations.telegram."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integra.integrations import telegram


@pytest.fixture(autouse=True)
def _reset_pending() -> None:
    """Clear pending futures between tests."""
    telegram._pending.clear()


@pytest.fixture()
def mock_bot() -> AsyncMock:
    """Provide a mock Bot and wire it into the telegram module."""
    bot = AsyncMock()
    telegram.set_bot(bot)
    return bot


@pytest.mark.asyncio
async def test_ask_confirmation_approved(mock_bot: AsyncMock) -> None:
    mock_msg = MagicMock()
    mock_msg.message_id = 42
    mock_bot.send_message.return_value = mock_msg
    mock_bot.edit_message_text.return_value = None

    async def _approve() -> str:
        # Wait briefly for the future to be registered
        await asyncio.sleep(0.01)
        future = telegram._pending.get(42)
        assert future is not None
        future.set_result(True)
        return ""

    task = asyncio.create_task(_approve())
    result = await telegram.ask_confirmation("Do something?")
    await task

    assert result == "APPROVED"
    mock_bot.send_message.assert_awaited_once()
    mock_bot.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_confirmation_denied(mock_bot: AsyncMock) -> None:
    mock_msg = MagicMock()
    mock_msg.message_id = 43
    mock_bot.send_message.return_value = mock_msg
    mock_bot.edit_message_text.return_value = None

    async def _deny() -> None:
        await asyncio.sleep(0.01)
        future = telegram._pending.get(43)
        assert future is not None
        future.set_result(False)

    task = asyncio.create_task(_deny())
    result = await telegram.ask_confirmation("Delete everything?")
    await task

    assert result == "DENIED"


@pytest.mark.asyncio
async def test_ask_confirmation_timeout(mock_bot: AsyncMock) -> None:
    mock_msg = MagicMock()
    mock_msg.message_id = 44
    mock_bot.send_message.return_value = mock_msg
    mock_bot.edit_message_text.return_value = None

    with patch("integra.integrations.telegram.asyncio.wait_for", side_effect=TimeoutError):
        result = await telegram.ask_confirmation("Slow action")

    assert "timed out" in result
    assert 44 not in telegram._pending


@pytest.mark.asyncio
async def test_notify(mock_bot: AsyncMock) -> None:
    mock_bot.send_message.return_value = None
    result = await telegram.notify("Hello admin")
    assert result == "Notification sent."
    mock_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_callback_resolves_future() -> None:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    telegram._pending[99] = future

    query = AsyncMock()
    query.data = "approve"
    query.message = MagicMock()
    query.message.message_id = 99

    update = MagicMock()
    update.callback_query = query

    await telegram.handle_callback(update, MagicMock())

    assert future.done()
    assert future.result() is True


@pytest.mark.asyncio
async def test_handle_callback_no_query() -> None:
    update = MagicMock()
    update.callback_query = None
    # Should return without error
    await telegram.handle_callback(update, MagicMock())
