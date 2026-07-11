from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.domain import AnswerSource


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


class HealthResponse(BaseModel):
    status: Literal["ready", "needs_configuration", "needs_index"]
    provider: Literal["local", "openai"]
    openai_configured: bool
    indexed_chunks: int
    chat_model: str
    embedding_model: str
