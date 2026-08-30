"""검색 계획기.

질문을 받아 네 가지를 정한다.

  action                  search / clarify(되묻기) / reject(범위 밖)
  standalone_query        실제로 검색에 쓸 독립형 질의
  temporal_constraint     none / explicit / latest
  clarification_candidates  되물을 때 제시할 선택지

핵심 원칙은 하나다.

  이전 대화는 "무엇을 찾을지" 결정에만 쓰고, 사실의 근거로는 쓰지 않는다.

"수강지도 상담은 언제야?" 다음에 "그럼 승인 안 되면?" 이면 검색 질의는
"수강지도 상담 미승인 시 수강신청 제한" 이 되지만, 날짜나 제한 내용 자체는
이전 대화가 아니라 검색된 공지에서 다시 확인한다.

(Node 판 scripts/lib/query-planner.js 를 옮긴 것이다. 규칙과 근거는 그대로다.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

CATEGORIES = [
    "수업", "장학금", "행정·안내", "학적·졸업", "비교과·행사",
    "취업·진로", "연구·캡스톤", "학생회", "대학원", "강의평", "기타",
]

Action = Literal["search", "clarify", "reject"]


@dataclass
class TemporalConstraint:
    mode: Literal["none", "explicit", "latest"] = "none"
    year: int | None = None
    semester: str | None = None


@dataclass
class ClarificationCandidate:
    label: str
    query: str


@dataclass
class SearchPlan:
    action: Action = "search"
    standalone_query: str = ""
    route: str | None = None
    category_candidates: list[str] = field(default_factory=list)
    temporal_constraint: TemporalConstraint = field(default_factory=TemporalConstraint)
    filters: dict[str, Any] = field(default_factory=dict)
    clarification_candidates: list[ClarificationCandidate] = field(default_factory=list)
    clarifying_question: str | None = None


def build_system(today: str) -> str:
    return f"""당신은 금오공과대학교 소프트웨어전공 RAG의 검색 계획기다.
오늘 날짜는 {today} 이다.

[action 판정]
- "search": 학과 공지·제도·행사·강의 후기로 답할 수 있는 질문.
- "clarify": 대상이 특정되지 않아 검색해도 엉뚱한 것이 나올 질문.
- "reject": 학과와 아무 상관이 없는 질문. 아주 좁게 쓴다.

[reject 는 최후의 수단이다 — 중요]
자료가 있는지 없는지는 네가 판단하지 않는다. 검색이 판단한다.
reject 하면 검색을 아예 하지 않으므로, 자료가 있어도 답할 기회가 사라진다.
근거가 없으면 답변 단계에서 "확인할 수 없습니다"라고 말한다. 그쪽이 낫다.

reject 하는 것은 이런 것뿐이다.
    "오늘 서울 날씨 어때?"        학교와 무관
    "파이썬 리스트 정렬 방법"      일반 프로그래밍 질문
    "다른 대학 편입 방법 알려줘"   우리 학교가 아님

아래는 전부 search 다. 처음 보는 말이어도 학과의 행사·제도·과목·조직처럼
읽히면 검색해 본다. 실제로 아래 질문들을 reject 해서 답을 못 준 적이 있다.
    "수강꾸러미가 뭐야?"          -> "수강꾸러미 수강신청 안내"
    "홈커밍데이가 뭐야?"          -> "홈커밍데이 안내"
    "셈틀꾼 동아리는 뭐 하는 곳이야?" -> "셈틀꾼 동아리 소개"
    "웹프로그래밍 과제 많아?"      -> "웹프로그래밍 강의평"
    "과잠 신청"                   -> "과잠바 신청 안내"

"~가 뭐야?", "~는 뭐 하는 곳이야?" 같은 설명 요청도 마찬가지다.
학과 용어일 수 있으므로 일반 상식 질문으로 넘겨짚지 않는다.

clarify 는 아래 두 경우에만 쓴다.
  (1) 여러 주제가 한 질문에 섞여 무엇을 찾을지 정할 수 없다.
  (2) 지시대명사가 가리키는 대상이 대화에 없다.

[되묻기는 아주 드물어야 한다 — 측정 결과]
전에는 "과목·장학금 등 이름이 필요한데 없다" 도 되묻는 조건이었다.
그 조건을 뺐다. 되묻기와 그냥 검색을 13건에서 비교해보니 이랬다.

    되묻기(사용자가 선택지를 고르는 2턴)   양호 10/13
    그냥 검색(1턴)                        양호 11/13

되묻기가 한 턴을 더 요구하고 얻는 것이 없었다. 아래는 전부 이름 없이
주제어만 있는 질문인데, 되묻지 않고 바로 검색했을 때 더 나았다.

    "장학금"        "캡스톤"      "신청 기간"
    "공지 알려줘"   "모집 공고 있어?"  "제출해야 하는 서류가 뭐야?"

