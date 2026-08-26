"""RAG 파이프라인.

질문 하나가 답변이 되기까지.

  1. 검색 계획기   질문을 독립형 질의로 바꾸고 search/clarify/reject 를 정한다
  2. 질의 임베딩   원문이 아니라 재작성된 standalone_query 를 쓴다
  3. 검색 top-100  분류 필터는 걸지 않는다
  4. 중요도 가중치 유사도 + 이벤트 가중치 − 경과연수 감쇠
  5. 최신 우선     temporal 이 latest 일 때만, 점수가 비슷한 것끼리
  6. 다양성        같은 문서 2청크, 같은 주제 2건까지 -> top-5
  7. 답변 생성     검색된 자료만 근거로
  8. 출처          검색된 순서 그대로, 걸러내지 않고

원래 Node 서버의 answerQuestion 이었다. 백엔드를 Python 으로 일원화하면서
server/index.js 는 지웠고, 지금은 여기가 정본이다.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from collections.abc import Sequence
from urllib.parse import urlparse

from backend.app.answer_rules import NO_ANSWER, OUT_OF_SCOPE
from backend.app.domain import AnswerSource, RetrievedChunk
from backend.app.query_planner import (
    ClarificationCandidate,
    SearchPlan,
    plan_search,
    plan_to_filters,
)
from backend.app.ranking import (
    ScoringConfig,
    apply_scoring,
    diversify,
    prefer_recent_among_similar,
)
from backend.app.schemas import ChatResponse, ClarificationOption
from backend.app.session import Session
from backend.app.suggestions import pick_suggested

MAX_PER_DOC = 2
MAX_PER_TOPIC = 2


# ------------------------------------------------------------------ 확정 의도
# 되묻기 선택지는 서버에 상태를 두지 않고 되돌릴 수 있어야 한다.
# 질의 자체를 base64url 로 실어 보낸다.
def encode_intent(query: str) -> str:
    return base64.urlsafe_b64encode(query.encode("utf-8")).decode("ascii").rstrip("=")


def decode_intent(key: str) -> str | None:
    try:
        padded = key + "=" * (-len(key) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8").strip() or None
    except Exception:
        return None


def _is_http_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(str(value))
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and not parsed.username and not parsed.password


def parse_review_title(title: str) -> tuple[str, str] | None:
    """강의평 제목은 "과목명 (교수명) 강의평 N" 형태다.

    링크가 없으므로 화면에서 "어떤 과목의 어떤 교수 강의평인지"를 대신
    보여주기 위해 분해한다.
    """
    match = re.match(r"^(.+?)\s*\(([^)]+)\)\s*강의평", str(title or ""))
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def to_sources(retrieved: Sequence[RetrievedChunk]) -> list[AnswerSource]:
    """검색 결과를 그대로, 같은 순서로 내보낸다.

    순서가 중요하다. 답변 프롬프트의 [1], [2] 가 이 순서를 쓰고 화면도 같은
    번호를 쓴다. 여기서 걸러내거나 순서를 바꾸면 본문 번호와 출처 목록이
    어긋난다. 그래서 URL 없는 강의평도 빼지 않고 url=None 으로 내보낸다.
    화면에서 무엇을 감출지는 프론트가 정한다(실제 인용된 것만 표시).
    """
    sources: list[AnswerSource] = []
    for index, item in enumerate(retrieved, start=1):
        meta = item.metadata or {}
        review = parse_review_title(meta.get("title", "")) if meta.get("source") == "에브리타임" else None
        url = meta.get("source_url") or meta.get("url")
        sources.append(
            AnswerSource(
                index=index,
                title=str(meta.get("title") or ""),
                url=str(url) if _is_http_url(url) else None,
                source=str(meta.get("source") or ""),
                published_at=str(meta.get("published_at")) if meta.get("published_at") else None,
                score=round(float(item.score), 4),
                kind="review" if review else "notice",
                course=review[0] if review else None,
                professor=review[1] if review else None,
            )
        )
    return sources


def to_clarification_options(
    candidates: Sequence[ClarificationCandidate],
) -> list[ClarificationOption]:
    return [
        ClarificationOption(
            topic_key=hashlib.sha1(c.label.encode("utf-8")).hexdigest()[:12],
            intent_key=encode_intent(c.query),
            label=c.label,
            example=c.query,
        )
        for c in candidates
    ]


class RAGService:
    def __init__(
        self,
        *,
        provider,
        vector_store,
        top_k: int = 5,
        scoring: ScoringConfig | None = None,
        fetch_k: int | None = None,
    ) -> None:
        self.provider = provider
        self.vector_store = vector_store
        self.top_k = top_k
        self.scoring = scoring or ScoringConfig()
        # 처음엔 30이었다. "이정연 장학금"의 정답이 33위여서 이후의
        # 가중치·다양성 로직이 손댈 대상 자체가 없었다.
        self.fetch_k = fetch_k or int(os.getenv("RAG_FETCH_K", "0")) or max(100, top_k * 10)

    # -------------------------------------------------------------- 응답 조립
    def _reply(
        self,
        *,
        response_type: str,
        answer: str,
        question: str,
        grounded: bool = False,
        sources: list[AnswerSource] | None = None,
        options: list[ClarificationOption] | None = None,
    ) -> ChatResponse:
        options = options or []
        return ChatResponse(
            response_type=response_type,
            answer=answer,
            sources=sources or [],
            grounded=grounded,
            interpreted_intent=options[0] if options else None,
            clarification_options=options,
            suggested_questions=pick_suggested(question),
            recent_notices=[],
        )

    # -------------------------------------------------------------- 파이프라인
    def ask(
        self,
        question: str,
        session: Session | None = None,
        confirmed_intent_key: str | None = None,
    ) -> ChatResponse:
        session = session or Session()

        confirmed_query = decode_intent(confirmed_intent_key) if confirmed_intent_key else None
        if confirmed_query:
            # 사용자가 되묻기 선택지를 골랐다. 다시 되묻지 않고 그 질의로 바로 검색한다.
            plan = SearchPlan(action="search", standalone_query=confirmed_query)
        else:
            plan = plan_search(self.provider, session, question)

        # --- 되묻기 (검색·생성 모델을 호출하지 않는다. 비용과 지연이 0이다)
        if plan.action == "clarify":
            options = to_clarification_options(plan.clarification_candidates)
            if options:
                return self._reply(
                    response_type="clarification",
                    answer=plan.clarifying_question or "어떤 것에 대해 물으시는지 알려주시겠어요?",
                    question=question,
                    options=options,
                )
            # 후보를 못 만들었으면 되묻기 형식을 만족시킬 수 없으므로 답변 불가로 처리한다.
            return self._reply(
                response_type="no_answer",
                answer=plan.clarifying_question or "질문을 조금 더 구체적으로 알려주시겠어요?",
                question=question,
            )

        if plan.action == "reject":
            return self._reply(response_type="no_answer", answer=OUT_OF_SCOPE, question=question)

        # --- 검색
        query_embedding = self.provider.embed([plan.standalone_query])[0]
        where = plan_to_filters(plan) or None
        retrieved = self.vector_store.query(query_embedding, self.fetch_k, where=where)
        if not retrieved and where is not None:
            # 필터 때문에 비었으면 필터 없이 한 번 더 본다.
            retrieved = self.vector_store.query(query_embedding, self.fetch_k)

        if not retrieved:
            return self._reply(response_type="no_answer", answer=NO_ANSWER, question=question)

        # --- 후처리
        retrieved = apply_scoring(retrieved, self.scoring)
        if plan.temporal_constraint.mode == "latest":
            retrieved = prefer_recent_among_similar(retrieved, self.top_k * 2)
        retrieved = diversify(
            retrieved, self.top_k, max_per_doc=MAX_PER_DOC, max_per_topic=MAX_PER_TOPIC
        )

        # --- 생성
        answer = self.provider.answer(question, retrieved)
        session.add_pair(question, answer)

        return self._reply(
            response_type="answer",
            answer=answer,
            question=question,
            grounded=True,
            sources=to_sources(retrieved),
        )
