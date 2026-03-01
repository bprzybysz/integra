"""Tests for integra.integrations.projects.github.GitHubProvider."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from integra.integrations.projects.base import IssueState
from integra.integrations.projects.github import GitHubProvider, _parse_issue

SAMPLE_ISSUE = {
    "number": 49,
    "title": "feat: cinema scraper",
    "body": "Implement cinema.py",
    "state": "OPEN",
    "labels": [{"name": "type:feature", "color": "0075ca", "description": ""}],
    "assignees": [],
    "url": "https://github.com/owner/repo/issues/49",
}

SAMPLE_CLOSED = {**SAMPLE_ISSUE, "number": 49, "state": "CLOSED"}


class TestParseIssue:
    def test_open_state(self) -> None:
        issue = _parse_issue(SAMPLE_ISSUE, "owner/repo")
        assert issue.state == IssueState.OPEN
        assert issue.ref.issue_id == "#49"
        assert issue.ref.provider == "github"
        assert len(issue.labels) == 1
        assert issue.labels[0].name == "type:feature"

    def test_closed_state(self) -> None:
        issue = _parse_issue(SAMPLE_CLOSED, "owner/repo")
        assert issue.state == IssueState.CLOSED

    def test_lowercase_state(self) -> None:
        data = {**SAMPLE_ISSUE, "state": "open"}
        issue = _parse_issue(data, "owner/repo")
        assert issue.state == IssueState.OPEN

    def test_assignee_parsed(self) -> None:
        data = {**SAMPLE_ISSUE, "assignees": [{"login": "blaisem4"}]}
        issue = _parse_issue(data, "owner/repo")
        assert issue.assignee == "blaisem4"

    def test_no_assignee(self) -> None:
        issue = _parse_issue(SAMPLE_ISSUE, "owner/repo")
        assert issue.assignee is None


class TestGitHubProviderInit:
    def test_name(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        assert p.name == "github"

    def test_capabilities_full(self) -> None:
        from integra.integrations.projects.base import ProjectCapability

        p = GitHubProvider()
        assert len(p.capabilities) == len(ProjectCapability)

    @pytest.mark.asyncio
    async def test_initialize_no_gh(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        with patch("integra.integrations.projects.github.shutil.which", return_value=None):
            await p.initialize()
        assert not p._available


class TestGitHubProviderCreate:
    @pytest.mark.asyncio
    async def test_create_issue_success(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        with patch(
            "integra.integrations.projects.github._run_gh",
            new=AsyncMock(return_value=(0, json.dumps(SAMPLE_ISSUE), "")),
        ):
            issue = await p.create_issue("feat: cinema scraper", "Body")
        assert issue.title == "feat: cinema scraper"
        assert issue.state == IssueState.OPEN

    @pytest.mark.asyncio
    async def test_create_issue_with_labels(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        captured: list[tuple[str, ...]] = []

        async def mock_run(*args: str) -> tuple[int, str, str]:
            captured.append(args)
            return 0, json.dumps(SAMPLE_ISSUE), ""

        with patch("integra.integrations.projects.github._run_gh", new=mock_run):
            await p.create_issue("T", "B", labels=["type:feature", "stage-2"])

        assert "type:feature" in captured[0]
        assert "stage-2" in captured[0]

    @pytest.mark.asyncio
    async def test_create_issue_failure(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        with (
            patch(
                "integra.integrations.projects.github._run_gh",
                new=AsyncMock(return_value=(1, "", "error: repo not found")),
            ),
            pytest.raises(RuntimeError, match="repo not found"),
        ):
            await p.create_issue("T", "B")


class TestGitHubProviderClose:
    @pytest.mark.asyncio
    async def test_close_issue(self) -> None:
        p = GitHubProvider(repo="owner/repo")

        async def mock_run(*args: str) -> tuple[int, str, str]:
            if "close" in args:
                return 0, "", ""
            return 0, json.dumps(SAMPLE_CLOSED), ""

        with patch("integra.integrations.projects.github._run_gh", new=mock_run):
            issue = await p.close_issue("#49")
        assert issue.state == IssueState.CLOSED

    @pytest.mark.asyncio
    async def test_close_issue_failure(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        with (
            patch(
                "integra.integrations.projects.github._run_gh",
                new=AsyncMock(return_value=(1, "", "not found")),
            ),
            pytest.raises(RuntimeError, match="not found"),
        ):
            await p.close_issue("#99")


class TestGitHubProviderList:
    @pytest.mark.asyncio
    async def test_list_issues(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        with patch(
            "integra.integrations.projects.github._run_gh",
            new=AsyncMock(return_value=(0, json.dumps([SAMPLE_ISSUE]), "")),
        ):
            issues = await p.list_issues()
        assert len(issues) == 1
        assert issues[0].ref.issue_id == "#49"

    @pytest.mark.asyncio
    async def test_list_issues_closed(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        captured: list[tuple[str, ...]] = []

        async def mock_run(*args: str) -> tuple[int, str, str]:
            captured.append(args)
            return 0, json.dumps([]), ""

        with patch("integra.integrations.projects.github._run_gh", new=mock_run):
            await p.list_issues(state=IssueState.CLOSED)

        assert "closed" in captured[0]


class TestGitHubProviderComment:
    @pytest.mark.asyncio
    async def test_add_comment(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        with patch(
            "integra.integrations.projects.github._run_gh",
            new=AsyncMock(return_value=(0, "", "")),
        ):
            await p.add_comment("#49", "Implementation complete")

    @pytest.mark.asyncio
    async def test_add_comment_failure(self) -> None:
        p = GitHubProvider(repo="owner/repo")
        with (
            patch(
                "integra.integrations.projects.github._run_gh",
                new=AsyncMock(return_value=(1, "", "auth error")),
            ),
            pytest.raises(RuntimeError, match="auth error"),
        ):
            await p.add_comment("#1", "oops")
