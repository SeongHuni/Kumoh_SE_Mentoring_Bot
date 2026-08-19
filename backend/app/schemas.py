from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    confirmed_intent_key: str | None = Field(default=None, max_length=100)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        question = value.strip()
        if len(question) < 2:
            raise ValueError("question must contain at least two characters")
        return question


class Source(BaseModel):
    title: str
    url: str
    source: str
    published_at: str | None
    score: float


class ChatResponse(BaseModel):
    response_type: Literal["answer", "no_answer"] = "answer"
    answer: str
    sources: list[Source] = Field(default_factory=list)
    grounded: bool
    interpreted_intent: None = None
    clarification_options: list[object] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    recent_notices: list[object] = Field(default_factory=list)


class LiveResponse(BaseModel):
    status: Literal["alive"] = "alive"


class HealthResponse(BaseModel):
    status: Literal[
        "ready", "needs_configuration", "needs_index", "needs_reindex", "unavailable"
    ]
    collection: str
    indexed_chunks: int
    embedding_model: str
    answer_model: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    embedding_api_configured: bool
    answer_api_configured: bool
    index_compatible: bool
    index_reason: str
