"""Tests for integra.integrations.projects.base."""

from __future__ import annotations

import pytest

from integra.integrations.projects.base import (
    Issue,
    IssueRef,
    IssueState,
    ProjectCapability,
    ProjectConfig,
    ProjectLabel,
    ProjectProvider,
)


class TestProjectCapability:
    def test_all_capabilities(self) -> None:
        names = {c.name for c in ProjectCapability}
        assert "CREATE_ISSUE" in names
        assert "UPDATE_ISSUE" in names
        assert "CLOSE_ISSUE" in names
        assert "LIST_ISSUES" in names
        assert "ADD_COMMENT" in names
        assert "SEARCH_ISSUES" in names
        assert "CREATE_LABEL" in names
        assert "LIST_LABELS" in names
        assert len(ProjectCapability) == 8


class TestIssueState:
    def test_all_states(self) -> None:
        assert IssueState.OPEN.value == "open"
        assert IssueState.IN_PROGRESS.value == "in_progress"
        assert IssueState.CLOSED.value == "closed"


class TestIssueRef:
    def test_fields(self) -> None:
        ref = IssueRef(provider="github", issue_id="#49", url="https://github.com/x/y/issues/49")
        assert ref.provider == "github"
        assert ref.issue_id == "#49"
        assert ref.url is not None

    def test_url_optional(self) -> None:
        ref = IssueRef(provider="linear", issue_id="LIN-42")
        assert ref.url is None


class TestProjectLabel:
    def test_required_only(self) -> None:
        lbl = ProjectLabel(name="bug")
        assert lbl.name == "bug"
        assert lbl.color is None
        assert lbl.description is None

    def test_full(self) -> None:
        lbl = ProjectLabel(name="stage-2", color="0075ca", description="Stage 2 work")
        assert lbl.color == "0075ca"


class TestIssue:
    def test_defaults(self) -> None:
        ref = IssueRef(provider="github", issue_id="#1")
        issue = Issue(ref=ref, title="Test", body="body", state=IssueState.OPEN)
        assert issue.labels == []
        assert issue.assignee is None


class TestProjectConfig:
    def test_defaults(self) -> None:
        cfg = ProjectConfig(name="github")
        assert cfg.enabled is True
        assert cfg.repo == ""
        assert cfg.team_id == ""


class FakeProvider(ProjectProvider):
    """Minimal concrete implementation for ABC conformance test."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def capabilities(self) -> frozenset[ProjectCapability]:
        return frozenset({ProjectCapability.CREATE_ISSUE})

    async def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> Issue:
        return Issue(ref=IssueRef("fake", "#0"), title=title, body=body, state=IssueState.OPEN)

    async def close_issue(self, issue_id: str) -> Issue:
        return Issue(ref=IssueRef("fake", issue_id), title="", body="", state=IssueState.CLOSED)

    async def update_issue(
        self, issue_id: str, title: str | None = None, body: str | None = None, labels: list[str] | None = None
    ) -> Issue:
        return Issue(ref=IssueRef("fake", issue_id), title=title or "", body=body or "", state=IssueState.OPEN)

    async def list_issues(self, state: IssueState | None = None, label: str | None = None) -> list[Issue]:
        return []

    async def add_comment(self, issue_id: str, body: str) -> None:
        pass

    async def search_issues(self, query: str) -> list[Issue]:
        return []


class TestFakeProviderConformance:
    def test_instantiation(self) -> None:
        p = FakeProvider()
        assert p.name == "fake"

    def test_supports(self) -> None:
        p = FakeProvider()
        assert p.supports(ProjectCapability.CREATE_ISSUE)
        assert not p.supports(ProjectCapability.LIST_ISSUES)

    @pytest.mark.asyncio
    async def test_no_op_lifecycle(self) -> None:
        p = FakeProvider()
        await p.initialize()
        await p.shutdown()
