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
from integra.integrations import telegram

logger = logging.getLogger(__name__)

# Application has 6 generic type params; using Any here is justified by telegram's own types
_tg_app: Application[Any, Any, Any, Any, Any, Any] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and stop the Telegram bot alongside the FastAPI server."""
    global _tg_app  # noqa: PLW0603

    if settings.telegram_bot_token:
        _tg_app = ApplicationBuilder().token(settings.telegram_bot_token).build()
        telegram.register_handlers(_tg_app)
        await _tg_app.initialize()
        await _tg_app.start()
        if _tg_app.updater is not None:
            await _tg_app.updater.start_polling()
        logger.info("Telegram bot started")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram HIL disabled")

    yield

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
