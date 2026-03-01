"""Security-specific tests for G1-sec quality gate.

Tests cover all 7 security fixes:
1. telegram.py: handle_callback user auth
2. app.py: /chat Bearer auth
3. cc_history.py: zip path traversal + size limits
4. mcp_server.py: category path traversal validation
5. ingestion.py: file size limits
6. youtube.py: URL domain whitelist
7. questionnaire.py: sender auth checks
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pyrage.x25519
import pytest
from httpx import ASGITransport, AsyncClient

from integra.app import app
from integra.core.config import Settings
from integra.data.cc_history import _extract_from_archive, _is_safe_zip_path
from integra.data.ingestion import ingest_from_landing_zone
from integra.data.mcp_server import query_data
from integra.data.youtube import _validate_youtube_url
from integra.integrations.channels.telegram import TelegramProvider, _pending
from integra.integrations.telegram_questionnaire_ui import TelegramQuestionnaireUI

# --- Fixtures ---


@pytest.fixture
def age_keypair() -> tuple[str, str]:
    identity = pyrage.x25519.Identity.generate()
    return str(identity.to_public()), str(identity)


@pytest.fixture
def test_config(tmp_path: Path, age_keypair: tuple[str, str]) -> Settings:
    pub, priv = age_keypair
    return Settings(
        age_recipient=pub,
        age_identity=priv,
        data_raw_path=tmp_path / "raw",
        data_lake_path=tmp_path / "lake",
        data_audit_path=tmp_path / "audit",
    )


# --- 1. telegram.py: handle_callback user auth ---


class TestTelegramCallbackAuth:
    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        _pending.clear()

    @pytest.fixture()
    def provider(self) -> TelegramProvider:
        p = TelegramProvider(bot_token="fake", admin_chat_id=123456)
        p.set_bot(AsyncMock())
        return p

    async def test_unauthorized_user_rejected(self, provider: TelegramProvider) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        _pending[99] = future

        query = AsyncMock()
        query.data = "approve"
        query.from_user = MagicMock()
        query.from_user.id = 999999  # wrong user
        query.message = MagicMock()
        query.message.message_id = 99

        update = MagicMock()
        update.callback_query = query

        await provider._handle_callback(update, MagicMock())

        # Future should NOT be resolved
        assert not future.done()
        query.answer.assert_awaited_once_with(text="Unauthorized.", show_alert=True)

    async def test_authorized_user_approved(self, provider: TelegramProvider) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        _pending[99] = future

        query = AsyncMock()
        query.data = "approve"
        query.from_user = MagicMock()
        query.from_user.id = 123456
        query.message = MagicMock()
        query.message.message_id = 99

        update = MagicMock()
        update.callback_query = query

        await provider._handle_callback(update, MagicMock())

        assert future.done()
        assert future.result() is True

    async def test_no_from_user_rejected(self, provider: TelegramProvider) -> None:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        _pending[99] = future

        query = AsyncMock()
        query.data = "approve"
        query.from_user = None
        query.message = MagicMock()
        query.message.message_id = 99

        update = MagicMock()
        update.callback_query = query

        await provider._handle_callback(update, MagicMock())

        assert not future.done()


# --- 2. app.py: /chat Bearer auth ---


class TestChatEndpointAuth:
    async def test_chat_without_auth_rejected(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/chat", json={"message": "Hi"})
        # FastAPI HTTPBearer returns 403 when no header, but our custom handler returns 401
        assert resp.status_code in (401, 403)

    async def test_chat_with_wrong_key_rejected(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={"message": "Hi"},
                headers={"Authorization": "Bearer wrong-key"},
            )
        assert resp.status_code == 401

    async def test_chat_with_valid_key_accepted(self) -> None:
        with (
            patch("integra.app.settings") as mock_settings,
            patch("integra.app.run_conversation", new_callable=AsyncMock) as mock_run,
        ):
            mock_settings.chat_api_key = "test-secret-key"
            mock_run.return_value = "Hello"
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/chat",
                    json={"message": "Hi"},
                    headers={"Authorization": "Bearer test-secret-key"},
                )
        assert resp.status_code == 200

    async def test_health_no_auth_required(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200


# --- 3. cc_history.py: zip path traversal + size limits ---


class TestZipPathTraversal:
    def test_safe_path(self) -> None:
        assert _is_safe_zip_path("sessions/data.jsonl") is True

    def test_traversal_path_rejected(self) -> None:
        assert _is_safe_zip_path("../../etc/passwd") is False

    def test_absolute_path_rejected(self) -> None:
        assert _is_safe_zip_path("/etc/passwd") is False

    def test_dotdot_in_middle_rejected(self) -> None:
        assert _is_safe_zip_path("data/../../../etc/passwd") is False

    def test_traversal_members_skipped(self, tmp_path: Path) -> None:
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0")
            zf.writestr("legit.jsonl", '{"ok": true}\n')
        records = _extract_from_archive(archive)
        assert len(records) == 1
        assert records[0]["ok"] is True


# --- 4. mcp_server.py: category path traversal ---


class TestCategoryValidation:
    async def test_valid_category(self, test_config: Settings) -> None:
        result = await query_data("health", config=test_config)
        assert json.loads(result) == []  # empty but valid

    async def test_traversal_category_rejected(self, test_config: Settings) -> None:
        result = await query_data("../../etc", config=test_config)
        data = json.loads(result)
        assert "error" in data

    async def test_slash_category_rejected(self, test_config: Settings) -> None:
        result = await query_data("foo/bar", config=test_config)
        data = json.loads(result)
        assert "error" in data

    async def test_dotdot_category_rejected(self, test_config: Settings) -> None:
        result = await query_data("..", config=test_config)
        data = json.loads(result)
        assert "error" in data


# --- 5. ingestion.py: file size limits ---


class TestFileSizeLimits:
    async def test_oversized_file_rejected(self, test_config: Settings) -> None:
        raw = test_config.data_raw_path / "health"
        raw.mkdir(parents=True)
        big_file = raw / "huge.json"
        # Create a file just over limit using sparse/truncated approach
        big_file.write_text(json.dumps({"key": "x" * 100}))

        # Patch MAX_FILE_SIZE to a small value for testing
        with patch("integra.data.ingestion.MAX_FILE_SIZE", 10):
            result = await ingest_from_landing_zone(test_config)

        assert result.files_processed == 0
        assert len(result.errors) == 1
        assert "too large" in result.errors[0].lower()

    async def test_normal_file_accepted(self, test_config: Settings) -> None:
        raw = test_config.data_raw_path / "health"
        raw.mkdir(parents=True)
        (raw / "ok.json").write_text(json.dumps({"bp": 120}))

        result = await ingest_from_landing_zone(test_config)
        assert result.files_processed == 1


# --- 6. youtube.py: URL domain whitelist ---


class TestYoutubeUrlValidation:
    def test_valid_youtube_url(self) -> None:
        _validate_youtube_url("https://www.youtube.com/watch?v=abc123")

    def test_valid_youtu_be(self) -> None:
        _validate_youtube_url("https://youtu.be/abc123")

    def test_file_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            _validate_youtube_url("file:///etc/passwd")

    def test_non_youtube_domain_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid domain"):
            _validate_youtube_url("https://evil.com/watch?v=abc")

    def test_ftp_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            _validate_youtube_url("ftp://youtube.com/video")

    def test_mobile_youtube_allowed(self) -> None:
        _validate_youtube_url("https://m.youtube.com/watch?v=abc123")


# --- 7. questionnaire.py: sender auth (via TelegramQuestionnaireUI) ---


class TestQuestionnaireSenderAuth:
    def _make_ui(self, admin_chat_id: int = 123456) -> TelegramQuestionnaireUI:
        from unittest.mock import AsyncMock

        return TelegramQuestionnaireUI(bot=AsyncMock(), admin_chat_id=admin_chat_id)

    async def test_text_message_unauthorized_ignored(self) -> None:
        ui = self._make_ui(admin_chat_id=123456)
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

    async def test_text_message_authorized_accepted(self) -> None:
        ui = self._make_ui(admin_chat_id=123456)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        ui._text_pending[999] = future

        update = MagicMock()
        update.message.chat_id = 999
        update.message.text = "hello"
        update.message.from_user = MagicMock()
        update.message.from_user.id = 123456

        await ui.handle_text_message(update, MagicMock())

        assert future.done()
        assert future.result() == "hello"

    async def test_callback_unauthorized_rejected(self) -> None:
        ui = self._make_ui(admin_chat_id=123456)

        query = AsyncMock()
        query.data = "q:field:value"
        query.from_user = MagicMock()
        query.from_user.id = 777  # wrong user
        query.message = MagicMock()

        update = MagicMock()
        update.callback_query = query

        await ui.handle_questionnaire_callback(update, MagicMock())

        query.answer.assert_awaited_once_with(text="Unauthorized.", show_alert=True)
