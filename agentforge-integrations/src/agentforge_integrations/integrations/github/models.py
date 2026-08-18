from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GitHubUser(BaseModel):
    login: str
    id: int
    avatar_url: str | None = None


class GitHubRepo(BaseModel):
    id: int
    name: str
    full_name: str
    private: bool
    owner: GitHubUser
    html_url: str
    description: str | None = None
    default_branch: str
    created_at: datetime
    updated_at: datetime


class GitHubIssue(BaseModel):
    id: int
    number: int
    title: str
    state: str  # open, closed
    body: str | None = None
    user: GitHubUser
    labels: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class GitHubPullRequest(BaseModel):
    id: int
    number: int
    title: str
    state: str
    body: str | None = None
    user: GitHubUser
    head: dict[str, str]  # {ref, sha, repo}
    base: dict[str, str]
    created_at: datetime
    updated_at: datetime


class GitHubBranch(BaseModel):
    name: str
    commit: dict[str, str]  # {sha, url}
    protected: bool


class GitHubFile(BaseModel):
    name: str
    path: str
    sha: str
    size: int
    url: str
    html_url: str | None = None
    content: str | None = None  # base64 encoded
    encoding: str | None = None