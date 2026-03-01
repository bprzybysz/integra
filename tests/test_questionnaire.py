"""Tests for integra.integrations.questionnaire and TelegramQuestionnaireUI."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from integra.integrations.questionnaire import (
    Question,
    Questionnaire,
    QuestionType,
    run_questionnaire,
)
from integra.integrations.telegram_questionnaire_ui import (
    TelegramQuestionnaireUI,
)


def _make_bot_mock() -> AsyncMock:
    bot = AsyncMock()
    msg = MagicMock()
    msg.message_id = 42
    bot.send_message = AsyncMock(return_value=msg)
    bot.edit_message_text = AsyncMock()
    return bot


def _make_ui(bot: AsyncMock | None = None, admin_chat_id: int = 123) -> TelegramQuestionnaireUI:
    return TelegramQuestionnaireUI(bot=bot or _make_bot_mock(), admin_chat_id=admin_chat_id)


# ---- run_questionnaire with mock UI ----


class TestRunQuestionnaire:
    async def test_collects_text_answers(self) -> None:
        ui = AsyncMock()
        ui.send_status = AsyncMock()
        ui.ask_text = AsyncMock(return_value="John")
        ui.ask_selection = AsyncMock()

        q = Questionnaire(
            title="Test",
            questions=[Question(text="Name?", field_name="name")],
        )
        answers = await run_questionnaire(q, ui=ui)
        assert answers["name"] == "John"
        ui.ask_text.assert_awaited_once()

    async def test_selection_question_dispatches_ask_selection(self) -> None:
        ui = AsyncMock()
        ui.send_status = AsyncMock()
        ui.ask_selection = AsyncMock(return_value="supplement")
        ui.ask_text = AsyncMock()

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
        answers = await run_questionnaire(q, ui=ui)
        assert answers["cat"] == "supplement"
        ui.ask_selection.assert_awaited_once()
        ui.ask_text.assert_not_awaited()

    async def test_send_status_called_twice(self) -> None:
        ui = AsyncMock()
        ui.send_status = AsyncMock()
        ui.ask_text = AsyncMock(return_value="x")

        q = Questionnaire(title="T", questions=[Question(text="Q?", field_name="q")])
        await run_questionnaire(q, ui=ui)
        assert ui.send_status.await_count == 2


# ---- TelegramQuestionnaireUI.ask_text ----


class TestTelegramUIAskText:
    async def test_resolves_on_future_set(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=123)

        async def _provide() -> None:
            for _ in range(50):
                if 123 in ui._text_pending:
                    ui._text_pending[123].set_result("hello")
                    return
                await asyncio.sleep(0.01)

        q = Question(text="Hi?", field_name="greeting")
        task = asyncio.create_task(_provide())
        answer = await ui.ask_text(q)
        await task
        assert answer == "hello"

    async def test_timeout_uses_default(self) -> None:
        from unittest.mock import patch

        bot = _make_bot_mock()
        ui = _make_ui(bot)

        q = Question(text="Dose?", field_name="dose", default="100")
        with patch(
            "integra.integrations.telegram_questionnaire_ui.TIMEOUT_SECONDS",
            0.05,
        ):
            answer = await ui.ask_text(q)
        assert answer == "100"

    async def test_clears_pending_after_answer(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=55)

        async def _provide() -> None:
            for _ in range(50):
                if 55 in ui._text_pending:
                    ui._text_pending[55].set_result("done")
                    return
                await asyncio.sleep(0.01)

        task = asyncio.create_task(_provide())
        await ui.ask_text(Question(text="?", field_name="f"))
        await task
        assert 55 not in ui._text_pending


# ---- TelegramQuestionnaireUI.ask_selection ----


class TestTelegramUIAskSelection:
    async def test_resolves_on_future_set(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=100)

        async def _provide() -> None:
            for _ in range(50):
                key = (100, 42)
                if key in ui._selection_pending:
                    ui._selection_pending[key].set_result("supplement")
                    return
                await asyncio.sleep(0.01)

        q = Question(
            text="Cat?",
            field_name="cat",
            question_type=QuestionType.SELECTION,
            options=["supplement", "medication"],
        )
        task = asyncio.create_task(_provide())
        answer = await ui.ask_selection(q)
        await task
        assert answer == "supplement"


# ---- handle_text_message security ----


class TestHandleTextMessage:
    async def test_resolves_pending_future(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=999)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        ui._text_pending[999] = future

        update = MagicMock()
        update.message.chat_id = 999
        update.message.text = "hello"
        update.message.from_user = MagicMock()
        update.message.from_user.id = 999

        await ui.handle_text_message(update, MagicMock())
        assert future.result() == "hello"

    async def test_unauthorized_user_ignored(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=999)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        ui._text_pending[999] = future

        update = MagicMock()
        update.message.chat_id = 999
        update.message.text = "hello"
        update.message.from_user = MagicMock()
        update.message.from_user.id = 777  # wrong user

        await ui.handle_text_message(update, MagicMock())
        assert not future.done()

    async def test_ignores_unknown_chat(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=999)

        update = MagicMock()
        update.message.chat_id = 999
        update.message.text = "hello"
        update.message.from_user = MagicMock()
        update.message.from_user.id = 999
        # No pending future — should not raise
        await ui.handle_text_message(update, MagicMock())


# ---- handle_questionnaire_callback security ----


class TestHandleQuestionnaireCallback:
    async def test_resolves_selection(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=100)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        ui._selection_pending[(100, 42)] = future

        update = MagicMock()
        update.callback_query.data = "q:field:supplement"
        update.callback_query.from_user = MagicMock()
        update.callback_query.from_user.id = 100
        update.callback_query.message.chat_id = 100
        update.callback_query.message.message_id = 42
        update.callback_query.answer = AsyncMock()

        await ui.handle_questionnaire_callback(update, MagicMock())
        assert future.result() == "supplement"

    async def test_unauthorized_callback_rejected(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=100)

        query = AsyncMock()
        query.data = "q:field:value"
        query.from_user = MagicMock()
        query.from_user.id = 777  # wrong user
        query.message = MagicMock()

        update = MagicMock()
        update.callback_query = query

        await ui.handle_questionnaire_callback(update, MagicMock())
        query.answer.assert_awaited_once_with(text="Unauthorized.", show_alert=True)

    async def test_ignores_non_questionnaire_callback(self) -> None:
        bot = _make_bot_mock()
        ui = _make_ui(bot, admin_chat_id=100)

        update = MagicMock()
        update.callback_query.data = "approve"
        update.callback_query.from_user = MagicMock()
        update.callback_query.from_user.id = 100
        # Should return without error (data doesn't start with "q:")
        await ui.handle_questionnaire_callback(update, MagicMock())
