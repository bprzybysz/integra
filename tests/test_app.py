"""Tests for integra.app FastAPI endpoints."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from integra.app import _register_tool_handlers, app
from integra.core.registry import TOOL_REGISTRY


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_chat_returns_response() -> None:
    with (
        patch("integra.app.settings") as mock_settings,
        patch("integra.app.run_conversation", new_callable=AsyncMock) as mock_run,
    ):
        mock_settings.chat_api_key = "test-key"
        mock_run.return_value = "Hello from Claude"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={"message": "Hi"},
                headers={"Authorization": "Bearer test-key"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"response": "Hello from Claude"}
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_missing_message() -> None:
    with patch("integra.app.settings") as mock_settings:
        mock_settings.chat_api_key = "test-key"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={},
                headers={"Authorization": "Bearer test-key"},
            )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Issue #30: App lifespan tests
# ---------------------------------------------------------------------------


# Issue #30 — test 1: _register_tool_handlers wires expected tool names
def test_register_tool_handlers_wires_all_tools() -> None:
    """_register_tool_handlers() should wire handlers for all 9 expected tool names."""
    expected_tools = {
        "ask_user_confirmation",
        "notify_user",
        "collect_supplement_stack",
        "log_drug_intake",
        "log_meal",
        "query_health_data",
        "ingest_cc_history",
        "analyze_cc_productivity",
        "collect_diary",
    }

    # Mock out the real handlers so we don't need real dependencies
    mock_handler: AsyncMock = AsyncMock(return_value="ok")

    with (
        patch("integra.app._ask_confirmation_handler", mock_handler),
        patch("integra.app._notify_handler", mock_handler),
        patch("integra.app.collect_supplement_stack", mock_handler),
        patch("integra.app.log_drug_intake", mock_handler),
        patch("integra.app.log_meal", mock_handler),
        patch("integra.app.query_health_data", mock_handler),
        patch("integra.app.ingest_cc_history", mock_handler),
        patch("integra.app.analyze_cc_productivity", mock_handler),
        patch("integra.app.collect_diary", mock_handler),
    ):
        _register_tool_handlers()

    # All expected names must be in TOOL_REGISTRY (they were registered)
    registered = set(TOOL_REGISTRY.keys())
    assert expected_tools.issubset(registered)


# Issue #30 — test 2: lifespan with no bot token → provider not created, app still starts
@pytest.mark.asyncio
async def test_lifespan_no_bot_token_app_starts(caplog: pytest.LogCaptureFixture) -> None:
    """When TELEGRAM_BOT_TOKEN is falsy, provider is not created, warning logged."""
    dummy_app = FastAPI()

    with (
        patch("integra.app.settings") as mock_settings,
        patch("integra.app.TelegramProvider") as mock_provider_cls,
        patch("integra.app.Scheduler") as mock_scheduler_cls,
        patch("integra.app._register_tool_handlers"),
    ):
        mock_settings.telegram_bot_token = ""  # falsy → skip provider
        mock_settings.schedule_enabled = False
        mock_settings.chat_api_key = "test-key"

        from integra.app import lifespan

        with caplog.at_level(logging.WARNING, logger="integra.app"):
            async with lifespan(dummy_app):
                pass  # app starts and yields without raising

    # Provider must NOT have been instantiated
    mock_provider_cls.assert_not_called()
    # Scheduler must NOT have been instantiated
    mock_scheduler_cls.assert_not_called()
    # Warning about missing token must appear
    assert any("TELEGRAM_BOT_TOKEN" in rec.message for rec in caplog.records)


# Issue #30 — test 3: lifespan with schedule_enabled=False → scheduler not started
@pytest.mark.asyncio
async def test_lifespan_schedule_disabled_scheduler_not_started() -> None:
    """When schedule_enabled=False, Scheduler.start() is not called."""
    dummy_app = FastAPI()

    mock_provider = AsyncMock()
    mock_provider.bot = MagicMock()
    mock_provider.admin_chat_id = 123
    mock_provider.app = None  # skip handler registration branch
    mock_scheduler = AsyncMock()

    with (
        patch("integra.app.settings") as mock_settings,
        patch("integra.app.TelegramProvider", return_value=mock_provider),
        patch("integra.app.Scheduler", return_value=mock_scheduler) as mock_scheduler_cls,
        patch("integra.app.TelegramQuestionnaireUI"),
        patch("integra.app.ChannelRouter"),
        patch("integra.app._register_tool_handlers"),
        patch("integra.app.register_command_handlers"),
        patch("integra.app.set_diary_callback"),
        patch("integra.app.set_interrupt_callback"),
        # set_questionnaire_ui and set_advisor_router are imported inside lifespan
        # from integra.integrations.scheduler — patch there, not on integra.app
        patch("integra.integrations.scheduler.set_questionnaire_ui"),
        patch("integra.integrations.scheduler.set_advisor_router"),
    ):
        mock_settings.telegram_bot_token = "fake-token"
        mock_settings.schedule_enabled = False  # scheduler should NOT start
        mock_settings.chat_api_key = "key"

        from integra.app import lifespan

        async with lifespan(dummy_app):
            pass

    # Scheduler class should never have been instantiated
    mock_scheduler_cls.assert_not_called()
