"""Tests for integra.app FastAPI endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from integra.app import app


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_chat_returns_response() -> None:
    with patch("integra.app.run_conversation", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "Hello from Claude"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/chat", json={"message": "Hi"})
    assert resp.status_code == 200
    assert resp.json() == {"response": "Hello from Claude"}
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_missing_message() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/chat", json={})
    assert resp.status_code == 422
