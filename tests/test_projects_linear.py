"""Tests for integra.integrations.projects.linear.LinearProvider."""

from __future__ import annotations

import pytest

from integra.integrations.projects.base import IssueState
from integra.integrations.projects.linear import _LINEAR_STATE_MAP, LinearProvider


class TestLinearStateMap:
    def test_backlog_is_open(self) -> None:
        assert _LINEAR_STATE_MAP["Backlog"] == IssueState.OPEN

    def test_todo_is_open(self) -> None:
        assert _LINEAR_STATE_MAP["Todo"] == IssueState.OPEN

    def test_in_progress(self) -> None:
        assert _LINEAR_STATE_MAP["In Progress"] == IssueState.IN_PROGRESS

    def test_done_is_closed(self) -> None:
        assert _LINEAR_STATE_MAP["Done"] == IssueState.CLOSED

    def test_cancelled_is_closed(self) -> None:
        assert _LINEAR_STATE_MAP["Cancelled"] == IssueState.CLOSED


class TestLinearProvider:
    def test_instantiation(self) -> None:
        p = LinearProvider(team_id="abc", project_id="xyz")
        assert p.name == "linear"
        assert p._team_id == "abc"
        assert p._project_id == "xyz"

    def test_state_map_property(self) -> None:
        p = LinearProvider()
        sm = p.state_map
        assert sm["Backlog"] == IssueState.OPEN
        assert sm["In Progress"] == IssueState.IN_PROGRESS

    def test_capabilities_full(self) -> None:
        from integra.integrations.projects.base import ProjectCapability

        p = LinearProvider()
        assert len(p.capabilities) == len(ProjectCapability)

    @pytest.mark.asyncio
    async def test_create_issue_raises(self) -> None:
        p = LinearProvider()
        with pytest.raises(RuntimeError, match="MCP"):
            await p.create_issue("T", "B")

    @pytest.mark.asyncio
    async def test_close_issue_raises(self) -> None:
        p = LinearProvider()
        with pytest.raises(RuntimeError, match="MCP"):
            await p.close_issue("#1")

    @pytest.mark.asyncio
    async def test_list_issues_raises(self) -> None:
        p = LinearProvider()
        with pytest.raises(RuntimeError, match="MCP"):
            await p.list_issues()

    @pytest.mark.asyncio
    async def test_add_comment_raises(self) -> None:
        p = LinearProvider()
        with pytest.raises(RuntimeError, match="MCP"):
            await p.add_comment("#1", "hi")

    @pytest.mark.asyncio
    async def test_search_raises(self) -> None:
        p = LinearProvider()
        with pytest.raises(RuntimeError, match="MCP"):
            await p.search_issues("query")

    @pytest.mark.asyncio
    async def test_lifecycle_no_op(self) -> None:
        p = LinearProvider()
        await p.initialize()
        await p.shutdown()
