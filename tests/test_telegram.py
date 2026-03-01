"""Tests for integra.integrations.channels.telegram (TelegramProvider)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integra.integrations.channels.telegram import (
    TelegramProvider,
    _handle_diary_command,
    _handle_help_command,
    _handle_requester_message,
    _handle_start_command,
    _handle_task_command,
    _pending,
    set_diary_callback,
    set_interrupt_callback,
    set_requester_ids,
)


@pytest.fixture(autouse=True)
def _reset_pending() -> None:
    """Clear pending futures between tests."""
    _pending.clear()


def _make_provider() -> tuple[TelegramProvider, Any]:
    """Create a TelegramProvider with a mock bot, returning (provider, mock_bot)."""
    p = TelegramProvider(bot_token="fake-token", admin_chat_id=12345)
    bot = AsyncMock()
    p.set_bot(bot)
    return p, bot


@pytest.mark.asyncio
async def test_ask_confirmation_approved() -> None:
    p, bot = _make_provider()
    mock_msg = MagicMock()
    mock_msg.message_id = 42
    bot.send_message.return_value = mock_msg
    bot.edit_message_text.return_value = None

    async def _approve() -> None:
        await asyncio.sleep(0.01)
        future = _pending.get(42)
        assert future is not None
        future.set_result(True)

    task = asyncio.create_task(_approve())
    result = await p.ask_confirmation("Do something?")
    await task

    assert result == "APPROVED"
    bot.send_message.assert_awaited_once()
    bot.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_confirmation_denied() -> None:
    p, bot = _make_provider()
    mock_msg = MagicMock()
    mock_msg.message_id = 43
    bot.send_message.return_value = mock_msg
    bot.edit_message_text.return_value = None

    async def _deny() -> None:
        await asyncio.sleep(0.01)
        future = _pending.get(43)
        assert future is not None
        future.set_result(False)

    task = asyncio.create_task(_deny())
    result = await p.ask_confirmation("Delete everything?")
    await task

    assert result == "DENIED"


@pytest.mark.asyncio
async def test_ask_confirmation_timeout() -> None:
    p, bot = _make_provider()
    mock_msg = MagicMock()
    mock_msg.message_id = 44
    bot.send_message.return_value = mock_msg
    bot.edit_message_text.return_value = None

    with patch(
        "integra.integrations.channels.telegram.asyncio.wait_for",
        side_effect=TimeoutError,
    ):
        result = await p.ask_confirmation("Slow action")

    assert "timed out" in result.lower()
    assert 44 not in _pending


@pytest.mark.asyncio
async def test_notify() -> None:
    p, bot = _make_provider()
    bot.send_message.return_value = None
    result = await p.notify("Hello admin")
    assert result == "Notification sent."
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_callback_resolves_future() -> None:
    p, _bot = _make_provider()
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    _pending[99] = future

    query = AsyncMock()
    query.data = "approve"
    query.from_user = MagicMock()
    query.from_user.id = 12345  # matches provider admin_chat_id
    query.message = MagicMock()
    query.message.message_id = 99

    update = MagicMock()
    update.callback_query = query

    await p._handle_callback(update, MagicMock())

    assert future.done()
    assert future.result() is True


@pytest.mark.asyncio
async def test_handle_callback_no_query() -> None:
    p, _bot = _make_provider()
    update = MagicMock()
    update.callback_query = None
    await p._handle_callback(update, MagicMock())


@pytest.mark.asyncio
async def test_send_message() -> None:
    p, bot = _make_provider()
    mock_msg = MagicMock()
    mock_msg.message_id = 10
    bot.send_message.return_value = mock_msg

    ref = await p.send_message("Test message")

    assert ref.channel == "telegram"
    assert ref.message_id == 10
    assert ref.chat_id == 12345


@pytest.mark.asyncio
async def test_send_selection() -> None:
    p, bot = _make_provider()
    mock_msg = MagicMock()
    mock_msg.message_id = 20
    bot.send_message.return_value = mock_msg

    ref = await p.send_selection("Pick one", ["A", "B"], "choice")

    assert ref.message_id == 20
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_properties() -> None:
    p = TelegramProvider(bot_token="tok", admin_chat_id=999)
    assert p.name == "telegram"
    assert len(p.capabilities) > 0
    assert p.admin_chat_id == 999


# ---------------------------------------------------------------------------
# Command handler tests
# ---------------------------------------------------------------------------


def _make_update(user_id: int, text: str = "/diary", args: list[str] | None = None) -> tuple[Any, Any]:
    """Build mock update + context for command handlers."""
    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id

    update = MagicMock()
    update.message = message

    context = MagicMock()
    context.args = args

    return update, context


@pytest.mark.asyncio
async def test_diary_command_fires_callback() -> None:
    called: list[bool] = []

    async def _cb() -> None:
        called.append(True)

    set_diary_callback(_cb)
    with patch("integra.core.config.settings") as mock_settings:
        mock_settings.telegram_admin_chat_id = 12345
        update, context = _make_update(user_id=12345)
        with patch("integra.integrations.channels.telegram.settings", mock_settings):
            await _handle_diary_command(update, context)

    # Give the task a chance to run
    await asyncio.sleep(0.05)
    assert called == [True]


@pytest.mark.asyncio
async def test_diary_command_unauthorized() -> None:
    called: list[bool] = []

    async def _cb() -> None:
        called.append(True)

    set_diary_callback(_cb)
    with patch("integra.core.config.settings") as mock_settings:
        mock_settings.telegram_admin_chat_id = 12345
        update, context = _make_update(user_id=99999)
        with patch("integra.integrations.channels.telegram.settings", mock_settings):
            await _handle_diary_command(update, context)

    await asyncio.sleep(0.05)
    assert called == []


@pytest.mark.asyncio
async def test_task_command_with_name() -> None:
    received: list[str] = []

    async def _cb(name: str) -> None:
        received.append(name)

    set_interrupt_callback(_cb)
    with patch("integra.core.config.settings") as mock_settings:
        mock_settings.telegram_admin_chat_id = 12345
        update, context = _make_update(user_id=12345, args=["morning_supplement_check"])
        with patch("integra.integrations.channels.telegram.settings", mock_settings):
            await _handle_task_command(update, context)

    await asyncio.sleep(0.05)
    assert received == ["morning_supplement_check"]


@pytest.mark.asyncio
async def test_task_command_no_args() -> None:
    with patch("integra.core.config.settings") as mock_settings:
        mock_settings.telegram_admin_chat_id = 12345
        update, context = _make_update(user_id=12345, args=None)
        with patch("integra.integrations.channels.telegram.settings", mock_settings):
            await _handle_task_command(update, context)

    update.message.reply_text.assert_awaited_once_with("Usage: /task <schedule_name>")


@pytest.mark.asyncio
async def test_start_command_authorized() -> None:
    with patch("integra.core.config.settings") as mock_settings:
        mock_settings.telegram_admin_chat_id = 12345
        update, context = _make_update(user_id=12345)
        with patch("integra.integrations.channels.telegram.settings", mock_settings):
            await _handle_start_command(update, context)

    update.message.reply_text.assert_awaited_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "Integra" in call_text


@pytest.mark.asyncio
async def test_start_command_unauthorized() -> None:
    with patch("integra.core.config.settings") as mock_settings:
        mock_settings.telegram_admin_chat_id = 12345
        update, context = _make_update(user_id=99999)
        with patch("integra.integrations.channels.telegram.settings", mock_settings):
            await _handle_start_command(update, context)

    update.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_help_command_lists_commands() -> None:
    with patch("integra.core.config.settings") as mock_settings:
        mock_settings.telegram_admin_chat_id = 12345
        update, context = _make_update(user_id=12345)
        with patch("integra.integrations.channels.telegram.settings", mock_settings):
            await _handle_help_command(update, context)

    update.message.reply_text.assert_awaited_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "/diary" in call_text
    assert "/task" in call_text


# ---------------------------------------------------------------------------
# Requester-tier tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_requester_message_stored() -> None:
    """Requester-tier user text message → stored as IncomingRequest."""
    set_requester_ids({99001})

    stored: list[dict[str, Any]] = []

    async def _fake_store(**kwargs: Any) -> str:
        stored.append(kwargs)
        return json.dumps({"status": "stored", "request_id": "99001_1"})

    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 99001
    message.from_user.first_name = "Mom"
    message.text = "buy milk please"

    update = MagicMock()
    update.message = message

    with (
        patch("integra.core.config.settings") as mock_settings,
        patch("integra.integrations.channels.telegram.settings", mock_settings),
        patch("integra.integrations.channels.telegram.store_request", _fake_store),
    ):
        mock_settings.telegram_admin_chat_id = 12345
        await _handle_requester_message(update, MagicMock())

    assert len(stored) == 1
    assert stored[0]["text"] == "buy milk please"
    message.reply_text.assert_awaited_once_with("Sent.")


@pytest.mark.asyncio
async def test_requester_message_unknown_user_ignored() -> None:
    """Unknown user text message → silently ignored."""
    set_requester_ids({99001})

    stored: list[dict[str, Any]] = []

    async def _fake_store(**kwargs: Any) -> str:
        stored.append(kwargs)
        return json.dumps({"status": "stored", "request_id": "x"})

    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 99999  # not in requester_ids
    message.from_user.first_name = "Stranger"
    message.text = "hello"

    update = MagicMock()
    update.message = message

    with (
        patch("integra.core.config.settings") as mock_settings,
        patch("integra.integrations.channels.telegram.settings", mock_settings),
        patch("integra.integrations.channels.telegram.store_request", _fake_store),
    ):
        mock_settings.telegram_admin_chat_id = 12345
        await _handle_requester_message(update, MagicMock())

    assert stored == []
    message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_message_not_stored_as_request() -> None:
    """Admin text message → not stored as IncomingRequest (admin uses commands)."""
    set_requester_ids({99001})

    stored: list[dict[str, Any]] = []

    async def _fake_store(**kwargs: Any) -> str:
        stored.append(kwargs)
        return json.dumps({"status": "stored", "request_id": "x"})

    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 12345  # admin
    message.from_user.first_name = "Admin"
    message.text = "some text"

    update = MagicMock()
    update.message = message

    with (
        patch("integra.core.config.settings") as mock_settings,
        patch("integra.integrations.channels.telegram.settings", mock_settings),
        patch("integra.integrations.channels.telegram.store_request", _fake_store),
    ):
        mock_settings.telegram_admin_chat_id = 12345
        await _handle_requester_message(update, MagicMock())

    assert stored == []
