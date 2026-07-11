from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class Attachment(BaseModel):
    name: str
    url: str


class BoardPost(BaseModel):
    id: str
    source: str
    title: str
    content: str
    author: str = ""
    published_at: str | None = None
    url: str
    attachments: list[Attachment] = Field(default_factory=list)
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("id", "source", "title", "content", "url")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned


class TextChunk(BaseModel):
    id: str
    post_id: str
    source: str
    title: str
    text: str
    url: str
    published_at: str | None
    chunk_index: int


class RetrievedChunk(BaseModel):
    chunk: TextChunk
    score: float


class AnswerSource(BaseModel):
    title: str
    url: str
    source: str
    published_at: str | None = None
    score: float
