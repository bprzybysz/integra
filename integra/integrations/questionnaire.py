"""Telegram questionnaire engine for structured data collection."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from integra.core.config import settings
from integra.integrations.telegram import get_bot

logger = logging.getLogger(__name__)


class QuestionType(StrEnum):
    """Supported question input types."""

    TEXT = "text"
    NUMERIC = "numeric"
    SELECTION = "selection"
    TIME = "time"


@dataclass
class Question:
    """A single question in a questionnaire."""

    text: str
    field_name: str
    question_type: QuestionType = QuestionType.TEXT
    options: list[str] = field(default_factory=list)
    required: bool = True
    default: str = ""


@dataclass
class Questionnaire:
    """An ordered list of questions to collect structured data."""

    title: str
    questions: list[Question]


# Pending text responses: chat_id -> Future
_text_pending: dict[int, asyncio.Future[str]] = {}

# Pending selection responses: (chat_id, message_id) -> Future
_selection_pending: dict[tuple[int, int], asyncio.Future[str]] = {}

TIMEOUT_SECONDS = 300  # 5 minutes per question


async def run_questionnaire(
    questionnaire: Questionnaire,
    chat_id: int | None = None,
) -> dict[str, str]:
    """Run a questionnaire via Telegram, collecting answers sequentially.

    Args:
        questionnaire: The questionnaire to run.
        chat_id: Target chat. Defaults to admin chat from settings.

    Returns:
        Dict mapping field_name -> answer string.
    """
    target_chat = chat_id or settings.telegram_admin_chat_id
    bot = get_bot()
    answers: dict[str, str] = {}

    await bot.send_message(chat_id=target_chat, text=f"📋 *{questionnaire.title}*", parse_mode="Markdown")

    for question in questionnaire.questions:
        answer = await _ask_question(bot, target_chat, question)
        answers[question.field_name] = answer

    await bot.send_message(chat_id=target_chat, text="✅ Questionnaire complete. Data recorded.")
    return answers


async def _ask_question(bot: Bot, chat_id: int, question: Question) -> str:
    """Ask a single question and wait for the response."""
    if question.question_type == QuestionType.SELECTION:
        return await _ask_selection(bot, chat_id, question)
    return await _ask_text(bot, chat_id, question)


async def _ask_text(bot: Bot, chat_id: int, question: Question) -> str:
    """Ask a free-text/numeric/time question and wait for reply."""
    prompt = question.text
    if question.question_type == QuestionType.NUMERIC:
        prompt += " (number)"
    elif question.question_type == QuestionType.TIME:
        prompt += " (HH:MM)"
    if question.default:
        prompt += f"\nDefault: {question.default}"

    await bot.send_message(chat_id=chat_id, text=prompt)

    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()
    _text_pending[chat_id] = future

    try:
        answer = await asyncio.wait_for(future, timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        answer = question.default
        await bot.send_message(chat_id=chat_id, text=f"⏳ Timed out — using default: {answer or '(empty)'}")
    finally:
        _text_pending.pop(chat_id, None)

    if question.question_type == QuestionType.NUMERIC:
        # Validate numeric input
        try:
            float(answer)
        except ValueError:
            await bot.send_message(chat_id=chat_id, text=f"⚠️ Expected a number, got '{answer}'. Using as-is.")

    return answer


async def _ask_selection(bot: Bot, chat_id: int, question: Question) -> str:
    """Ask a selection question with inline keyboard buttons."""
    buttons = [[InlineKeyboardButton(opt, callback_data=f"q:{question.field_name}:{opt}")] for opt in question.options]
    keyboard = InlineKeyboardMarkup(buttons)
    msg = await bot.send_message(chat_id=chat_id, text=question.text, reply_markup=keyboard)

    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()
    _selection_pending[(chat_id, msg.message_id)] = future

    try:
        answer = await asyncio.wait_for(future, timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        answer = question.default or question.options[0] if question.options else ""
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text=f"{question.text}\n\n⏳ Timed out — selected: {answer}",
        )
    finally:
        _selection_pending.pop((chat_id, msg.message_id), None)

    return answer


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages for pending questionnaire questions."""
    message = update.message
    if message is None or message.text is None:
        return
    chat_id = message.chat_id
    future = _text_pending.get(chat_id)
    if future is not None and not future.done():
        future.set_result(message.text)


async def handle_questionnaire_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard selections for questionnaire questions."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if not query.data.startswith("q:"):
        return
    await query.answer()

    message = query.message
    if message is None or not hasattr(message, "chat_id"):
        return

    chat_id: int = message.chat_id
    msg_id: int = message.message_id
    # Parse "q:field_name:selected_value"
    parts = query.data.split(":", 2)
    if len(parts) < 3:
        return
    selected = parts[2]

    future = _selection_pending.get((chat_id, msg_id))
    if future is not None and not future.done():
        future.set_result(selected)
        await get_bot().edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=f"Selected: {selected}",
        )


def register_questionnaire_handlers(app: Any) -> None:
    """Register questionnaire message and callback handlers on Telegram Application."""
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(handle_questionnaire_callback, pattern=r"^q:"))
