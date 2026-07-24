from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.categories import CategoryLabel


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
    llm_category: CategoryLabel | None = None
    document_type: Literal["notice", "static", "historical"] = "notice"
    url: str
    attachments: list[Attachment] = Field(default_factory=list)
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    topic_key: str | None = None
    topic_label: str | None = None
    category_key: str | None = None
    category_label: str | None = None
    intent_key: str | None = None
    notice_kind: str | None = None
    is_latest_topic: bool = False

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
    document_type: Literal["notice", "static", "historical"] = "notice"
    chunk_index: int
    topic_key: str
    topic_label: str
    is_latest_topic: bool
    intent_key: str | None = None
    category_key: str = "other"
    category_label: str = "기타"
    notice_kind: str | None = None


class RetrievedChunk(BaseModel):
    chunk: TextChunk
    score: float


class AnswerSource(BaseModel):
    title: str
    url: str
    source: str
    published_at: str | None = None
    score: float


class RecentNotice(BaseModel):
    title: str
    url: str
    source: str
    published_at: str | None = None
    topic_key: str
    topic_label: str
