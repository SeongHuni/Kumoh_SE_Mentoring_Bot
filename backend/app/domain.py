from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    topic_key: str | None = None
    topic_label: str | None = None
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
    chunk_index: int
    topic_key: str
    topic_label: str
    is_latest_topic: bool


class RetrievedChunk(BaseModel):
    chunk: TextChunk
    score: float
    # Chroma 가 준 원본 메타데이터. 중요도 가중치와 다양성 로직이 쓴다.
    metadata: dict[str, Any] = Field(default_factory=dict)
    # 보정 전 유사도. 무엇이 왜 움직였는지 확인하려고 남긴다.
    base_score: float | None = None
    boost: float = 0.0
    decay: float = 0.0


class AnswerSource(BaseModel):
    """화면에 보여줄 근거 한 건.

    index 는 검색된 순서(1부터)이고 답변 본문의 [1], [2] 와 같은 번호다.
    걸러내거나 다시 매기지 않는다. 그렇게 하면 본문의 [3] 과 목록의 [3] 이
    서로 다른 자료를 가리키게 된다.
    """

    index: int = 0
    title: str
    # 에브리타임 강의평은 원문 링크가 없어 None 이다.
    url: str | None = None
    source: str
    published_at: str | None = None
    score: float
    # 강의평이면 "review", 공지면 "notice".
    kind: str = "notice"
    # 강의평일 때만 채워진다. 링크 대신 "과목 (교수) 강의평" 으로 표시한다.
    course: str | None = None
    professor: str | None = None


class RecentNotice(BaseModel):
    title: str
    url: str
    source: str
    published_at: str | None = None
    topic_key: str
    topic_label: str
