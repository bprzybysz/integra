"""FastAPI entrypoint with Telegram bot lifespan."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
from telegram.ext import Application, ApplicationBuilder

from integra.core.config import settings
from integra.core.orchestrator import run_conversation
from integra.core.registry import register_handler
from integra.data.cc_history import analyze_cc_productivity, ingest_cc_history
from integra.data.collectors import (
    collect_supplement_stack,
    log_drug_intake,
    log_meal,
    query_health_data,
)
from integra.integrations import telegram
from integra.integrations.questionnaire import register_questionnaire_handlers
from integra.integrations.scheduler import Scheduler

logger = logging.getLogger(__name__)

# Application has 6 generic type params; using Any here is justified by telegram's own types
_tg_app: Application[Any, Any, Any, Any, Any, Any] | None = None
_scheduler: Scheduler | None = None


def _register_tool_handlers() -> None:
    """Wire real handler implementations into the tool registry."""
    register_handler("ask_user_confirmation", telegram.ask_confirmation_handler)
    register_handler("notify_user", telegram.notify_handler)
    register_handler("collect_supplement_stack", collect_supplement_stack)
    register_handler("log_drug_intake", log_drug_intake)
    register_handler("log_meal", log_meal)
    register_handler("query_health_data", query_health_data)
    register_handler("ingest_cc_history", ingest_cc_history)
    register_handler("analyze_cc_productivity", analyze_cc_productivity)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and stop the Telegram bot and scheduler alongside the FastAPI server."""
    global _tg_app, _scheduler  # noqa: PLW0603

    _register_tool_handlers()

    if settings.telegram_bot_token:
        _tg_app = ApplicationBuilder().token(settings.telegram_bot_token).build()
        telegram.register_handlers(_tg_app)
        register_questionnaire_handlers(_tg_app)
        await _tg_app.initialize()
        await _tg_app.start()
        if _tg_app.updater is not None:
            await _tg_app.updater.start_polling()
        logger.info("Telegram bot started")

        if settings.schedule_enabled:
            _scheduler = Scheduler()
            await _scheduler.start()
            logger.info("Scheduler started")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram HIL disabled")

    yield

    if _scheduler is not None:
        await _scheduler.stop()
        logger.info("Scheduler stopped")

    if _tg_app is not None:
        if _tg_app.updater is not None:
            await _tg_app.updater.stop()
        await _tg_app.stop()
        await _tg_app.shutdown()
        logger.info("Telegram bot stopped")


app = FastAPI(title="Integra", version="0.1.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    """Body for the /chat endpoint."""

    message: str


class ChatResponse(BaseModel):
    """Response for the /chat endpoint."""

    response: str


class HealthResponse(BaseModel):
    """Response for the /health endpoint."""

    status: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """Run a single-turn conversation through the orchestrator."""
    result = await run_conversation(
        user_message=body.message,
        confirm_fn=_confirm_via_telegram,
    )
    return ChatResponse(response=result)


async def _confirm_via_telegram(tool_name: str, input_data: dict[str, object]) -> str:
    """HIL confirmation callback that delegates to Telegram."""
    description = f"Tool **{tool_name}** wants to run with:\n```\n{input_data}\n```"
    return await telegram.ask_confirmation(description)
