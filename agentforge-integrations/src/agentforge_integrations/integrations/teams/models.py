
from pydantic import BaseModel


class TeamsTeam(BaseModel):
    id: str
    display_name: str
    description: str | None = None


class TeamsChannel(BaseModel):
    id: str
    display_name: str
    description: str | None = None


class TeamsMessage(BaseModel):
    id: str
    body: str
    from_user: dict[str, str]
    created_at: str
    channel_id: str
    team_id: str | None = None