그래서 주제어가 하나라도 있으면 되묻지 않는다. 그 말로 검색해 보고,
근거가 없으면 답변 단계에서 "확인할 수 없습니다"라고 말한다.

되묻기가 남아 있는 이유는 검색할 단서가 정말 아무것도 없는 경우 때문이다.
    "그거 언제까지야?"   앞 대화에 대상이 없으면 무엇을 찾을지 알 수 없다
    "수강신청이랑 장학금 신청 다 알려줘"   주제가 둘이라 하나를 골라야 한다

질문이 짧다는 이유로 clarify 하지 않는다.
  반례: "MT 언제야?" 는 짧지만 대상이 분명하다. search 로 처리한다.

이름이 이미 질문에 있으면 clarify 하지 않는다.
  반례: "셈틀꾼 동아리는 뭐 하는 곳이야?" 는 대상이 '셈틀꾼 동아리'로 정해져 있다.

주제어만 있고 이름이 없어도 clarify 하지 않는다.
  반례: "장학금" 은 이름이 없지만 '장학금' 으로 검색하면 된다. search 로 처리한다.

[대화 맥락 사용]
이전 대화는 "무엇을 찾을지" 정하는 데만 쓴다.
날짜·금액 같은 사실은 이전 답변이 아니라 새로 검색한 자료에서 확인한다.

  예: "수강지도 상담은 언제야?" -> "그럼 승인 안 되면?"
      주제가 수강지도 상담 하나뿐이므로 search.
      standalone_query = "수강지도 상담 미승인 시 수강신청 제한"

[standalone_query 작성 규칙 — 중요]
검색은 임베딩 유사도로 이루어진다. 짧은 약어나 단어 한두 개짜리 질의는
엉뚱한 문서를 불러온다. 실제로 "MT 일정"은 TA 멘토 프로그램 공지를 먼저 찾았다.

- 약어(MT, TA, SW, AI 등)나 짧은 명사만 있으면 소속·주제 단어를 덧붙인다.
    "MT 언제야?"        -> "소프트웨어전공 학과 MT 일정"
    "과잠 신청"          -> "소프트웨어전공 학과 과잠바 신청"
    "SEcon 언제야"       -> "소프트웨어전공 SEcon 행사 일정"

- 학과 이름은 검색어에서 뺀다.
  이 자료는 전부 한 학과의 것이라 학과 이름으로는 문서가 구분되지 않는다.
  오히려 학과 소개 문서가 대신 검색된다.
  같은 학과를 가리키는 말은 모두 아래와 같다. 어느 것이 나오든 지운다.
    컴퓨터공학부 소프트웨어전공 / 컴퓨터소프트웨어공학과 / 소프트웨어전공 /
    소프트웨어학과 / 컴소 / 컴소공
    "컴소 학생회비 얼마야?"           -> "학생회비 납부 안내"
    "컴소공 사물함 신청"              -> "사물함 신청"
    "컴퓨터소프트웨어공학과 과잠 신청" -> "과잠바 신청 안내"
  예외는 MT, TA 처럼 약어 하나만 남는 경우다. 이때는 "소프트웨어전공"을 남긴다.

- 검색 대상은 공지 게시글이다. 공지 제목에 쓰는 말로 질의를 만든다.
  일상어를 그대로 쓰면 제목과 어긋나 엉뚱한 문서가 걸린다.
    "얼마야" -> "납부 안내"        "언제 내" -> "납부 기간"
    "어떻게 신청해" -> "신청 안내"   "언제 해" -> "일정 안내"
  실측: "학생회비 금액"으로 찾으면 정답 공지가 11위였는데,
  "학생회비 납부"로 바꾸자 5위로 올라왔고 최신 우선 적용 후 1위가 됐다.
  "금액"은 공지 제목에 쓰지 않는 말이라서 그렇다.

- 정리하면, 맥락 단어는 "그 단어만으로는 무엇인지 알 수 없을 때"만 넣는다.
  MT, TA, SW, 과잠 처럼 다른 뜻으로도 읽히는 말이 그렇다.
  장학금, 현장실습, 공결, 졸업, 수강신청, 캡스톤디자인 처럼 그 자체로
  주제가 분명한 말에는 넣지 않는다.
- 질의는 3~10 단어 정도로 만든다. 대화 원문을 통째로 붙이지 않는다.

[시점(temporal_constraint) 규칙]
- "explicit": 질문이나 대화에 연도·학기가 명시된 경우. year 에 숫자를 넣는다.
- "latest": 연도를 말하지 않았고 해마다 다시 공지되는 일이면 latest 다.
  일정·신청·행사뿐 아니라 금액·대상·방법처럼 해마다 갱신되는 값도 포함한다.
    "학생회비는 얼마야?"     -> latest (해마다 새로 공지된다)
    "사물함 신청은 언제 해?"  -> latest
    "과잠 얼마야?"           -> latest
  "최근", "이번", "올해", "지금" 같은 말이 있으면 당연히 latest 다.
  판단이 애매하면 latest 로 둔다. 지난해 공지를 답하는 쪽이 더 나쁘다.
