
from pydantic import BaseModel


class SlackUser(BaseModel):
    id: str
    name: str
    real_name: str | None = None
    email: str | None = None


class SlackChannel(BaseModel):
    id: str
    name: str
    is_private: bool = False
    topic: str | None = None
    purpose: str | None = None


class SlackMessage(BaseModel):
    user: str
    text: str
    ts: str  # timestamp
    channel: str
    thread_ts: str | None = None
    attachments: list[dict] | None = None