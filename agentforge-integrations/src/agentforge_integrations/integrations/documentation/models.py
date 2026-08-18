from datetime import datetime

from pydantic import BaseModel


class Document(BaseModel):
    id: str
    title: str
    content: str
    path: str
    created_at: datetime
    updated_at: datetime
    version: str | None = None


class DocumentFolder(BaseModel):
    id: str
    name: str
    path: str
    documents: list[Document] = []