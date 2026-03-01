"""Telegram implementation of CommunicationProvider."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, ContextTypes

from integra.core.config import settings
from integra.integrations.channels.base import (
    Capability,
    CommunicationProvider,
    ConfirmationResult,
    MessageRef,
)

logger = logging.getLogger(__name__)

# Pending HIL confirmation futures: message_id -> Future[bool]
_pending: dict[int, asyncio.Future[bool]] = {}

# prevent fire-and-forget tasks from being garbage collected
_background_tasks: set[asyncio.Task[None]] = set()


class TelegramProvider(CommunicationProvider):
    """Telegram-based communication provider.

    Wraps python-telegram-bot for HIL, notifications, and questionnaire delivery.
    """

    def __init__(self, bot_token: str = "", admin_chat_id: int = 0) -> None:
        self._bot_token = bot_token or settings.telegram_bot_token
        self._admin_chat_id = admin_chat_id or settings.telegram_admin_chat_id
        self._bot: Bot | None = None
        self._app: Application[Any, Any, Any, Any, Any, Any] | None = None

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset(Capability)

    @property
    def bot(self) -> Bot:
        """Return the bot instance, creating lazily if needed."""
        if self._bot is None:
            self._bot = Bot(token=self._bot_token)
        return self._bot

    @property
    def app(self) -> Application[Any, Any, Any, Any, Any, Any] | None:
        """Return the Application instance (None before initialize)."""
        return self._app

    @property
    def admin_chat_id(self) -> int:
        return self._admin_chat_id

    def set_bot(self, bot: Bot) -> None:
        """Override the bot instance (useful for testing)."""
        self._bot = bot

    async def initialize(self) -> None:
        """Build and start the Telegram Application with polling."""
        if not self._bot_token:
            logger.warning("No Telegram bot token — provider disabled")
            return
        self._app = ApplicationBuilder().token(self._bot_token).build()
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        await self._app.initialize()
        await self._app.start()
        if self._app.updater is not None:
            await self._app.updater.start_polling()
        self._bot = self._app.bot
        logger.info("TelegramProvider initialized")

    async def shutdown(self) -> None:
        """Stop polling and shut down the Application."""
        if self._app is not None:
            if self._app.updater is not None:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("TelegramProvider shut down")

    async def send_message(
        self,
        text: str,
        parse_mode: str | None = None,
    ) -> MessageRef:
        """Send a message to the admin chat."""
        msg = await self.bot.send_message(
            chat_id=self._admin_chat_id,
            text=text,
            parse_mode=parse_mode,
        )
        return MessageRef(
            channel="telegram",
            message_id=msg.message_id,
            chat_id=self._admin_chat_id,
        )

    async def ask_confirmation(self, description: str) -> str:
        """Send inline-keyboard confirmation and wait for response."""
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Approve", callback_data="approve"),
                    InlineKeyboardButton("Deny", callback_data="deny"),
                ]
            ]
        )
        msg = await self.bot.send_message(
            chat_id=self._admin_chat_id,
            text=f"**Confirmation Required**\n\n{description}",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        _pending[msg.message_id] = future

        try:
            approved = await asyncio.wait_for(future, timeout=300)
        except TimeoutError:
            await self.bot.edit_message_text(
                chat_id=self._admin_chat_id,
                message_id=msg.message_id,
                text=f"~~{description}~~\n\n_Timed out_",
                parse_mode="Markdown",
            )
            return ConfirmationResult.TIMED_OUT
        finally:
            _pending.pop(msg.message_id, None)

        status = ConfirmationResult.APPROVED if approved else ConfirmationResult.DENIED
        await self.bot.edit_message_text(
            chat_id=self._admin_chat_id,
            message_id=msg.message_id,
            text=f"{description}\n\n_User {status}_",
            parse_mode="Markdown",
        )
        return status

    async def notify(self, message: str) -> str:
        """Send a notification to the admin chat."""
        await self.bot.send_message(chat_id=self._admin_chat_id, text=message)
        return "Notification sent."

    async def send_selection(
        self,
        text: str,
        options: list[str],
        field_name: str,
    ) -> MessageRef:
        """Send an inline keyboard selection."""
        buttons = [[InlineKeyboardButton(opt, callback_data=f"q:{field_name}:{opt}")] for opt in options]
        keyboard = InlineKeyboardMarkup(buttons)
        msg = await self.bot.send_message(
            chat_id=self._admin_chat_id,
            text=text,
            reply_markup=keyboard,
        )
        return MessageRef(
            channel="telegram",
            message_id=msg.message_id,
            chat_id=self._admin_chat_id,
        )

    async def _handle_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Process inline-keyboard callbacks. Security: admin-only."""
        query = update.callback_query
        if query is None:
            return

        if query.from_user is None or query.from_user.id != self._admin_chat_id:
            logger.warning(
                "Unauthorized callback from user_id=%s",
                query.from_user.id if query.from_user else "unknown",
            )
            await query.answer(text="Unauthorized.", show_alert=True)
            return

        await query.answer()

        message = query.message
        if message is None:
            return

        msg_id = message.message_id
        future = _pending.get(msg_id)
        if future is not None and not future.done():
            future.set_result(query.data == "approve")


# ---------------------------------------------------------------------------
# Module-level command callbacks — set from app.py
# ---------------------------------------------------------------------------

_diary_callback: Callable[[], Coroutine[Any, Any, None]] | None = None
_interrupt_callback: Callable[[str], Coroutine[Any, Any, None]] | None = None


def set_diary_callback(fn: Callable[[], Coroutine[Any, Any, None]]) -> None:
    """Set the callback for /diary command."""
    global _diary_callback  # noqa: PLW0603
    _diary_callback = fn


def set_interrupt_callback(fn: Callable[[str], Coroutine[Any, Any, None]]) -> None:
    """Set the callback for /task command."""
    global _interrupt_callback  # noqa: PLW0603
    _interrupt_callback = fn


async def _handle_diary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /diary — trigger on-demand diary entry. Admin only."""
    if update.message is None or update.message.from_user is None:
        return
    if update.message.from_user.id != settings.telegram_admin_chat_id:
        return
    if _diary_callback is None:
        await update.message.reply_text("Diary not configured.")
        return
    task = asyncio.create_task(_diary_callback())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _handle_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /task <name> — interrupt current and start named task. Admin only."""
    if update.message is None or update.message.from_user is None:
        return
    if update.message.from_user.id != settings.telegram_admin_chat_id:
        return
    args: list[str] | None = getattr(context, "args", None)
    if args:
        task_name = args[0]
    else:
        await update.message.reply_text("Usage: /task <schedule_name>")
        return
    if _interrupt_callback is None:
        await update.message.reply_text("Task interrupt not configured.")
        return
    task = asyncio.create_task(_interrupt_callback(task_name))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def register_command_handlers(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
    """Register /diary and /task command handlers on Application."""
    from telegram.ext import CommandHandler

    app.add_handler(CommandHandler("diary", _handle_diary_command))
    app.add_handler(CommandHandler("task", _handle_task_command))
