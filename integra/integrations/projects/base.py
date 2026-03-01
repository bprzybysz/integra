"""Abstract base for project management providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum


class ProjectCapability(StrEnum):
    """What a project provider can do."""

    CREATE_ISSUE = "create_issue"
    UPDATE_ISSUE = "update_issue"
    CLOSE_ISSUE = "close_issue"
    LIST_ISSUES = "list_issues"
    ADD_COMMENT = "add_comment"
    SEARCH_ISSUES = "search_issues"
    CREATE_LABEL = "create_label"
    LIST_LABELS = "list_labels"


class IssueState(StrEnum):
    """Normalized issue state."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


@dataclass
class IssueRef:
    """Reference to an issue across providers."""

    provider: str  # "github" | "linear"
    issue_id: str  # "#49" or "LIN-123"
    url: str | None = None


@dataclass
class ProjectLabel:
    """Issue label with optional color and description."""

    name: str
    color: str | None = None
    description: str | None = None


@dataclass
class Issue:
    """Normalized issue representation."""

    ref: IssueRef
    title: str
    body: str
    state: IssueState
    labels: list[ProjectLabel] = field(default_factory=list)
    assignee: str | None = None


class ProjectProvider(ABC):
    """Abstract project management provider.

    Implementations: GitHubProvider (Stage 2), LinearProvider (Stage 3 stub).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name (e.g. 'github')."""

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[ProjectCapability]:
        """Set of capabilities this provider supports."""

    @abstractmethod
    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> Issue:
        """Create a new issue."""

    @abstractmethod
    async def close_issue(self, issue_id: str) -> Issue:
        """Close an existing issue by ID."""

    @abstractmethod
    async def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> Issue:
        """Update issue fields."""

    @abstractmethod
    async def list_issues(
        self,
        state: IssueState | None = None,
        label: str | None = None,
    ) -> list[Issue]:
        """List issues, optionally filtered by state and label."""

    @abstractmethod
    async def add_comment(self, issue_id: str, body: str) -> None:
        """Add a comment to an issue."""

    @abstractmethod
    async def search_issues(self, query: str) -> list[Issue]:
        """Search issues by query string."""

    def supports(self, capability: ProjectCapability) -> bool:
        """Check if this provider supports a capability."""
        return capability in self.capabilities

    async def initialize(self) -> None:  # noqa: B027
        """Initialize the provider (no-op default)."""

    async def shutdown(self) -> None:  # noqa: B027
        """Shut down the provider (no-op default)."""


@dataclass
class ProjectConfig:
    """Configuration for a project provider."""

    name: str
    enabled: bool = True
    repo: str = ""  # "owner/repo" for GitHub
    team_id: str = ""  # Linear team ID
    project_id: str = ""  # Linear project ID
