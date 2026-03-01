"""Tests for integra.integrations.projects.router."""

from __future__ import annotations

import pytest

from integra.integrations.projects.base import Issue, IssueRef, IssueState, ProjectCapability, ProjectProvider
from integra.integrations.projects.router import ProjectRouter


class FakeProvider(ProjectProvider):
    def __init__(self, name: str = "fake") -> None:
        self._name = name
        self.created: list[tuple[str, str]] = []
        self.closed: list[str] = []
        self.comments: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> frozenset[ProjectCapability]:
        return frozenset(ProjectCapability)

    async def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> Issue:
        self.created.append((title, body))
        return Issue(ref=IssueRef(self._name, "#1"), title=title, body=body, state=IssueState.OPEN)

    async def close_issue(self, issue_id: str) -> Issue:
        self.closed.append(issue_id)
        return Issue(ref=IssueRef(self._name, issue_id), title="", body="", state=IssueState.CLOSED)

    async def update_issue(
        self, issue_id: str, title: str | None = None, body: str | None = None, labels: list[str] | None = None
    ) -> Issue:
        return Issue(ref=IssueRef(self._name, issue_id), title=title or "", body=body or "", state=IssueState.OPEN)

    async def list_issues(self, state: IssueState | None = None, label: str | None = None) -> list[Issue]:
        return []

    async def add_comment(self, issue_id: str, body: str) -> None:
        self.comments.append((issue_id, body))

    async def search_issues(self, query: str) -> list[Issue]:
        return []


class TestProjectRouter:
    def test_no_provider_raises(self) -> None:
        router = ProjectRouter()
        with pytest.raises(RuntimeError, match="No project provider"):
            _ = router.default

    def test_first_registered_is_default(self) -> None:
        router = ProjectRouter()
        p1 = FakeProvider("first")
        p2 = FakeProvider("second")
        router.register(p1)
        router.register(p2)
        assert router.default.name == "first"

    @pytest.mark.asyncio
    async def test_create_issue_delegates(self) -> None:
        router = ProjectRouter()
        p = FakeProvider()
        router.register(p)
        issue = await router.create_issue("Title", "Body")
        assert issue.title == "Title"
        assert p.created == [("Title", "Body")]

    @pytest.mark.asyncio
    async def test_close_issue_delegates(self) -> None:
        router = ProjectRouter()
        p = FakeProvider()
        router.register(p)
        issue = await router.close_issue("#42")
        assert issue.state == IssueState.CLOSED
        assert "#42" in p.closed

    @pytest.mark.asyncio
    async def test_add_comment_delegates(self) -> None:
        router = ProjectRouter()
        p = FakeProvider()
        router.register(p)
        await router.add_comment("#5", "Good work")
        assert p.comments == [("#5", "Good work")]

    @pytest.mark.asyncio
    async def test_list_issues_delegates(self) -> None:
        router = ProjectRouter()
        p = FakeProvider()
        router.register(p)
        result = await router.list_issues()
        assert result == []

    @pytest.mark.asyncio
    async def test_search_delegates(self) -> None:
        router = ProjectRouter()
        p = FakeProvider()
        router.register(p)
        result = await router.search_issues("bug")
        assert result == []
