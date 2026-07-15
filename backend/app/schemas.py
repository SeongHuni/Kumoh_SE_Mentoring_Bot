from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.domain import AnswerSource, RecentNotice
from backend.app.index_manifest import IndexReason


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class ChatResponse(BaseModel):
    answer: str
    sources: list[AnswerSource]
    grounded: bool
    suggested_questions: list[str] = Field(default_factory=list)
    recent_notices: list[RecentNotice] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal[
        "ready",
        "needs_configuration",
        "needs_index",
        "needs_reindex",
        "unavailable",
    ]
    provider: Literal["local", "openai"]
    openai_configured: bool
    indexed_chunks: int
    chat_model: str
    embedding_model: str
    index_compatible: bool
    index_reason: IndexReason
