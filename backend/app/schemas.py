from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.domain import AnswerSource, RecentNotice


class ClarificationOption(BaseModel):
    """되묻기 선택지.

    사용자가 고르면 intent_key 를 그대로 서버에 돌려보내, 다시 되묻지 않고
    그 주제로 바로 검색한다. 서버에 상태를 두지 않기 위해 질의 자체를
    base64url 로 인코딩한 값이다.
    """

    topic_key: str = Field(description="선택지 식별자입니다.")
    intent_key: str = Field(description="다시 보낼 때 쓰는 확정 의도 키입니다.")
    label: str = Field(description="사용자에게 보여줄 짧은 이름입니다.", examples=["수강신청 일정"])
    example: str = Field(description="이 선택지를 고르면 검색할 질의입니다.")


class ChatRequest(BaseModel):
    """챗봇 답변을 요청하는 본문입니다."""

    question: str = Field(
        min_length=2,
        max_length=500,
        description="학과 공지 또는 SE 게시판에서 찾을 질문입니다.",
        examples=["캡스톤디자인 신청 방법을 알려줘"],
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "대화 이력을 잇기 위한 세션 식별자입니다. 보내지 않으면 클라이언트 "
            "주소로 구분하므로, 같은 망에 여러 사용자가 있으면 이력이 섞입니다."
        ),
    )
    confirmed_intent_key: str | None = Field(
        default=None,
        description="되묻기 선택지를 고른 경우, 그 선택지의 intent_key 입니다.",
    )

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class ChatResponse(BaseModel):
    """검색된 게시글을 근거로 생성한 챗봇 답변입니다."""

    response_type: Literal["answer", "clarification", "no_answer"] = Field(
        default="answer",
        description=(
            "answer 는 검색 결과를 근거로 답한 경우, clarification 은 대상이 "
            "특정되지 않아 되물은 경우(검색·생성 모델을 호출하지 않습니다), "
            "no_answer 는 근거가 없거나 범위 밖이라 답하지 않은 경우입니다."
        ),
    )
    answer: str = Field(description="출처 표기가 포함된 답변 본문입니다.")
    sources: list[AnswerSource] = Field(
        default_factory=list,
        description=(
            "답변의 근거로 사용한 원문 게시글입니다. 걸러내거나 재정렬하지 않고 "
            "검색된 순서 그대로 보냅니다. 답변 본문의 [1], [2] 가 이 순서를 가리킵니다."
        ),
    )
    grounded: bool = Field(description="검색된 출처를 근거로 답변했는지 여부입니다.")
    interpreted_intent: ClarificationOption | None = Field(
        default=None,
        description="되물었을 때 가장 그럴듯한 해석입니다.",
    )
    clarification_options: list[ClarificationOption] = Field(
        default_factory=list,
        description="되물을 때 사용자가 고를 수 있는 선택지입니다.",
    )
    suggested_questions: list[str] = Field(
        default_factory=list,
        description="후속으로 물어볼 수 있는 추천 질문입니다.",
    )
    recent_notices: list[RecentNotice] = Field(
        default_factory=list,
        description="관련 최근 공지 목록입니다. 현재 화면에서는 표시하지 않습니다.",
    )


class ApiError(BaseModel):
    """API 요청을 처리하지 못했을 때의 오류 응답입니다."""

    detail: str = Field(description="오류 원인입니다.", examples=["벡터 인덱스가 비어 있습니다."])


class HealthResponse(BaseModel):
    """현재 RAG 서비스의 준비 상태입니다."""

    status: Literal["ready", "needs_configuration", "needs_index"] = Field(
        description="ready이면 채팅 요청을 처리할 수 있습니다."
    )
    provider: Literal["local", "openai"] = Field(description="현재 선택된 답변 제공자입니다.")
    openai_configured: bool = Field(description="OpenAI 키 또는 로컬 제공자가 준비됐는지 여부입니다.")
    indexed_chunks: int = Field(description="Chroma DB에 저장된 검색 청크 수입니다.")
    collection: str = Field(default="", description="현재 사용 중인 Chroma 컬렉션 이름입니다.")
    chat_model: str = Field(description="현재 답변 모델 이름입니다.")
    embedding_model: str = Field(description="현재 임베딩 모델 이름입니다.")
