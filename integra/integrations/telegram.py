"""Telegram Human-in-the-Loop: confirmations and notifications."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from integra.core.config import settings

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_pending: dict[int, asyncio.Future[bool]] = {}


def get_bot() -> Bot:
    """Return a lazily-initialised Bot instance."""
    global _bot  # noqa: PLW0603
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


def set_bot(bot: Bot) -> None:
    """Override the bot instance (useful for testing)."""
    global _bot  # noqa: PLW0603
    _bot = bot


async def ask_confirmation(action_description: str) -> str:
    """Send an inline-keyboard confirmation to the admin and wait for a response.

    Returns:
        ``"APPROVED"``, ``"DENIED"``, or ``"DENIED (timed out after 5 minutes)"``.
    """
    bot = get_bot()
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data="approve"),
                InlineKeyboardButton("Deny", callback_data="deny"),
            ]
        ]
    )
    msg = await bot.send_message(
        chat_id=settings.telegram_admin_chat_id,
        text=f"**Confirmation Required**\n\n{action_description}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    _pending[msg.message_id] = future

    try:
        approved = await asyncio.wait_for(future, timeout=300)
    except TimeoutError:
        await bot.edit_message_text(
            chat_id=settings.telegram_admin_chat_id,
            message_id=msg.message_id,
            text=f"~~{action_description}~~\n\n_Timed out_",
            parse_mode="Markdown",
        )
        return "DENIED (timed out after 5 minutes)"
    finally:
        _pending.pop(msg.message_id, None)

    status = "APPROVED" if approved else "DENIED"
    await bot.edit_message_text(
        chat_id=settings.telegram_admin_chat_id,
        message_id=msg.message_id,
        text=f"{action_description}\n\n_User {status}_",
        parse_mode="Markdown",
    )
    return status


async def notify(message: str) -> str:
    """Send a plain notification message to the admin chat."""
    bot = get_bot()
    await bot.send_message(chat_id=settings.telegram_admin_chat_id, text=message)
    return "Notification sent."


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process inline-keyboard callback data for pending confirmations."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    message = query.message
    if message is None:
        return

    msg_id = message.message_id
    future = _pending.get(msg_id)
    if future is not None and not future.done():
        future.set_result(query.data == "approve")


async def ask_confirmation_handler(**kwargs: object) -> str:
    """Tool handler wrapper for ask_confirmation."""
    question = str(kwargs.get("question", ""))
    return await ask_confirmation(question)


async def notify_handler(**kwargs: object) -> str:
    """Tool handler wrapper for notify."""
    message = str(kwargs.get("message", ""))
    return await notify(message)


def register_handlers(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Register Telegram callback-query handlers on the given Application."""
    app.add_handler(CallbackQueryHandler(handle_callback))
