"""Project router — delegates to the default registered provider."""

from __future__ import annotations

from integra.integrations.projects.base import Issue, IssueState, ProjectProvider


class ProjectRouter:
    """Routes project management calls to the default registered provider.

    Simpler than ChannelRouter — no sensitivity dimension.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProjectProvider] = {}
        self._default: str | None = None

    def register(self, provider: ProjectProvider) -> None:
        """Register a provider; first registered becomes the default."""
        self._providers[provider.name] = provider
        if self._default is None:
            self._default = provider.name

    @property
    def default(self) -> ProjectProvider:
        """Return the default provider."""
        if self._default is None or self._default not in self._providers:
            raise RuntimeError("No project provider registered")
        return self._providers[self._default]

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> Issue:
        return await self.default.create_issue(title, body, labels)

    async def close_issue(self, issue_id: str) -> Issue:
        return await self.default.close_issue(issue_id)

    async def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> Issue:
        return await self.default.update_issue(issue_id, title, body, labels)

    async def list_issues(
        self,
        state: IssueState | None = None,
        label: str | None = None,
    ) -> list[Issue]:
        return await self.default.list_issues(state, label)

    async def add_comment(self, issue_id: str, body: str) -> None:
        return await self.default.add_comment(issue_id, body)

    async def search_issues(self, query: str) -> list[Issue]:
        return await self.default.search_issues(query)