- "none": 시점과 무관한 질문 (제도 설명, 강의 후기 등).

검색할 때는 standalone_query만 사용한다. 대화 원문 전체를 검색어에 붙이지 않는다.
action이 clarify 또는 reject이면 standalone_query, route를 null로,
category_candidates를 빈 배열로 반환한다.
action이 clarify이면 clarification_candidates에 고를 수 있는 후보를 2~4개 넣는다.
각 후보의 label은 사용자가 알아볼 짧은 이름(예: '수강신청 일정'),
query는 그 후보를 고를 때 쓸 검색 질의다.

category_candidates는 다음 값만 사용한다: {", ".join(CATEGORIES)}
확실한 것 하나만 넣는다. 애매하면 빈 배열로 둔다.
route가 student_review이면 분류는 '강의평'이거나 빈 배열이어야 한다.

출력은 지정된 JSON만 반환한다."""


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["search", "clarify", "reject"]},
        "standalone_query": {"type": ["string", "null"]},
        "route": {"type": ["string", "null"]},
        "category_candidates": {"type": "array", "items": {"type": "string"}},
        "temporal_constraint": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["none", "explicit", "latest"]},
                "year": {"type": ["integer", "null"]},
                "semester": {"type": ["string", "null"]},
            },
            "required": ["mode", "year", "semester"],
            "additionalProperties": False,
        },
        "clarifying_question": {"type": ["string", "null"]},
        "clarification_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["label", "query"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "action", "standalone_query", "route", "category_candidates",
        "temporal_constraint", "clarifying_question", "clarification_candidates",
    ],
    "additionalProperties": False,
}


def _coerce(raw: dict[str, Any], question: str) -> SearchPlan:
    action = raw.get("action")
    if action not in ("search", "clarify", "reject"):
        action = "search"

    temporal_raw = raw.get("temporal_constraint") or {}
    mode = temporal_raw.get("mode")
    if mode not in ("none", "explicit", "latest"):
        mode = "none"
    year = temporal_raw.get("year")
    temporal = TemporalConstraint(
        mode=mode,
        year=int(year) if isinstance(year, (int, float)) else None,
        semester=temporal_raw.get("semester") or None,
    )

    candidates = []
    for item in raw.get("clarification_candidates") or []:
        label = str(item.get("label") or "").strip()
        query = str(item.get("query") or "").strip()
        if label and query:
            candidates.append(ClarificationCandidate(label=label, query=query))

    query = str(raw.get("standalone_query") or "").strip()
    # 계획기가 질의를 비워 보내도 검색은 계속돼야 한다.
    if action == "search" and not query:
        query = question.strip()

    return SearchPlan(
        action=action,
        standalone_query=query,
        route=raw.get("route") or None,
        category_candidates=[c for c in (raw.get("category_candidates") or []) if c in CATEGORIES],
        temporal_constraint=temporal,
        clarification_candidates=candidates[:4],
        clarifying_question=(raw.get("clarifying_question") or None),
    )


def plan_to_filters(plan: SearchPlan) -> dict[str, Any]:
    """계획을 Chroma where 절로 바꾼다.

    분류(category)는 필터로 걸지 않는다.
    300문항 측정 결과, 분류를 '완벽하게' 맞혔을 때의 Recall@5 상한이 0.803 인데
    필터를 아예 안 걸면 0.740 이다. 즉 잘 맞혀도 이득은 6.3pp 뿐이다.
    반면 틀리면 정답 문서가 후보에서 통째로 빠진다.

    연도만 필터로 쓴다. 이건 사용자가 명시했을 때만 걸리므로 위험이 낮다.
    """
    if plan.temporal_constraint.mode == "explicit" and plan.temporal_constraint.year:
        return {"published_year": plan.temporal_constraint.year}
    return {}


def plan_search(provider, session, question: str, today: str | None = None) -> SearchPlan:
    """provider 는 chat_json(system, user, schema) 을 제공해야 한다."""
    today = today or date.today().isoformat()
    history = session.to_prompt_block() if session else ""
    user = f"{history}\n[현재 질문]\n{question}".strip()

    try:
        raw = provider.chat_json(
            system=build_system(today),
            user=user,
            schema=RESPONSE_SCHEMA,
            schema_name="search_plan",
        )
    except Exception:
        # 계획기가 실패해도 검색 자체는 되어야 한다. 원문으로 검색한다.
        return SearchPlan(action="search", standalone_query=question.strip())

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return SearchPlan(action="search", standalone_query=question.strip())

    return _coerce(raw or {}, question)
