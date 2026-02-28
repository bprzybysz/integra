"""Tests for integra.core.registry."""

from integra.core.registry import (
    TOOL_REGISTRY,
    dispatch_tool,
    get_tool_schemas,
)


class TestGetToolSchemas:
    def test_returns_all_schemas(self) -> None:
        schemas = get_tool_schemas()
        assert len(schemas) == len(TOOL_REGISTRY)

    def test_schema_has_required_fields(self) -> None:
        schemas = get_tool_schemas()
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema

    def test_schema_names_match_registry_keys(self) -> None:
        schemas = get_tool_schemas()
        schema_names = {s["name"] for s in schemas}
        assert schema_names == set(TOOL_REGISTRY.keys())


class TestDispatchTool:
    async def test_known_tool_executes(self) -> None:
        result = await dispatch_tool("notify_user", {"message": "hi"})
        # Placeholder handler returns a string
        assert isinstance(result, str)

    async def test_unknown_tool_returns_error(self) -> None:
        result = await dispatch_tool("nonexistent_tool", {})
        assert "Error" in result
        assert "unknown tool" in result

    async def test_requires_confirmation_calls_confirm_fn(self) -> None:
        # Temporarily set a tool to require confirmation
        original = TOOL_REGISTRY["notify_user"]["requires_confirmation"]
        TOOL_REGISTRY["notify_user"]["requires_confirmation"] = True
        try:
            called = False

            async def mock_confirm(name: str, data: dict[str, object]) -> str:
                nonlocal called
                called = True
                return "APPROVED"

            result = await dispatch_tool("notify_user", {"message": "hi"}, confirm_fn=mock_confirm)
            assert called
            assert isinstance(result, str)
        finally:
            TOOL_REGISTRY["notify_user"]["requires_confirmation"] = original

    async def test_confirmation_denied_blocks_execution(self) -> None:
        original = TOOL_REGISTRY["notify_user"]["requires_confirmation"]
        TOOL_REGISTRY["notify_user"]["requires_confirmation"] = True
        try:

            async def deny(_name: str, _data: dict[str, object]) -> str:
                return "DENIED"

            result = await dispatch_tool("notify_user", {"message": "hi"}, confirm_fn=deny)
            assert "denied" in result.lower()
        finally:
            TOOL_REGISTRY["notify_user"]["requires_confirmation"] = original

    async def test_confirmation_required_but_no_fn(self) -> None:
        original = TOOL_REGISTRY["notify_user"]["requires_confirmation"]
        TOOL_REGISTRY["notify_user"]["requires_confirmation"] = True
        try:
            result = await dispatch_tool("notify_user", {"message": "hi"})
            assert "Error" in result
        finally:
            TOOL_REGISTRY["notify_user"]["requires_confirmation"] = original
