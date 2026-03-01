"""Telegram-backed QuestionnaireUI implementation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from integra.integrations.questionnaire import Question, QuestionType

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 300  # 5 minutes per question


class TelegramQuestionnaireUI:
    """Telegram bot implementation of the QuestionnaireUI protocol."""

    def __init__(self, bot: Bot, admin_chat_id: int) -> None:
        self._bot = bot
        self._admin_chat_id = admin_chat_id
        # Pending text responses: chat_id -> Future
        self._text_pending: dict[int, asyncio.Future[str]] = {}
        # Pending selection responses: (chat_id, message_id) -> Future
        self._selection_pending: dict[tuple[int, int], asyncio.Future[str]] = {}

    async def send_status(self, text: str, parse_mode: str | None = None) -> None:
        """Send a status/header message to the admin chat."""
        await self._bot.send_message(
            chat_id=self._admin_chat_id,
            text=text,
            parse_mode=parse_mode,
        )

    async def ask_text(self, question: Question) -> str:
        """Ask a free-text/numeric/time question and wait for reply."""
        prompt = question.text
        if question.question_type == QuestionType.NUMERIC:
            prompt += " (number)"
        elif question.question_type == QuestionType.TIME:
            prompt += " (HH:MM)"
        if question.default:
            prompt += f"\nDefault: {question.default}"

        await self._bot.send_message(chat_id=self._admin_chat_id, text=prompt)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._text_pending[self._admin_chat_id] = future

        try:
            answer = await asyncio.wait_for(future, timeout=TIMEOUT_SECONDS)
        except TimeoutError:
            answer = question.default
            await self._bot.send_message(
                chat_id=self._admin_chat_id,
                text=f"⏳ Timed out — using default: {answer or '(empty)'}",
            )
        finally:
            self._text_pending.pop(self._admin_chat_id, None)

        if question.question_type == QuestionType.NUMERIC:
            try:
                float(answer)
            except ValueError:
                await self._bot.send_message(
                    chat_id=self._admin_chat_id,
                    text=f"⚠️ Expected a number, got '{answer}'. Using as-is.",
                )

        return answer

    async def ask_selection(self, question: Question) -> str:
        """Ask a selection question with inline keyboard buttons."""
        buttons = [
            [InlineKeyboardButton(opt, callback_data=f"q:{question.field_name}:{opt}")] for opt in question.options
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        msg = await self._bot.send_message(
            chat_id=self._admin_chat_id,
            text=question.text,
            reply_markup=keyboard,
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._selection_pending[(self._admin_chat_id, msg.message_id)] = future

        try:
            answer = await asyncio.wait_for(future, timeout=TIMEOUT_SECONDS)
        except TimeoutError:
            answer = question.default or (question.options[0] if question.options else "")
            await self._bot.edit_message_text(
                chat_id=self._admin_chat_id,
                message_id=msg.message_id,
                text=f"{question.text}\n\n⏳ Timed out — selected: {answer}",
            )
        finally:
            self._selection_pending.pop((self._admin_chat_id, msg.message_id), None)

        return answer

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages for pending questionnaire questions.

        Security: Only processes messages from the configured admin user.
        """
        message = update.message
        if message is None or message.text is None:
            return

        if message.from_user is None or message.from_user.id != self._admin_chat_id:
            return

        chat_id = message.chat_id
        future = self._text_pending.get(chat_id)
        if future is not None and not future.done():
            future.set_result(message.text)

    async def handle_questionnaire_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard selections for questionnaire questions.

        Security: Only processes callbacks from the configured admin user.
        """
        query = update.callback_query
        if query is None or query.data is None:
            return
        if not query.data.startswith("q:"):
            return

        if query.from_user is None or query.from_user.id != self._admin_chat_id:
            logger.warning(
                "Unauthorized questionnaire callback from user_id=%s",
                query.from_user.id if query.from_user else "unknown",
            )
            await query.answer(text="Unauthorized.", show_alert=True)
            return

        await query.answer()

        message = query.message
        if message is None or not hasattr(message, "chat_id"):
            return

        chat_id: int = message.chat_id
        msg_id: int = message.message_id
        parts = query.data.split(":", 2)
        if len(parts) < 3:
            return
        selected = parts[2]

        future = self._selection_pending.get((chat_id, msg_id))
        if future is not None and not future.done():
            future.set_result(selected)
            await self._bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"Selected: {selected}",
            )

    def register_handlers(self, app: Any) -> None:
        """Register questionnaire message and callback handlers on Telegram Application."""
        from telegram.ext import CallbackQueryHandler, MessageHandler, filters

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        app.add_handler(CallbackQueryHandler(self.handle_questionnaire_callback, pattern=r"^q:"))
