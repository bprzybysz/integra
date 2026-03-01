"""GitHub project provider using the gh CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Any

from integra.integrations.projects.base import (
    Issue,
    IssueRef,
    IssueState,
    ProjectCapability,
    ProjectLabel,
    ProjectProvider,
)

logger = logging.getLogger(__name__)

_GH_STATE_MAP: dict[str, IssueState] = {
    "OPEN": IssueState.OPEN,
    "open": IssueState.OPEN,
    "CLOSED": IssueState.CLOSED,
    "closed": IssueState.CLOSED,
}


def _parse_issue(data: dict[str, Any], repo: str) -> Issue:
    """Parse a gh --json issue dict into an Issue."""
    number = data.get("number", 0)
    raw_state = str(data.get("state", "open"))
    state = _GH_STATE_MAP.get(raw_state, IssueState.OPEN)
    labels_raw: list[dict[str, Any]] = data.get("labels", [])
    labels = [
        ProjectLabel(
            name=str(lb.get("name", "")),
            color=str(lb.get("color", "")) or None,
            description=str(lb.get("description", "")) or None,
        )
        for lb in labels_raw
    ]
    assignees_raw: list[dict[str, Any]] = data.get("assignees", [])
    assignee: str | None = None
    if assignees_raw:
        assignee = str(assignees_raw[0].get("login", "")) or None
    return Issue(
        ref=IssueRef(
            provider="github",
            issue_id=f"#{number}",
            url=str(data.get("url", "")),
        ),
        title=str(data.get("title", "")),
        body=str(data.get("body", "")),
        state=state,
        labels=labels,
        assignee=assignee,
    )


async def _run_gh(*args: str) -> tuple[int, str, str]:
    """Run a gh CLI command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "gh",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    return proc.returncode or 0, stdout_b.decode(), stderr_b.decode()


class GitHubProvider(ProjectProvider):
    """GitHub project provider using the gh CLI.

    Requires the gh CLI to be installed and authenticated.
    Falls back to warning log if gh is not found at initialize().
    """

    def __init__(self, repo: str = "") -> None:
        self._repo = repo
        self._available = False

    @property
    def name(self) -> str:
        return "github"

    @property
    def capabilities(self) -> frozenset[ProjectCapability]:
        return frozenset(ProjectCapability)

    async def initialize(self) -> None:
        """Check that gh CLI is available."""
        if shutil.which("gh") is None:
            logger.warning("gh CLI not found — GitHubProvider disabled")
        else:
            self._available = True
            logger.info("GitHubProvider initialized (repo=%s)", self._repo)

    async def shutdown(self) -> None:
        pass

    def _repo_args(self) -> list[str]:
        return ["--repo", self._repo] if self._repo else []

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> Issue:
        args = ["issue", "create", "--title", title, "--body", body, *self._repo_args()]
        if labels:
            for lbl in labels:
                args += ["--label", lbl]
        args += ["--json", "number,title,body,state,labels,assignees,url"]
        rc, out, err = await _run_gh(*args)
        if rc != 0:
            raise RuntimeError(f"gh issue create failed: {err.strip()}")
        data: dict[str, Any] = json.loads(out)
        return _parse_issue(data, self._repo)

    async def close_issue(self, issue_id: str) -> Issue:
        num = issue_id.lstrip("#")
        rc, _out, err = await _run_gh("issue", "close", num, *self._repo_args())
        if rc != 0:
            raise RuntimeError(f"gh issue close failed: {err.strip()}")
        return await self._fetch_issue(num)

    async def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> Issue:
        num = issue_id.lstrip("#")
        args = ["issue", "edit", num, *self._repo_args()]
        if title:
            args += ["--title", title]
        if body:
            args += ["--body", body]
        if labels:
            args += ["--add-label", ",".join(labels)]
        rc, _out, err = await _run_gh(*args)
        if rc != 0:
            raise RuntimeError(f"gh issue edit failed: {err.strip()}")
        return await self._fetch_issue(num)

    async def list_issues(
        self,
        state: IssueState | None = None,
        label: str | None = None,
    ) -> list[Issue]:
        args = [
            "issue",
            "list",
            *self._repo_args(),
            "--json",
            "number,title,body,state,labels,assignees,url",
        ]
        if state == IssueState.CLOSED:
            args += ["--state", "closed"]
        elif state == IssueState.OPEN:
            args += ["--state", "open"]
        if label:
            args += ["--label", label]
        rc, out, err = await _run_gh(*args)
        if rc != 0:
            raise RuntimeError(f"gh issue list failed: {err.strip()}")
        items: list[dict[str, Any]] = json.loads(out)
        return [_parse_issue(item, self._repo) for item in items]

    async def add_comment(self, issue_id: str, body: str) -> None:
        num = issue_id.lstrip("#")
        rc, _out, err = await _run_gh("issue", "comment", num, "--body", body, *self._repo_args())
        if rc != 0:
            raise RuntimeError(f"gh issue comment failed: {err.strip()}")

    async def search_issues(self, query: str) -> list[Issue]:
        repo_qualifier = f"repo:{self._repo} " if self._repo else ""
        args = [
            "search",
            "issues",
            f"{repo_qualifier}{query}",
            "--json",
            "number,title,body,state,labels,assignees,url",
        ]
        rc, out, err = await _run_gh(*args)
        if rc != 0:
            raise RuntimeError(f"gh search issues failed: {err.strip()}")
        items: list[dict[str, Any]] = json.loads(out)
        return [_parse_issue(item, self._repo) for item in items]

    async def _fetch_issue(self, num: str) -> Issue:
        rc, out, err = await _run_gh(
            "issue",
            "view",
            num,
            *self._repo_args(),
            "--json",
            "number,title,body,state,labels,assignees,url",
        )
        if rc != 0:
            raise RuntimeError(f"gh issue view failed: {err.strip()}")
        data: dict[str, Any] = json.loads(out)
        return _parse_issue(data, self._repo)
