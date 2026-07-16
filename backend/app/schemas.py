from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.domain import AnswerSource, RecentNotice
from backend.app.index_manifest import IndexReason


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    confirmed_intent_key: str | None = Field(default=None, max_length=100)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("confirmed_intent_key")
    @classmethod
    def strip_confirmed_intent_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("confirmed_intent_key must not be blank")
        return stripped


class ClarificationOption(BaseModel):
    topic_key: str
    intent_key: str
    label: str
    example: str


class ChatResponse(BaseModel):
    response_type: Literal["clarification", "answer", "no_answer"] = "answer"
    answer: str
    sources: list[AnswerSource]
    grounded: bool
    interpreted_intent: ClarificationOption | None = None
    clarification_options: list[ClarificationOption] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    recent_notices: list[RecentNotice] = Field(default_factory=list)


class LiveResponse(BaseModel):
    status: Literal["alive"] = "alive"


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
