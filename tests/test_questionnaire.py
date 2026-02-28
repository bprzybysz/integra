"""Tests for integra.integrations.questionnaire."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integra.integrations.questionnaire import (
    Question,
    Questionnaire,
    QuestionType,
    _selection_pending,
    _text_pending,
    handle_questionnaire_callback,
    handle_text_message,
    run_questionnaire,
)


@pytest.fixture(autouse=True)
def _clear_pending() -> None:
    _text_pending.clear()
    _selection_pending.clear()


def _make_bot_mock() -> AsyncMock:
    bot = AsyncMock()
    msg = MagicMock()
    msg.message_id = 42
    bot.send_message = AsyncMock(return_value=msg)
    bot.edit_message_text = AsyncMock()
    return bot


class TestRunQuestionnaire:
    @patch("integra.integrations.questionnaire.get_bot")
    async def test_collects_text_answers(self, mock_get_bot: MagicMock) -> None:
        bot = _make_bot_mock()
        mock_get_bot.return_value = bot

        q = Questionnaire(
            title="Test",
            questions=[Question(text="Name?", field_name="name")],
        )

        async def _provide_answer() -> None:
            # Wait for the future to be registered
            for _ in range(50):
                if 123 in _text_pending:
                    _text_pending[123].set_result("John")
                    return
                await asyncio.sleep(0.01)

        task = asyncio.create_task(_provide_answer())
        answers = await run_questionnaire(q, chat_id=123)
        await task
        assert answers["name"] == "John"

    @patch("integra.integrations.questionnaire.get_bot")
    async def test_selection_question(self, mock_get_bot: MagicMock) -> None:
        bot = _make_bot_mock()
        mock_get_bot.return_value = bot

        q = Questionnaire(
            title="Test",
            questions=[
                Question(
                    text="Category?",
                    field_name="cat",
                    question_type=QuestionType.SELECTION,
                    options=["supplement", "medication"],
                ),
            ],
        )

        async def _provide_answer() -> None:
            for _ in range(50):
                key = (123, 42)
                if key in _selection_pending:
                    _selection_pending[key].set_result("supplement")
                    return
                await asyncio.sleep(0.01)

        task = asyncio.create_task(_provide_answer())
        answers = await run_questionnaire(q, chat_id=123)
        await task
        assert answers["cat"] == "supplement"

    @patch("integra.integrations.questionnaire.get_bot")
    async def test_timeout_uses_default(self, mock_get_bot: MagicMock) -> None:
        bot = _make_bot_mock()
        mock_get_bot.return_value = bot

        q = Questionnaire(
            title="Test",
            questions=[
                Question(text="Dose?", field_name="dose", default="100"),
            ],
        )

        # Patch timeout to be very short
        with patch("integra.integrations.questionnaire.TIMEOUT_SECONDS", 0.05):
            answers = await run_questionnaire(q, chat_id=123)

        assert answers["dose"] == "100"


class TestHandleTextMessage:
    async def test_resolves_pending_future(self) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        _text_pending[999] = future

        update = MagicMock()
        update.message.chat_id = 999
        update.message.text = "hello"

        await handle_text_message(update, MagicMock())
        assert future.result() == "hello"

    async def test_ignores_unknown_chat(self) -> None:
        update = MagicMock()
        update.message.chat_id = 999
        update.message.text = "hello"
        # No pending future — should not raise
        await handle_text_message(update, MagicMock())


class TestHandleQuestionnaireCallback:
    async def test_resolves_selection(self) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        _selection_pending[(100, 42)] = future

        update = MagicMock()
        update.callback_query.data = "q:field:supplement"
        update.callback_query.message.chat_id = 100
        update.callback_query.message.message_id = 42
        update.callback_query.answer = AsyncMock()

        with patch("integra.integrations.questionnaire.get_bot") as mock_get_bot:
            mock_get_bot.return_value = AsyncMock()
            await handle_questionnaire_callback(update, MagicMock())

        assert future.result() == "supplement"

    async def test_ignores_non_questionnaire_callback(self) -> None:
        update = MagicMock()
        update.callback_query.data = "approve"
        # Should return without error
        await handle_questionnaire_callback(update, MagicMock())
