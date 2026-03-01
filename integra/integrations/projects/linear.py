"""Linear project provider — MCP-only stub.

This provider maps Linear API concepts to the ProjectProvider ABC but
cannot run in FastAPI runtime. Methods raise RuntimeError with a clear
message. Future path: replace with HTTP client using linear_api_key.

State mapping:
  Backlog / Todo  → IssueState.OPEN
  In Progress     → IssueState.IN_PROGRESS
  Done            → IssueState.CLOSED
  Cancelled       → IssueState.CLOSED
"""

from __future__ import annotations

from integra.integrations.projects.base import (
    Issue,
    IssueState,
    ProjectCapability,
    ProjectProvider,
)

_LINEAR_STATE_MAP: dict[str, IssueState] = {
    "Backlog": IssueState.OPEN,
    "Todo": IssueState.OPEN,
    "In Progress": IssueState.IN_PROGRESS,
    "Done": IssueState.CLOSED,
    "Cancelled": IssueState.CLOSED,
}

_MCP_ONLY = "Linear MCP tools only available in Claude Code sessions"


class LinearProvider(ProjectProvider):
    """Linear project provider (MCP-only stub).

    Instantiates successfully but raises RuntimeError on all operations.
    Intended for Claude Code sessions where MCP Linear tools are available.

    Future: replace with HTTP client using settings.linear_api_key.
    Config: team_id, project_id from settings.linear_team_id / settings.linear_project_id.
    """

    def __init__(self, team_id: str = "", project_id: str = "") -> None:
        self._team_id = team_id
        self._project_id = project_id

    @property
    def name(self) -> str:
        return "linear"

    @property
    def capabilities(self) -> frozenset[ProjectCapability]:
        return frozenset(ProjectCapability)

    @property
    def state_map(self) -> dict[str, IssueState]:
        """Linear state name → IssueState mapping."""
        return dict(_LINEAR_STATE_MAP)

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> Issue:
        raise RuntimeError(_MCP_ONLY)

    async def close_issue(self, issue_id: str) -> Issue:
        raise RuntimeError(_MCP_ONLY)

    async def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> Issue:
        raise RuntimeError(_MCP_ONLY)

    async def list_issues(
        self,
        state: IssueState | None = None,
        label: str | None = None,
    ) -> list[Issue]:
        raise RuntimeError(_MCP_ONLY)

    async def add_comment(self, issue_id: str, body: str) -> None:
        raise RuntimeError(_MCP_ONLY)

    async def search_issues(self, query: str) -> list[Issue]:
        raise RuntimeError(_MCP_ONLY)
