"""FastAPI entrypoint with Telegram bot lifespan."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from integra.core.config import settings
from integra.core.orchestrator import run_conversation
from integra.core.registry import register_handler
from integra.data.cc_history import analyze_cc_productivity, ingest_cc_history
from integra.data.collectors import (
    collect_diary,
    collect_supplement_stack,
    log_drug_intake,
    log_meal,
    query_health_data,
)
from integra.integrations.channels import ChannelRouter, TelegramProvider
from integra.integrations.channels.telegram import (
    register_command_handlers,
    set_admin_bot,
    set_diary_callback,
    set_interrupt_callback,
    set_requester_ids,
)
from integra.integrations.projects import GitHubProvider, ProjectRouter
from integra.integrations.questionnaire import run_questionnaire
from integra.integrations.scheduler import Scheduler
from integra.integrations.telegram_questionnaire_ui import TelegramQuestionnaireUI

logger = logging.getLogger(__name__)

_provider: TelegramProvider | None = None
_router: ChannelRouter | None = None
_scheduler: Scheduler | None = None
_questionnaire_ui: TelegramQuestionnaireUI | None = None
_project_router: ProjectRouter | None = None


async def _ask_confirmation_handler(**kwargs: object) -> str:
    """Tool handler wrapper for ask_confirmation via channel router."""
    question = str(kwargs.get("question", ""))
    if _router is None:
        return "DENIED (no communication provider available)"
    return await _router.ask_confirmation(question)


async def _notify_handler(**kwargs: object) -> str:
    """Tool handler wrapper for notify via channel router."""
    message = str(kwargs.get("message", ""))
    if _router is None:
        return "No communication provider available"
    return await _router.notify(message)


def _register_tool_handlers() -> None:
    """Wire real handler implementations into the tool registry."""
    register_handler("ask_user_confirmation", _ask_confirmation_handler)
    register_handler("notify_user", _notify_handler)
    register_handler("collect_supplement_stack", collect_supplement_stack)
    register_handler("log_drug_intake", log_drug_intake)
    register_handler("log_meal", log_meal)
    register_handler("query_health_data", query_health_data)
    register_handler("ingest_cc_history", ingest_cc_history)
    register_handler("analyze_cc_productivity", analyze_cc_productivity)
    register_handler("collect_diary", collect_diary)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and stop the Telegram bot and scheduler alongside the FastAPI server."""
    global _provider, _router, _scheduler, _questionnaire_ui, _project_router  # noqa: PLW0603

    _register_tool_handlers()

    # Wire ProjectRouter
    if settings.github_repo:
        _project_router = ProjectRouter()
        gh_provider = GitHubProvider(repo=settings.github_repo)
        await gh_provider.initialize()
        _project_router.register(gh_provider)

    if settings.telegram_bot_token:
        _provider = TelegramProvider()
        await _provider.initialize()

        _questionnaire_ui = TelegramQuestionnaireUI(
            bot=_provider.bot,
            admin_chat_id=_provider.admin_chat_id,
        )

        # Register questionnaire handlers on the provider's Application
        if _provider.app is not None:
            _questionnaire_ui.register_handlers(_provider.app)
            register_command_handlers(_provider.app)

        _router = ChannelRouter()
        _router.register(_provider)

        # Wire requester-tier user IDs
        set_requester_ids(set(settings.telegram_requester_ids))
        set_admin_bot(_provider.bot)

        logger.info("Telegram bot started via TelegramProvider")

        # Wire diary + task interrupt commands (work even without scheduler)
        from integra.integrations.scheduler import (
            ON_DEMAND_DIARY,
            _process_answers,
            set_advisor_router,
            set_questionnaire_ui,
        )

        set_questionnaire_ui(_questionnaire_ui)
        set_advisor_router(_router)

        async def _diary_entry_callback() -> None:
            if _questionnaire_ui is None:
                return
            if _scheduler is not None:
                await _scheduler.interrupt_current()
            answers = await run_questionnaire(ON_DEMAND_DIARY, ui=_questionnaire_ui)
            await _process_answers("diary_entry", answers)

        async def _interrupt_task_callback(task_name: str) -> None:
            if _scheduler is None:
                if _router is not None:
                    await _router.notify("Scheduler not running.")
                return
            await _scheduler.interrupt_current()
            if _router is not None:
                await _router.notify(f"Starting: {task_name}")
            result = await _scheduler.trigger_now(task_name)
            if result is None and _router is not None:
                await _router.notify(f"Unknown task: {task_name}")

        set_diary_callback(_diary_entry_callback)
        set_interrupt_callback(_interrupt_task_callback)

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

    if _provider is not None:
        await _provider.shutdown()


app = FastAPI(title="Integra", version="0.1.0", lifespan=lifespan)

_bearer_scheme = HTTPBearer()


class ChatRequest(BaseModel):
    """Body for the /chat endpoint."""

    message: str


class ChatResponse(BaseModel):
    """Response for the /chat endpoint."""

    response: str


class HealthResponse(BaseModel):
    """Response for the /health endpoint."""

    status: str


async def _verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),  # noqa: B008
) -> str:
    """Validate the Bearer token against the configured chat_api_key."""
    if not settings.chat_api_key or credentials.credentials != settings.chat_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return credentials.credentials


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    _key: str = Depends(_verify_api_key),
) -> ChatResponse:
    """Run a single-turn conversation through the orchestrator. Requires Bearer auth."""
    result = await run_conversation(
        user_message=body.message,
        confirm_fn=_confirm_via_channels,
    )
    return ChatResponse(response=result)


async def _confirm_via_channels(tool_name: str, input_data: dict[str, object]) -> str:
    """HIL confirmation callback that delegates to the channel router."""
    if _router is None:
        return "DENIED (no communication provider)"
    description = f"Tool **{tool_name}** wants to run with:\n```\n{input_data}\n```"
    return await _router.ask_confirmation(description)
