from datetime import datetime

from pydantic import BaseModel


class JiraUser(BaseModel):
    account_id: str
    display_name: str
    email_address: str | None = None
    active: bool = True


class JiraProject(BaseModel):
    id: str
    key: str
    name: str
    description: str | None = None


class JiraIssue(BaseModel):
    id: str
    key: str
    summary: str
    description: str | None = None
    status: str
    priority: str | None = None
    assignee: JiraUser | None = None
    reporter: JiraUser | None = None
    created: datetime
    updated: datetime


class JiraComment(BaseModel):
    id: str
    body: str
    author: JiraUser
    created: datetime
    updated: datetime