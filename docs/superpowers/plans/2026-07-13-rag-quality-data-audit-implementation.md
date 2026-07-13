# RAG Quality and Data Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 30개 평가 기대값을 유지한 채 RAG 품질을 30/30으로 높이고, 부분 수집 원본 보호와 재현 가능한 데이터 감사 보고서를 추가한다.

**Architecture:** `QueryIntent`가 질문의 기간·최근성·제목 비교 단어를 결정적으로 추출하고, `EvidencePolicy`가 최신 Chroma 후보를 기간·제목 규칙으로 검증한다. 데이터 감사는 런타임 RAG와 분리된 순수 집계 계층과 CLI로 구성하며, 평가·감사 보고서는 공용 원자적 writer를 사용한다.

**Tech Stack:** Python 3.11+, FastAPI/Pydantic, ChromaDB, pytest, Ruff, JSON/Markdown, Next.js 15 검증 도구

---

## 작업 전제와 파일 지도

- 설계 기준: `docs/superpowers/specs/2026-07-13-rag-quality-data-audit-design.md`
- 평가 기대값 `data/evaluation/questions.json`은 수정하지 않는다.
- production code를 수정하기 전에 각 task의 RED 테스트를 먼저 실행한다.
- `data/evaluation/reports/`, `data/audit/reports/`, `data/raw/candidates/`, `chroma_db/`는 생성물이며 Git에 포함하지 않는다.

| 파일 | 최종 책임 |
| --- | --- |
| `backend/app/topic_rules.py` | 주제, evidence marker, recency/generic/alias 정책 로딩 |
| `backend/app/query_intent.py` | 질문의 연도·학기·최근성·제목 비교 단어 추출 |
| `backend/app/evidence_policy.py` | 후보의 기간·제목 적합성 판정 |
| `backend/app/rag.py` | 최신 URL 선택, 의미 재정렬, evidence gate 연결 |
| `backend/app/reporting.py` | JSON/Markdown 쌍의 stage·backup·commit·rollback |
| `backend/app/data_audit.py` | 데이터 품질 집계 모델과 Markdown 렌더링 |
| `backend/scripts/crawl.py` | 운영 원본과 부분 수집 후보 출력 분리 |
| `backend/scripts/evaluate.py` | 기존 평가 보고서를 공용 writer로 기록 |
| `backend/scripts/audit_data.py` | 데이터 감사 인자, 보고서 기록, exit 0/1/2 |
| `data/topic_rules.json` | 사람이 관리하는 evidence marker와 동의어 |

### Task 1: 검색 정책 설정 모델과 엄격한 로딩

**Files:**
- Modify: `backend/app/topic_rules.py`
- Modify: `backend/tests/test_topic_rules.py`

- [x] **Step 1: 정책 로딩 RED 테스트 작성**

`backend/tests/test_topic_rules.py`에 다음 테스트를 추가한다.

```python
def test_catalog_loads_evidence_markers_and_retrieval_policy(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "retrieval_policy": {
                    "recency_terms": ["최근", "최신"],
                    "generic_terms": ["공지", "알려줘"],
                    "alias_groups": [["채용", "초빙"]],
                },
                "topics": [
                    {
                        "key": "career",
                        "label": "진로·취업",
                        "keywords": ["채용"],
                        "evidence_markers": ["초빙"],
                        "suggested_questions": [],
                    },
                    {
                        "key": "general",
                        "label": "전체 공지",
                        "keywords": [],
                        "suggested_questions": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    catalog = load_topic_catalog(path)

    assert catalog.rule_for("career").evidence_markers == ("초빙",)
    assert catalog.retrieval_policy.recency_terms == ("최근", "최신")
    assert catalog.retrieval_policy.alias_groups == (("채용", "초빙"),)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "default_topic_key": "general",
                "retrieval_policy": {"alias_groups": [["채용"]]},
                "topics": [
                    {"key": "general", "label": "전체", "keywords": []}
                ],
            },
            "alias group",
        ),
        (
            {
                "default_topic_key": "general",
                "topics": [
                    {"key": "general", "label": "전체", "keywords": []},
                    {"key": "general", "label": "중복", "keywords": []},
                ],
            },
            "중복 topic key",
        ),
    ],
)
def test_catalog_rejects_invalid_policy(tmp_path, payload, message) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_topic_catalog(path)
```

- [x] **Step 2: RED 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_topic_rules.py -q
```

Expected: `TopicRule`에 `evidence_markers`가 없거나 `TopicCatalog`에 `retrieval_policy`가 없어 FAIL.

- [x] **Step 3: 최소 설정 모델 구현**

`backend/app/topic_rules.py`의 dataclass와 loader를 다음 계약으로 갱신한다. 기존 `rule_for()`와 `classify()`의 동작은 유지한다.

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetrievalPolicy:
    recency_terms: tuple[str, ...] = ()
    generic_terms: tuple[str, ...] = ()
    alias_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class TopicRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    suggested_questions: tuple[str, ...]
    evidence_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class TopicCatalog:
    default_topic_key: str
    rules: tuple[TopicRule, ...]
    retrieval_policy: RetrievalPolicy = field(default_factory=RetrievalPolicy)

    def rule_for(self, key: str) -> TopicRule | None:
        return next((rule for rule in self.rules if rule.key == key), None)

    def classify(self, text: str) -> TopicRule:
        normalized = " ".join(text.casefold().split())
        matches: list[tuple[int, int, TopicRule]] = []
        for order, rule in enumerate(self.rules):
            for keyword in rule.keywords:
                normalized_keyword = " ".join(keyword.casefold().split())
                if normalized_keyword and normalized_keyword in normalized:
                    matches.append((len(normalized_keyword), -order, rule))
        if matches:
            return max(matches, key=lambda item: (item[0], item[1]))[2]
        default = self.rule_for(self.default_topic_key)
        if default is None:
            raise ValueError("default_topic_key에 해당하는 규칙이 없습니다.")
        return default


def _clean_strings(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name}은 문자열 배열이어야 합니다.")
    cleaned = tuple(str(item).strip() for item in value)
    if any(not item for item in cleaned):
        raise ValueError(f"{field_name}에는 빈 문자열을 둘 수 없습니다.")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name}에는 중복 값을 둘 수 없습니다.")
    return cleaned


def _load_retrieval_policy(value: object) -> RetrievalPolicy:
    if value is None:
        return RetrievalPolicy()
    if not isinstance(value, dict):
        raise ValueError("retrieval_policy는 객체여야 합니다.")
    raw_groups = value.get("alias_groups", [])
    if not isinstance(raw_groups, list):
        raise ValueError("alias_groups는 문자열 배열의 배열이어야 합니다.")
    groups: list[tuple[str, ...]] = []
    for index, group in enumerate(raw_groups):
        cleaned = _clean_strings(group, f"alias group {index}")
        if len(cleaned) < 2:
            raise ValueError("alias group은 서로 다른 표현을 2개 이상 포함해야 합니다.")
        groups.append(cleaned)
    return RetrievalPolicy(
        recency_terms=_clean_strings(value.get("recency_terms", []), "recency_terms"),
        generic_terms=_clean_strings(value.get("generic_terms", []), "generic_terms"),
        alias_groups=tuple(groups),
    )


def load_topic_catalog(path: Path) -> TopicCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise ValueError("주제 규칙은 topics 배열을 포함해야 합니다.")
    topic_items = payload["topics"]
    keys = [str(item.get("key", "")).strip() for item in topic_items if isinstance(item, dict)]
    if len(keys) != len(topic_items) or any(not key for key in keys):
        raise ValueError("모든 topic은 비어 있지 않은 key를 포함해야 합니다.")
    if len(keys) != len(set(keys)):
        raise ValueError("중복 topic key가 있습니다.")
    rules = tuple(
        TopicRule(
            key=str(item["key"]).strip(),
            label=str(item["label"]).strip(),
            keywords=_clean_strings(item.get("keywords", []), f"{item['key']}.keywords"),
            suggested_questions=_clean_strings(
                item.get("suggested_questions", []),
                f"{item['key']}.suggested_questions",
            ),
            evidence_markers=_clean_strings(
                item.get("evidence_markers", []),
                f"{item['key']}.evidence_markers",
            ),
        )
        for item in topic_items
    )
    catalog = TopicCatalog(
        default_topic_key=str(payload.get("default_topic_key", "general")).strip(),
        rules=rules,
        retrieval_policy=_load_retrieval_policy(payload.get("retrieval_policy")),
    )
    if catalog.rule_for(catalog.default_topic_key) is None:
        raise ValueError("default_topic_key에 해당하는 규칙이 없습니다.")
    return catalog
```

- [x] **Step 4: GREEN과 전체 관련 테스트 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_topic_rules.py backend/tests/test_topic_classifier.py backend/tests/test_recommendations.py -q
backend/.venv/Scripts/python -m ruff check backend/app/topic_rules.py backend/tests/test_topic_rules.py
```

Expected: 모든 테스트와 Ruff exit 0.

- [x] **Step 5: 커밋**

```bash
git add backend/app/topic_rules.py backend/tests/test_topic_rules.py
git commit -m "feat: validate retrieval evidence policy"
```

> 2026-07-13 중단 기록: Task 1 구현 커밋 `4093c94`, 관련 9개와 전체 backend 60개 테스트, Ruff, 명세 리뷰를 통과했다. 코드 품질 리뷰는 사용자 요청으로 실행 중 종료했으므로 재개 시 새 검토자로 다시 수행한다. 상세 진입점은 `docs/superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md`를 따른다.

### Task 2: 질문 의도 분석

**Files:**
- Create: `backend/app/query_intent.py`
- Create: `backend/tests/test_query_intent.py`

- [ ] **Step 1: QueryIntent RED 테스트 작성**

```python
from backend.app.query_intent import analyze_query
from backend.app.topic_rules import RetrievalPolicy, TopicCatalog, TopicRule


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        retrieval_policy=RetrievalPolicy(
            recency_terms=("최근", "최신"),
            generic_terms=("공지", "알려줘", "찾아줘", "언제"),
            alias_groups=(("채용", "초빙"),),
        ),
        rules=(
            TopicRule("career", "진로·취업", ("채용", "취업"), (), ("초빙",)),
            TopicRule("capstone", "캡스톤", ("캡스톤디자인", "캡스톤 디자인"), ()),
            TopicRule("registration", "수강신청", ("수강신청", "수강 신청"), ()),
            TopicRule("general", "전체", (), ()),
        ),
    )


def test_analyze_query_extracts_year_and_academic_term() -> None:
    rules = catalog()
    topic = rules.rule_for("capstone")
    assert topic is not None

    intent = analyze_query(
        "2026학년도 2학기 캡스톤디자인 공지를 알려줘",
        topic=topic,
        catalog=rules,
    )

    assert intent.topic_key == "capstone"
    assert intent.requested_year == 2026
    assert intent.requested_term == "second"
    assert intent.recency_requested is False


def test_analyze_query_expands_alias_terms_for_title_matching() -> None:
    rules = catalog()
    topic = rules.rule_for("career")
    assert topic is not None

    intent = analyze_query("최근 채용 공지를 찾아줘", topic=topic, catalog=rules)

    assert intent.recency_requested is True
    assert "채용" in intent.match_terms
    assert "초빙" in intent.match_terms


def test_analyze_query_keeps_only_distinctive_terms() -> None:
    rules = catalog()
    topic = rules.rule_for("registration")
    assert topic is not None

    intent = analyze_query("수강 신청 기간은 언제야?", topic=topic, catalog=rules)

    assert "기간" in intent.distinctive_terms
    assert "수강" not in intent.distinctive_terms
    assert "신청" not in intent.distinctive_terms
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_query_intent.py -q
```

Expected: `backend.app.query_intent` import 오류로 FAIL.

- [ ] **Step 3: 결정적 parser 구현**

`backend/app/query_intent.py`를 다음 내용으로 만든다.

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from backend.app.topic_rules import TopicCatalog, TopicRule

AcademicTerm = Literal["first", "second", "summer", "winter"]
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:학년도|년)?(?!\d)")
TERM_PATTERNS: tuple[tuple[AcademicTerm, re.Pattern[str]], ...] = (
    ("summer", re.compile(r"여름\s*계절(?:학기|수업)?")),
    ("winter", re.compile(r"겨울\s*계절(?:학기|수업)?")),
    ("first", re.compile(r"1\s*학기")),
    ("second", re.compile(r"2\s*학기")),
)
PARTICLES = ("으로", "에서", "까지", "부터", "에게", "한테", "처럼", "보다", "으로", "로", "을", "를", "은", "는", "이", "가", "의", "와", "과", "도", "에")


@dataclass(frozen=True)
class QueryIntent:
    topic_key: str
    requested_year: int | None
    requested_term: AcademicTerm | None
    recency_requested: bool
    match_terms: tuple[str, ...]
    distinctive_terms: tuple[str, ...]


def compact(value: str) -> str:
    return "".join(TOKEN_PATTERN.findall(value.casefold()))


def extract_year(value: str) -> int | None:
    match = YEAR_PATTERN.search(value)
    return int(match.group(1)) if match else None


def extract_term(value: str) -> AcademicTerm | None:
    for term, pattern in TERM_PATTERNS:
        if pattern.search(value):
            return term
    return None


def _strip_particle(token: str) -> str:
    for particle in PARTICLES:
        if len(token) > len(particle) + 1 and token.endswith(particle):
            return token[: -len(particle)]
    return token


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for token in TOKEN_PATTERN.findall(value.casefold())
        if len(normalized := _strip_particle(token)) >= 2
    )


def _phrase_tokens(values: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    for value in values:
        result.update(_tokens(value))
        normalized = compact(value)
        if normalized:
            result.add(normalized)
    return result


def analyze_query(
    question: str,
    *,
    topic: TopicRule,
    catalog: TopicCatalog,
) -> QueryIntent:
    policy = catalog.retrieval_policy
    normalized_question = compact(question)
    raw_tokens = set(_tokens(question))
    match_terms = set(raw_tokens)
    match_terms.add(normalized_question)
    for group in policy.alias_groups:
        if any(compact(value) in normalized_question for value in group):
            match_terms.update(compact(value) for value in group)

    ignored = _phrase_tokens(
        topic.keywords + policy.recency_terms + policy.generic_terms
    )
    year = extract_year(question)
    term = extract_term(question)
    distinctive = {
        token
        for token in raw_tokens
        if token not in ignored
        and not token.isdigit()
        and token not in {"학년도", "학기", "여름계절", "겨울계절"}
    }
    return QueryIntent(
        topic_key=topic.key,
        requested_year=year,
        requested_term=term,
        recency_requested=any(compact(value) in normalized_question for value in policy.recency_terms),
        match_terms=tuple(sorted(match_terms)),
        distinctive_terms=tuple(sorted(distinctive)),
    )
```

- [ ] **Step 4: GREEN과 경계값 확인**

계절학기 테스트를 하나 더 추가한다.

```python
def test_analyze_query_distinguishes_summer_term() -> None:
    rules = catalog()
    topic = rules.rule_for("registration")
    assert topic is not None

    intent = analyze_query("2026학년도 여름계절수업 안내", topic=topic, catalog=rules)

    assert intent.requested_year == 2026
    assert intent.requested_term == "summer"
```

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_query_intent.py -q
backend/.venv/Scripts/python -m ruff check backend/app/query_intent.py backend/tests/test_query_intent.py
```

Expected: 4 tests와 Ruff exit 0.

- [ ] **Step 5: 커밋**

```bash
git add backend/app/query_intent.py backend/tests/test_query_intent.py
git commit -m "feat: analyze rag query intent"
```

### Task 3: 기간·제목 근거 정책

**Files:**
- Create: `backend/app/evidence_policy.py`
- Create: `backend/tests/test_evidence_policy.py`

- [ ] **Step 1: EvidencePolicy RED 테스트 작성**

```python
from backend.app.domain import RetrievedChunk, TextChunk
from backend.app.evidence_policy import decide_evidence
from backend.app.query_intent import QueryIntent
from backend.app.topic_rules import RetrievalPolicy, TopicCatalog, TopicRule


def chunk(title: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id="kumoh:1:0",
            post_id="1",
            source="kumoh",
            title=title,
            text="본문은 근거 적합성 1차 판정에 사용하지 않습니다.",
            url="https://example.com/1",
            published_at="2026-03-19",
            chunk_index=0,
            topic_key="capstone",
            topic_label="캡스톤",
            is_latest_topic=True,
        ),
        score=0.9,
    )


def policy_catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        retrieval_policy=RetrievalPolicy(alias_groups=(("채용", "초빙"),)),
        rules=(
            TopicRule("capstone", "캡스톤", ("캡스톤",), (), ("캡스톤",)),
            TopicRule("career", "진로", ("채용",), (), ("초빙",)),
            TopicRule("general", "전체", (), ()),
        ),
    )


def intent(**updates) -> QueryIntent:
    values = {
        "topic_key": "capstone",
        "requested_year": None,
        "requested_term": None,
        "recency_requested": False,
        "match_terms": ("캡스톤",),
        "distinctive_terms": (),
    }
    values.update(updates)
    return QueryIntent(**values)


def test_rejects_conflicting_semester() -> None:
    catalog = policy_catalog()
    rule = catalog.rule_for("capstone")
    assert rule is not None

    decision = decide_evidence(
        intent(requested_year=2026, requested_term="second"),
        topic=rule,
        catalog=catalog,
        item=chunk("2026학년도 1학기 캡스톤 디자인 운영 계획"),
    )

    assert decision.accepted is False
    assert decision.reason == "semester_mismatch"


def test_accepts_alias_connected_title_marker() -> None:
    catalog = policy_catalog()
    rule = catalog.rule_for("career")
    assert rule is not None

    decision = decide_evidence(
        intent(
            topic_key="career",
            recency_requested=True,
            match_terms=("채용", "초빙"),
        ),
        topic=rule,
        catalog=catalog,
        item=chunk("2026년 하반기 전임교원 초빙 공개강의 심사 공고"),
    )

    assert decision.accepted is True
    assert decision.reason == "accepted_topic_marker"


def test_rejects_unrelated_latest_topic_title() -> None:
    catalog = policy_catalog()
    rule = TopicRule("scholarship", "장학", ("장학",), (), ("장학",))

    decision = decide_evidence(
        intent(
            topic_key="scholarship",
            match_terms=("장학금", "신청"),
            distinctive_terms=("신청",),
        ),
        topic=rule,
        catalog=catalog,
        item=chunk("방산AI인재양성부트캠프사업단 설명회 안내"),
    )

    assert decision.accepted is False
    assert decision.reason == "insufficient_title_evidence"


def test_accepts_single_strong_distinctive_title_term() -> None:
    catalog = policy_catalog()
    rule = catalog.rule_for("general")
    assert rule is not None

    decision = decide_evidence(
        intent(
            topic_key="general",
            match_terms=("소프트웨어전공",),
            distinctive_terms=("소프트웨어전공",),
        ),
        topic=rule,
        catalog=catalog,
        item=chunk("소프트웨어전공 전임교원 초빙 공개강의 심사 공고"),
    )

    assert decision.accepted is True
    assert decision.reason == "accepted_title_overlap"
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evidence_policy.py -q
```

Expected: `backend.app.evidence_policy` import 오류로 FAIL.

- [ ] **Step 3: 최소 evidence decision 구현**

```python
from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain import RetrievedChunk
from backend.app.query_intent import QueryIntent, compact, extract_term, extract_year
from backend.app.topic_rules import TopicCatalog, TopicRule


@dataclass(frozen=True)
class EvidenceDecision:
    accepted: bool
    reason: str


def _matches_marker(intent: QueryIntent, marker: str, title: str) -> bool:
    normalized_marker = compact(marker)
    normalized_title = compact(title)
    if not normalized_marker or normalized_marker not in normalized_title:
        return False
    return any(
        normalized_marker in term or term in normalized_marker
        for term in intent.match_terms
        if len(term) >= 2
    )


def decide_evidence(
    intent: QueryIntent,
    *,
    topic: TopicRule,
    catalog: TopicCatalog,
    item: RetrievedChunk,
) -> EvidenceDecision:
    title = item.chunk.title
    title_year = extract_year(title)
    title_term = extract_term(title)
    if intent.requested_year is not None:
        if title_year is None:
            return EvidenceDecision(False, "missing_temporal_evidence")
        if title_year != intent.requested_year:
            return EvidenceDecision(False, "year_mismatch")
    if intent.requested_term is not None:
        if title_term is None:
            return EvidenceDecision(False, "missing_temporal_evidence")
        if title_term != intent.requested_term:
            return EvidenceDecision(False, "semester_mismatch")

    if intent.topic_key == catalog.default_topic_key and intent.recency_requested:
        return EvidenceDecision(True, "accepted_general_latest")

    if any(_matches_marker(intent, marker, title) for marker in topic.evidence_markers):
        return EvidenceDecision(True, "accepted_topic_marker")

    normalized_title = compact(title)
    overlaps = {
        term
        for term in intent.distinctive_terms
        if len(term) >= 2 and compact(term) in normalized_title
    }
    if len(overlaps) >= 2 or any(len(compact(term)) >= 5 for term in overlaps):
        return EvidenceDecision(True, "accepted_title_overlap")
    return EvidenceDecision(False, "insufficient_title_evidence")
```

- [ ] **Step 4: GREEN과 날짜 누락 경계값 확인**

다음 테스트를 추가한다.

```python
def test_requires_explicit_title_date_for_specific_period() -> None:
    catalog = policy_catalog()
    rule = catalog.rule_for("capstone")
    assert rule is not None

    decision = decide_evidence(
        intent(requested_year=2026, requested_term="first"),
        topic=rule,
        catalog=catalog,
        item=chunk("캡스톤 디자인 운영 계획"),
    )

    assert decision.reason == "missing_temporal_evidence"
```

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evidence_policy.py -q
backend/.venv/Scripts/python -m ruff check backend/app/evidence_policy.py backend/tests/test_evidence_policy.py
```

Expected: 5 tests와 Ruff exit 0.

- [ ] **Step 5: 커밋**

```bash
git add backend/app/evidence_policy.py backend/tests/test_evidence_policy.py
git commit -m "feat: validate rag evidence relevance"
```

### Task 4: RAG 연결과 평가 실패 5건 회귀

**Files:**
- Modify: `backend/app/rag.py`
- Modify: `backend/tests/test_rag.py`
- Modify: `data/topic_rules.json`

- [ ] **Step 1: 실패 5건을 표현하는 RAG RED 테스트 작성**

`backend/tests/test_rag.py`에 `pytest`, `RetrievalPolicy` import와 다음 helper·테스트를 추가한다.

```python
import pytest

from backend.app.topic_rules import RetrievalPolicy


def hardening_catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        retrieval_policy=RetrievalPolicy(
            recency_terms=("최근", "최신"),
            generic_terms=("공지", "알려줘", "찾아줘", "언제"),
            alias_groups=(
                ("개설강좌", "개설 과목", "수강 가능 과목", "수강신청 안내"),
                ("채용", "초빙"),
            ),
        ),
        rules=(
            TopicRule("course_openings", "개설", ("개설강좌", "개설 과목"), (), ("수강신청 안내",)),
            TopicRule("registration", "수강", ("수강신청", "수강 신청", "수강변경"), (), ("수강신청", "수강변경")),
            TopicRule("capstone", "캡스톤", ("캡스톤디자인", "캡스톤 디자인"), (), ("캡스톤디자인", "캡스톤 디자인")),
            TopicRule("career", "진로", ("취업", "채용", "인턴", "진로"), (), ("취업", "채용", "초빙", "인턴", "진로")),
            TopicRule("scholarship", "장학", ("장학금", "장학생", "장학"), (), ("장학금", "장학생", "장학")),
            TopicRule("general", "전체", (), ()),
        ),
    )


def policy_result(
    *, title: str, topic_key: str, published_at: str, score: float
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id="kumoh:policy:0",
            post_id="policy",
            source="kumoh",
            title=title,
            text=f"제목: {title}\n본문: 테스트 내용",
            url="https://example.com/policy",
            published_at=published_at,
            chunk_index=0,
            topic_key=topic_key,
            topic_label=topic_key,
            is_latest_topic=True,
        ),
        score=score,
    )


def policy_post(title: str, topic_key: str, published_at: str) -> BoardPost:
    return BoardPost(
        id="policy",
        source="kumoh",
        title=title,
        content="테스트 내용",
        url="https://example.com/policy",
        published_at=published_at,
        crawled_at=datetime(2026, 7, 1, tzinfo=UTC),
        topic_key=topic_key,
        topic_label=topic_key,
        is_latest_topic=True,
    )


@pytest.mark.parametrize(
    ("question", "topic_key", "title", "published_at"),
    [
        (
            "수강 신청 기간은 언제야?",
            "registration",
            "[수업] 2026학년도 여름계절수업 조기취업자 출석인정신청 안내",
            "2026-06-16",
        ),
        (
            "2026학년도 2학기 캡스톤디자인 공지를 알려줘",
            "capstone",
            "2026학년도 1학기 캡스톤 디자인 운영 계획 안내",
            "2026-03-19",
        ),
        (
            "장학금 신청 공지를 알려줘",
            "scholarship",
            "방산AI인재양성부트캠프사업단 소개 및 설명회 안내",
            "2026-06-17",
        ),
    ],
)
def test_rag_rejects_latest_document_that_does_not_answer_question(
    question: str, topic_key: str, title: str, published_at: str
) -> None:
    provider = FakeProvider()
    store = FakeStore(
        [policy_result(title=title, topic_key=topic_key, published_at=published_at, score=0.8)]
    )
    service = RAGService(
        provider=provider,
        vector_store=store,  # type: ignore[arg-type]
        topic_catalog=hardening_catalog(),
        posts=[policy_post(title, topic_key, published_at)],
        min_score=0.09,
    )

    result = service.ask(question)

    assert result.grounded is False
    assert result.sources == []
    assert provider.answer_called is False


def test_rag_uses_alias_to_recover_latest_recruitment_notice() -> None:
    title = "2026년 하반기 소프트웨어전공 전임교원 초빙 공개강의 심사 공고"
    provider = FakeProvider()
    store = FakeStore(
        [policy_result(title=title, topic_key="career", published_at="2026-06-30", score=0.0)]
    )
    service = RAGService(
        provider=provider,
        vector_store=store,  # type: ignore[arg-type]
        topic_catalog=hardening_catalog(),
        posts=[policy_post(title, "career", "2026-06-30")],
        min_score=0.09,
    )

    result = service.ask("최근 채용 공지를 찾아줘")

    assert result.grounded is True
    assert result.sources[0].title == title


def test_rag_prefers_date_for_general_latest_notice_even_with_zero_score() -> None:
    title = "2026년 하반기 소프트웨어전공 전임교원 초빙 공개강의 심사 공고"
    provider = FakeProvider()
    store = FakeStore(
        [policy_result(title=title, topic_key="career", published_at="2026-06-30", score=0.0)]
    )
    service = RAGService(
        provider=provider,
        vector_store=store,  # type: ignore[arg-type]
        topic_catalog=hardening_catalog(),
        posts=[policy_post(title, "career", "2026-06-30")],
        min_score=0.09,
    )

    result = service.ask("최근 학과 공지를 알려줘")

    assert result.grounded is True
    assert result.sources[0].published_at == "2026-06-30"
    assert store.last_where == {
        "$and": [
            {"is_latest_topic": True},
            {"url": "https://example.com/policy"},
        ]
    }
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_rag.py -q
backend/.venv/Scripts/python -m backend.scripts.evaluate
```

Expected: pytest에서 false-positive 3건은 현재 `grounded=True`, false-negative 2건은 `grounded=False` 또는 URL filter 불일치로 FAIL. 실제 평가는 quality exit 1, 30건 중 25건 통과와 기존 실패 ID 5개를 보고한다.

- [ ] **Step 3: RAG에 intent와 evidence gate 연결**

`backend/app/rag.py`에 다음 import와 helper를 추가하고 `ask()`를 교체한다.

```python
from backend.app.evidence_policy import decide_evidence
from backend.app.freshness import freshness_key
from backend.app.query_intent import QueryIntent, analyze_query, compact


    @staticmethod
    def _rerank(
        question: str,
        items: list[RetrievedChunk],
        intent: QueryIntent | None = None,
    ) -> list[RetrievedChunk]:
        terms = {
            term.lower()
            for term in re.findall(r"[0-9A-Za-z가-힣]{2,}", question)
            if term.lower() not in QUERY_STOP_WORDS
        }
        match_terms = intent.match_terms if intent else ()
        reranked: list[RetrievedChunk] = []
        for item in items:
            normalized_title = compact(item.chunk.title)
            lexical_hits = sum(1 for term in terms if compact(term) in normalized_title)
            policy_hits = sum(
                1
                for term in match_terms
                if 2 <= len(term) <= len(normalized_title) and term in normalized_title
            )
            boost = 0.08 * lexical_hits + min(0.24, 0.12 * policy_hits)
            reranked.append(
                item.model_copy(update={"score": min(1.0, item.score + boost)})
            )
        return sorted(reranked, key=lambda item: item.score, reverse=True)

    def _general_latest_url(self) -> str | None:
        latest = [post for post in self.posts if post.is_latest_topic]
        if not latest:
            return None
        return max(latest, key=freshness_key).url

    def ask(self, question: str) -> ChatResponse:
        topic = self.topic_catalog.classify(question) if self.topic_catalog else None
        intent = (
            analyze_query(question, topic=topic, catalog=self.topic_catalog)
            if topic is not None and self.topic_catalog is not None
            else None
        )
        query_embedding = self.provider.embed([question])[0]
        where = None
        if topic is not None and self.topic_catalog is not None:
            where_parts: list[dict[str, object]] = [{"is_latest_topic": True}]
            if topic.key != self.topic_catalog.default_topic_key:
                where_parts.append({"topic_key": topic.key})
            elif intent is not None and intent.recency_requested:
                latest_url = self._general_latest_url()
                if latest_url is not None:
                    where_parts.append({"url": latest_url})
            where = where_parts[0] if len(where_parts) == 1 else {"$and": where_parts}

        retrieved = self._rerank(
            question,
            self.vector_store.query(query_embedding, self.top_k, where=where),
            intent,
        )
        policy_enabled = bool(
            topic is not None
            and self.topic_catalog is not None
            and intent is not None
            and (
                topic.evidence_markers
                or self.topic_catalog.retrieval_policy.recency_terms
                or self.topic_catalog.retrieval_policy.alias_groups
            )
        )
        accepted: list[tuple[RetrievedChunk, str]] = []
        for item in retrieved:
            if not policy_enabled:
                accepted.append((item, "legacy"))
                continue
            decision = decide_evidence(
                intent,
                topic=topic,
                catalog=self.topic_catalog,
                item=item,
            )
            if decision.accepted:
                accepted.append((item, decision.reason))

        candidates = [
            item
            for item, reason in accepted
            if item.score >= self.min_score or reason == "accepted_general_latest"
        ]
        best_score = max((item.score for item in candidates), default=0.0)
        relevant = [
            item
            for item in candidates
            if best_score == 0.0 or item.score >= best_score * 0.75
        ]
        suggestions = suggested_questions(self.topic_catalog, topic.key) if topic else []
        notices = recent_notices(self.posts, topic.key, self.topic_catalog) if topic else []
        if not relevant:
            return ChatResponse(
                answer=NO_ANSWER,
                sources=[],
                grounded=False,
                suggested_questions=suggestions,
                recent_notices=notices,
            )
        answer = self.provider.answer(question, relevant)
        return ChatResponse(
            answer=answer,
            sources=self._sources(relevant),
            grounded=True,
            suggested_questions=suggestions,
            recent_notices=notices,
        )
```

- [ ] **Step 4: 사람이 관리하는 실제 정책 값 추가**

`data/topic_rules.json`을 다음 완전한 구조로 갱신한다.

```json
{
  "default_topic_key": "general",
  "retrieval_policy": {
    "recency_terms": ["최근", "최신"],
    "generic_terms": ["공지", "안내", "알려줘", "찾아줘", "관련", "방법", "뭐야", "무엇", "어디서", "확인", "있어", "있나요", "언제", "이번", "학기"],
    "alias_groups": [
      ["개설강좌", "개설 과목", "수강 가능 과목", "수강신청 안내"],
      ["채용", "초빙"],
      ["수강변경", "수강 변경"],
      ["캡스톤디자인", "캡스톤 디자인"]
    ]
  },
  "topics": [
    {
      "key": "course_openings",
      "label": "개설강좌조회",
      "keywords": ["개설강좌", "개설 과목", "수강 가능 과목"],
      "evidence_markers": ["수강신청 안내"],
      "suggested_questions": ["이번 학기 개설강좌를 알려줘", "개설강좌 조회 방법은?"]
    },
    {
      "key": "registration",
      "label": "수강신청",
      "keywords": ["수강신청", "수강 신청", "수강변경"],
      "evidence_markers": ["수강신청", "수강변경"],
      "suggested_questions": ["수강신청 기간은 언제야?", "수강신청 변경 방법은?"]
    },
    {
      "key": "capstone",
      "label": "캡스톤디자인",
      "keywords": ["캡스톤디자인", "캡스톤 디자인"],
      "evidence_markers": ["캡스톤디자인", "캡스톤 디자인"],
      "suggested_questions": ["캡스톤디자인 신청 방법은?", "캡스톤디자인 일정은?"]
    },
    {
      "key": "career",
      "label": "진로·취업",
      "keywords": ["취업", "채용", "인턴", "진로"],
      "evidence_markers": ["취업", "채용", "초빙", "인턴", "진로"],
      "suggested_questions": ["최근 취업 프로그램을 알려줘", "인턴 관련 공지가 있어?"]
    },
    {
      "key": "scholarship",
      "label": "장학금",
      "keywords": ["장학금", "장학생", "장학"],
      "evidence_markers": ["장학금", "장학생", "장학"],
      "suggested_questions": ["장학금 신청 공지를 알려줘", "장학생 선발 기준은?"]
    },
    {
      "key": "graduation",
      "label": "졸업요건",
      "keywords": ["졸업요건", "졸업 요건", "졸업인증"],
      "evidence_markers": ["졸업요건", "졸업 요건", "졸업인증"],
      "suggested_questions": ["졸업요건을 확인해줘", "졸업인증 기준은?"]
    },
    {
      "key": "general",
      "label": "전체 공지",
      "keywords": [],
      "evidence_markers": [],
      "suggested_questions": ["최근 학과 공지를 알려줘", "소프트웨어전공 공지를 알려줘"]
    }
  ]
}
```

- [ ] **Step 5: GREEN과 기존 회귀 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_rag.py backend/tests/test_topic_rules.py backend/tests/test_query_intent.py backend/tests/test_evidence_policy.py -q
backend/.venv/Scripts/python -m ruff check backend/app/rag.py backend/app/query_intent.py backend/app/evidence_policy.py
```

Expected: 모든 대상 테스트와 Ruff exit 0. 기존 topic policy가 없는 fixture는 legacy 경로로 계속 통과.

- [ ] **Step 6: 커밋**

```bash
git add backend/app/rag.py backend/tests/test_rag.py data/topic_rules.json
git commit -m "fix: enforce latest rag evidence relevance"
```

### Task 5: 부분 수집 후보와 운영 원본 분리

**Files:**
- Modify: `backend/scripts/crawl.py`
- Create: `backend/tests/test_crawl_script.py`
- Modify: `.gitignore`

- [ ] **Step 1: 운영 원본 보호 RED 테스트 작성**

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.app.config import Settings
from backend.app.domain import BoardPost
from backend.app.storage import load_posts, save_posts
from backend.scripts import crawl


def post(post_id: str, source: str) -> BoardPost:
    return BoardPost(
        id=post_id,
        source=source,
        title=f"{source} 공지",
        content="공개 게시글 내용",
        url=f"https://example.com/{source}/{post_id}",
        published_at="2026-07-01",
        crawled_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def settings(tmp_path: Path) -> Settings:
    return Settings(
        ai_provider="local",
        openai_api_key=None,
        chat_model="local",
        embedding_model="local",
        chroma_path=tmp_path / "chroma",
        chroma_collection="test",
        raw_posts_path=tmp_path / "posts.json",
        topic_rules_path=tmp_path / "topics.json",
        rag_top_k=5,
        rag_min_score=0.09,
        crawler_delay_seconds=0.0,
        crawler_timeout_seconds=1.0,
        seboard_api_url=None,
        seboard_headless=True,
        cors_origins=("http://localhost:3000",),
    )


def test_allow_partial_writes_candidate_without_overwriting_raw_posts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_settings = settings(tmp_path)
    original = post("old", "kumoh")
    save_posts([original], app_settings.raw_posts_path)
    partial_path = tmp_path / "candidates" / "partial.json"

    class GoodKumoh:
        def __init__(self, **_kwargs) -> None:
            pass

        def crawl(self, _limit: int) -> list[BoardPost]:
            return [post("new", "kumoh")]

    class FailedSeBoard:
        def __init__(self, **_kwargs) -> None:
            pass

        def crawl(self, _limit: int) -> list[BoardPost]:
            raise RuntimeError("fixture failure")

    monkeypatch.setattr(crawl, "get_settings", lambda: app_settings)
    monkeypatch.setattr(crawl, "KumohBoardCrawler", GoodKumoh)
    monkeypatch.setattr(crawl, "SeBoardCrawler", FailedSeBoard)

    exit_code = crawl.main(
        [
            "--kumoh-limit", "1",
            "--seboard-limit", "1",
            "--allow-partial",
            "--partial-output", str(partial_path),
        ]
    )

    assert exit_code == 2
    assert [item.id for item in load_posts(app_settings.raw_posts_path)] == ["old"]
    assert [item.id for item in load_posts(partial_path)] == ["new"]


def test_partial_output_cannot_equal_operational_raw_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_settings = settings(tmp_path)
    monkeypatch.setattr(crawl, "get_settings", lambda: app_settings)

    exit_code = crawl.main(
        ["--allow-partial", "--partial-output", str(app_settings.raw_posts_path)]
    )

    assert exit_code == 2
    assert not app_settings.raw_posts_path.exists()
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_crawl_script.py -q
```

Expected: `crawl.main()`이 argv를 받지 못하거나 부분 결과가 운영 raw path에 저장되어 FAIL.

- [ ] **Step 3: crawl CLI 출력 경로 분리 구현**

`backend/scripts/crawl.py`에서 `Path`, `REPOSITORY_ROOT`를 import하고 parser/main을 다음 코드로 바꾼다.

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공개 게시글을 JSON으로 수집합니다.")
    parser.add_argument("--kumoh-limit", type=int, default=50)
    parser.add_argument("--seboard-limit", type=int, default=50)
    parser.add_argument("--allow-partial", action="store_true", help="실패한 수집의 일부 결과를 후보 파일에 저장")
    parser.add_argument(
        "--partial-output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "raw" / "candidates" / "posts-partial.json",
        help="부분 수집 후보 파일 경로",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    if args.allow_partial and args.partial_output.resolve() == settings.raw_posts_path.resolve():
        print("오류 - 부분 수집 후보는 운영 RAW_POSTS_PATH와 달라야 합니다.", file=sys.stderr)
        return 2

    posts: list[BoardPost] = []
    failures: list[str] = []

    if args.kumoh_limit > 0:
        try:
            kumoh = KumohBoardCrawler(
                delay_seconds=settings.crawler_delay_seconds,
                timeout_seconds=settings.crawler_timeout_seconds,
            )
            collected = kumoh.crawl(args.kumoh_limit)
            posts.extend(collected)
            print(f"학과 게시판: {len(collected)}건 수집")
        except Exception as exc:
            failures.append(f"학과 게시판: {exc}")

    if args.seboard_limit > 0:
        try:
            seboard = SeBoardCrawler(
                api_url=settings.seboard_api_url,
                delay_seconds=settings.crawler_delay_seconds,
                timeout_seconds=settings.crawler_timeout_seconds,
                headless=settings.seboard_headless,
            )
            collected = seboard.crawl(args.seboard_limit)
            posts.extend(collected)
            print(f"SE 게시판: {len(collected)}건 수집")
        except Exception as exc:
            failures.append(f"SE 게시판: {exc}")

    posts = deduplicate_posts(posts)
    if posts and not failures:
        save_posts(posts, settings.raw_posts_path)
        print(f"총 {len(posts)}건 저장: {settings.raw_posts_path}")
    elif posts and failures and args.allow_partial:
        save_posts(posts, args.partial_output)
        print(f"부분 수집 후보 {len(posts)}건 저장: {args.partial_output}")

    if failures:
        for failure in failures:
            print(f"오류 - {failure}", file=sys.stderr)
        return 2
    if not posts:
        print("수집된 게시글이 없습니다.", file=sys.stderr)
        return 1
    return 0
```

`.gitignore`에 다음을 추가한다.

```gitignore
data/raw/candidates/
```

- [ ] **Step 4: GREEN과 기존 crawler 테스트 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_crawl_script.py backend/tests/test_kumoh_crawler.py -q
backend/.venv/Scripts/python -m ruff check backend/scripts/crawl.py backend/tests/test_crawl_script.py
git check-ignore -v data/raw/candidates/posts-partial.json
```

Expected: tests/Ruff exit 0, 마지막 명령이 `.gitignore` 규칙을 출력.

- [ ] **Step 5: 커밋**

```bash
git add .gitignore backend/scripts/crawl.py backend/tests/test_crawl_script.py
git commit -m "fix: isolate partial crawl candidates"
```

### Task 6: 평가·감사 공용 원자적 보고서 writer

**Files:**
- Create: `backend/app/reporting.py`
- Create: `backend/tests/test_reporting.py`
- Modify: `backend/scripts/evaluate.py`
- Verify: `backend/tests/test_evaluate_script.py`

- [ ] **Step 1: 공용 writer RED 테스트 작성**

```python
from pathlib import Path

import pytest
from backend.app.reporting import write_text_reports


def test_write_text_reports_replaces_pair(tmp_path: Path) -> None:
    json_path = tmp_path / "latest.json"
    markdown_path = tmp_path / "latest.md"
    json_path.write_text("old json", encoding="utf-8")
    markdown_path.write_text("old markdown", encoding="utf-8")

    write_text_reports(
        ((json_path, "new json\n"), (markdown_path, "new markdown\n")),
        label="테스트 보고서",
    )

    assert json_path.read_text(encoding="utf-8") == "new json\n"
    assert markdown_path.read_text(encoding="utf-8") == "new markdown\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["latest.json", "latest.md"]


def test_write_text_reports_rolls_back_when_second_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    json_path = tmp_path / "latest.json"
    markdown_path = tmp_path / "latest.md"
    json_path.write_text("old json", encoding="utf-8")
    markdown_path.write_text("old markdown", encoding="utf-8")
    original_replace = Path.replace
    failed = False

    def fail_markdown(self: Path, target: Path) -> Path:
        nonlocal failed
        if not failed and self.suffix == ".tmp" and Path(target).name == "latest.md":
            failed = True
            raise OSError("second commit failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_markdown)

    with pytest.raises(OSError, match="second commit failed"):
        write_text_reports(
            ((json_path, "new json"), (markdown_path, "new markdown")),
            label="테스트 보고서",
        )

    assert json_path.read_text(encoding="utf-8") == "old json"
    assert markdown_path.read_text(encoding="utf-8") == "old markdown"
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_reporting.py -q
```

Expected: `backend.app.reporting` import 오류로 FAIL.

- [ ] **Step 3: writer 구현과 evaluate wrapper 전환**

`backend/app/reporting.py`를 만든다.

```python
from __future__ import annotations

from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile


class RollbackFailure(RuntimeError):
    def __init__(
        self,
        failed_target_names: tuple[str, ...],
        failed_backup_paths: tuple[Path, ...],
        cause: OSError,
    ) -> None:
        self.failed_target_names = failed_target_names
        self.failed_backup_paths = failed_backup_paths
        target_names = ", ".join(failed_target_names)
        backup_paths = ", ".join(str(path) for path in failed_backup_paths)
        message = f"{target_names} 복구 실패"
        if backup_paths:
            message += f"; 보존된 백업: {backup_paths}"
        super().__init__(message)
        self.__cause__ = cause


def _cleanup_artifacts(
    paths: list[Path | None], preserve: set[Path] | None = None
) -> OSError | None:
    first_error: OSError | None = None
    preserve = preserve or set()
    for path in paths:
        if path is None or path in preserve:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            first_error = first_error or exc
    return first_error


def _stage_text(target: Path, content: str, *, label: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=str(target.parent),
            suffix=".tmp",
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
    except OSError as exc:
        cleanup_error = _cleanup_artifacts([temporary_path])
        if cleanup_error is not None:
            raise RuntimeError(
                f"{label} 임시 파일 정리에 실패했습니다: {cleanup_error}"
            ) from exc
        raise
    if temporary_path is None:
        raise RuntimeError(f"{label} 임시 파일을 만들지 못했습니다.")
    return temporary_path


def _backup_target(target: Path, *, label: str) -> Path | None:
    if not target.exists():
        return None
    with NamedTemporaryFile(
        mode="wb", delete=False, dir=str(target.parent), suffix=".bak"
    ) as handle:
        backup_path = Path(handle.name)
    try:
        copyfile(target, backup_path)
    except OSError as exc:
        cleanup_error = _cleanup_artifacts([backup_path])
        if cleanup_error is not None:
            raise RuntimeError(
                f"{label} 백업 파일 정리에 실패했습니다: {cleanup_error}"
            ) from exc
        raise
    return backup_path


def _rollback_reports(
    targets: tuple[Path, ...], backups: tuple[Path | None, ...]
) -> None:
    first_error: OSError | None = None
    failed_targets: list[str] = []
    failed_backup_paths: list[Path] = []
    for target, backup in zip(targets, backups, strict=True):
        try:
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                backup.replace(target)
        except OSError as exc:
            failed_targets.append(target.name)
            if backup is not None:
                failed_backup_paths.append(backup)
            first_error = first_error or exc
    if first_error is not None:
        raise RollbackFailure(
            tuple(failed_targets), tuple(failed_backup_paths), first_error
        ) from first_error


def write_text_reports(
    reports: tuple[tuple[Path, str], ...], *, label: str
) -> None:
    if not reports:
        raise ValueError(f"{label} 출력이 비어 있습니다.")
    targets = tuple(target for target, _content in reports)
    staged: list[Path] = []
    backups: list[Path | None] = []
    commit_started = False
    try:
        staged.extend(
            _stage_text(target, content, label=label) for target, content in reports
        )
        backups.extend(_backup_target(target, label=label) for target in targets)
        commit_started = True
        for target, temporary_path in zip(targets, staged, strict=True):
            temporary_path.replace(target)
    except Exception as original_error:
        rollback_error: Exception | None = None
        preserved_backups: set[Path] = set()
        if commit_started:
            try:
                _rollback_reports(targets, tuple(backups))
            except RollbackFailure as exc:
                rollback_error = exc
                preserved_backups = set(exc.failed_backup_paths)
            except Exception as exc:
                rollback_error = exc
        cleanup_error = _cleanup_artifacts(
            [*staged, *backups], preserve=preserved_backups
        )
        if rollback_error is not None:
            message = f"{label} 롤백에 실패했습니다: {rollback_error}"
            if cleanup_error is not None:
                message += f"; 임시 파일 정리 실패: {cleanup_error}"
            raise RuntimeError(message) from original_error
        if cleanup_error is not None:
            raise RuntimeError(
                f"{label} 임시 파일 정리에 실패했습니다: {cleanup_error}"
            ) from original_error
        raise

    cleanup_error = _cleanup_artifacts([*staged, *backups])
    if cleanup_error is not None:
        raise RuntimeError(
            f"{label} 임시 파일 정리에 실패했습니다: {cleanup_error}"
        ) from cleanup_error
```

`backend/scripts/evaluate.py`는 기존 공개 wrapper 이름을 유지한다.

```python
from backend.app.reporting import write_text_reports


def write_reports(report: EvaluationReport, output_dir: Path) -> None:
    write_text_reports(
        (
            (output_dir / "latest.json", report.model_dump_json(indent=2) + "\n"),
            (output_dir / "latest.md", render_markdown(report)),
        ),
        label="평가 보고서",
    )
```

`evaluate.py`에서 이제 사용하지 않는 `copyfile`, `NamedTemporaryFile`, rollback helper와 class를 제거한다.

- [ ] **Step 4: GREEN과 기존 rollback 계약 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_reporting.py backend/tests/test_evaluate_script.py -q
backend/.venv/Scripts/python -m ruff check backend/app/reporting.py backend/scripts/evaluate.py backend/tests/test_reporting.py
```

Expected: 신규 2 tests와 기존 평가 script tests 모두 exit 0. commit·rollback 동시 실패 테스트에서 수동 복구용 `.bak` 경로와 원래 commit 오류가 보존된다.

- [ ] **Step 5: 커밋**

```bash
git add backend/app/reporting.py backend/scripts/evaluate.py backend/tests/test_reporting.py
git commit -m "refactor: share atomic report writer"
```

### Task 7: 데이터 감사 순수 계층

**Files:**
- Create: `backend/app/data_audit.py`
- Create: `backend/tests/test_data_audit.py`

- [ ] **Step 1: 감사 집계와 보안 RED 테스트 작성**

```python
from datetime import UTC, datetime

import pytest
from backend.app.data_audit import audit_posts, render_markdown
from backend.app.domain import BoardPost
from backend.app.topic_rules import TopicCatalog, TopicRule


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course_openings", "개설", ("개설강좌",), ()),
            TopicRule("graduation", "졸업", ("졸업요건",), ()),
            TopicRule("general", "전체", (), ()),
        ),
    )


def post(
    post_id: str,
    *,
    source: str = "kumoh",
    published_at: str | None = "2025-08-07",
    topic_key: str | None = "course_openings",
) -> BoardPost:
    return BoardPost(
        id=post_id,
        source=source,
        title="2025학년도 2학기 개설강좌 안내",
        content="감사 보고서에 포함되면 안 되는 비공개 테스트 본문",
        url=f"https://example.com/{post_id}",
        published_at=published_at,
        crawled_at=datetime(2025, 8, 8, tzinfo=UTC),
        topic_key=topic_key,
    )


def test_audit_reports_missing_source_staleness_and_empty_topic_without_body() -> None:
    report = audit_posts(
        [post("1")],
        catalog=catalog(),
        required_sources=("kumoh", "seboard"),
        stale_after_days=180,
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert report.total_posts == 1
    assert report.source_counts == {"kumoh": 1}
    assert report.topic_summaries[0].topic_key == "course_openings"
    assert {issue.code for issue in report.issues} >= {
        "missing_source",
        "stale_topic",
        "empty_topic",
    }
    serialized = report.model_dump_json()
    markdown = render_markdown(report)
    assert "비공개 테스트 본문" not in serialized
    assert "비공개 테스트 본문" not in markdown


def test_audit_reports_missing_or_invalid_published_date() -> None:
    report = audit_posts(
        [post("missing", published_at=None), post("invalid", published_at="not-a-date")],
        catalog=catalog(),
        required_sources=("kumoh",),
        stale_after_days=180,
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert [issue.code for issue in report.issues].count("missing_published_at") == 2


def test_audit_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="비어"):
        audit_posts(
            [],
            catalog=catalog(),
            required_sources=("kumoh",),
            stale_after_days=180,
        )
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_data_audit.py -q
```

Expected: `backend.app.data_audit` import 오류로 FAIL.

- [ ] **Step 3: 감사 모델·집계·Markdown 구현**

`backend/app/data_audit.py`를 다음 구조로 구현한다.

```python
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from backend.app.domain import BoardPost
from backend.app.freshness import parse_published_at
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import TopicCatalog


class AuditIssue(BaseModel):
    code: str
    message: str
    source: str | None = None
    topic_key: str | None = None
    post_id: str | None = None
    title: str | None = None
    url: str | None = None


class TopicAuditSummary(BaseModel):
    topic_key: str
    topic_label: str
    post_count: int
    latest_title: str | None
    latest_url: str | None
    latest_published_at: str | None


class DataAuditReport(BaseModel):
    generated_at: datetime
    stale_after_days: int
    total_posts: int
    source_counts: dict[str, int]
    topic_summaries: list[TopicAuditSummary]
    issues: list[AuditIssue]


def audit_posts(
    posts: Iterable[BoardPost],
    *,
    catalog: TopicCatalog,
    required_sources: tuple[str, ...],
    stale_after_days: int,
    generated_at: datetime | None = None,
) -> DataAuditReport:
    post_list = list(posts)
    if not post_list:
        raise ValueError("감사할 게시글 데이터가 비어 있습니다.")
    if stale_after_days < 1:
        raise ValueError("stale-after-days는 1 이상이어야 합니다.")
    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    enriched = enrich_posts(post_list, catalog)
    source_counts = dict(sorted(Counter(post.source for post in enriched).items()))
    issues: list[AuditIssue] = []

    for source in required_sources:
        if source not in source_counts:
            issues.append(
                AuditIssue(
                    code="missing_source",
                    source=source,
                    message=f"필수 source가 없습니다: {source}",
                )
            )

    for post in enriched:
        if parse_published_at(post.published_at) is None:
            issues.append(
                AuditIssue(
                    code="missing_published_at",
                    source=post.source,
                    topic_key=post.topic_key,
                    post_id=post.id,
                    title=post.title,
                    url=post.url,
                    message="게시일이 없거나 ISO 날짜로 해석되지 않습니다.",
                )
            )
        if post.topic_key and catalog.rule_for(post.topic_key):
            classified = catalog.classify(f"{post.title}\n{post.content}").key
            if classified != post.topic_key:
                issues.append(
                    AuditIssue(
                        code="topic_override_mismatch",
                        source=post.source,
                        topic_key=post.topic_key,
                        post_id=post.id,
                        title=post.title,
                        url=post.url,
                        message=f"규칙 분류는 {classified}이지만 override는 {post.topic_key}입니다.",
                    )
                )

    summaries: list[TopicAuditSummary] = []
    for rule in catalog.rules:
        topic_posts = [post for post in enriched if post.topic_key == rule.key]
        latest = next((post for post in topic_posts if post.is_latest_topic), None)
        summaries.append(
            TopicAuditSummary(
                topic_key=rule.key,
                topic_label=rule.label,
                post_count=len(topic_posts),
                latest_title=latest.title if latest else None,
                latest_url=latest.url if latest else None,
                latest_published_at=latest.published_at if latest else None,
            )
        )
        if latest is None:
            issues.append(
                AuditIssue(
                    code="empty_topic",
                    topic_key=rule.key,
                    message=f"주제에 게시글이 없습니다: {rule.key}",
                )
            )
            continue
        published = parse_published_at(latest.published_at)
        if published is not None and now - published > timedelta(days=stale_after_days):
            issues.append(
                AuditIssue(
                    code="stale_topic",
                    source=latest.source,
                    topic_key=rule.key,
                    post_id=latest.id,
                    title=latest.title,
                    url=latest.url,
                    message=f"최신 게시일이 {stale_after_days}일 기준보다 오래됐습니다.",
                )
            )

    return DataAuditReport(
        generated_at=now,
        stale_after_days=stale_after_days,
        total_posts=len(enriched),
        source_counts=source_counts,
        topic_summaries=summaries,
        issues=issues,
    )


def render_markdown(report: DataAuditReport) -> str:
    lines = [
        "# Data Audit Report",
        "",
        f"- Generated at: {report.generated_at.isoformat()}",
        f"- Total posts: {report.total_posts}",
        f"- Issues: {len(report.issues)}",
        "",
        "## Sources",
        "",
        "| Source | Posts |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {source} | {count} |" for source, count in report.source_counts.items())
    lines.extend(
        [
            "",
            "## Topics",
            "",
            "| Topic | Posts | Latest title | Latest date | URL |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for summary in report.topic_summaries:
        lines.append(
            f"| {summary.topic_key} | {summary.post_count} | "
            f"{summary.latest_title or '-'} | {summary.latest_published_at or '-'} | "
            f"{summary.latest_url or '-'} |"
        )
    lines.extend(["", "## Issues", ""])
    lines.extend(
        f"- [{issue.code}] {issue.message}"
        + (f" · {issue.title}" if issue.title else "")
        + (f" · {issue.url}" if issue.url else "")
        for issue in report.issues
    )
    if not report.issues:
        lines.append("- 없음")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: GREEN·Ruff·본문 제외 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_data_audit.py -q
backend/.venv/Scripts/python -m ruff check backend/app/data_audit.py backend/tests/test_data_audit.py
```

Expected: 3 tests와 Ruff exit 0, JSON/Markdown에 fixture 본문이 없음.

- [ ] **Step 5: 커밋**

```bash
git add backend/app/data_audit.py backend/tests/test_data_audit.py
git commit -m "feat: audit rag source data quality"
```

### Task 8: 데이터 감사 CLI와 보고서 계약

**Files:**
- Create: `backend/scripts/audit_data.py`
- Create: `backend/tests/test_audit_data_script.py`
- Modify: `.gitignore`

- [ ] **Step 1: CLI exit와 보고서 RED 테스트 작성**

```python
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.app.data_audit import AuditIssue, DataAuditReport, TopicAuditSummary
from backend.app.config import REPOSITORY_ROOT
from backend.scripts import audit_data


def report(*, issues: int) -> DataAuditReport:
    return DataAuditReport(
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
        stale_after_days=180,
        total_posts=1,
        source_counts={"kumoh": 1},
        topic_summaries=[
            TopicAuditSummary(
                topic_key="general",
                topic_label="전체",
                post_count=1,
                latest_title="공개 공지",
                latest_url="https://example.com/1",
                latest_published_at="2026-07-01",
            )
        ],
        issues=[
            AuditIssue(code="missing_source", source="seboard", message="source 없음")
            for _ in range(issues)
        ],
    )


def test_module_help_does_not_emit_runtime_warning() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "backend.scripts.audit_data", "--help"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert b"RuntimeWarning" not in result.stderr


@pytest.mark.parametrize(("issues", "expected_exit"), [(0, 0), (1, 1)])
def test_main_writes_reports_and_returns_quality_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    issues: int,
    expected_exit: int,
) -> None:
    monkeypatch.setattr(audit_data, "run_audit", lambda _args: report(issues=issues))

    exit_code = audit_data.main(["--output-dir", str(tmp_path)])

    assert exit_code == expected_exit
    assert (tmp_path / "latest.json").is_file()
    assert (tmp_path / "latest.md").is_file()


def test_main_returns_two_without_replacing_report_on_input_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    json_path = tmp_path / "latest.json"
    json_path.write_text("old", encoding="utf-8")

    def fail(_args):
        raise ValueError("감사 입력 오류")

    monkeypatch.setattr(audit_data, "run_audit", fail)

    assert audit_data.main(["--output-dir", str(tmp_path)]) == 2
    assert json_path.read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "latest.md").exists()
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_audit_data_script.py -q
```

Expected: `backend.scripts.audit_data` import 오류로 FAIL.

- [ ] **Step 3: 감사 CLI 구현**

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.app.config import REPOSITORY_ROOT
from backend.app.data_audit import DataAuditReport, audit_posts, render_markdown
from backend.app.reporting import write_text_reports
from backend.app.storage import load_posts
from backend.app.topic_rules import load_topic_catalog


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG 원본 데이터의 최신성과 분류를 감사합니다.")
    parser.add_argument("--posts", type=Path, default=REPOSITORY_ROOT / "data" / "raw" / "posts.json")
    parser.add_argument("--topic-rules", type=Path, default=REPOSITORY_ROOT / "data" / "topic_rules.json")
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / "data" / "audit" / "reports")
    parser.add_argument("--stale-after-days", type=int, default=180)
    parser.add_argument("--required-source", action="append", default=None)
    return parser.parse_args(argv)


def run_audit(args: argparse.Namespace) -> DataAuditReport:
    required_sources = tuple(args.required_source or ("kumoh", "seboard"))
    return audit_posts(
        load_posts(args.posts),
        catalog=load_topic_catalog(args.topic_rules),
        required_sources=required_sources,
        stale_after_days=args.stale_after_days,
    )


def write_reports(report: DataAuditReport, output_dir: Path) -> None:
    write_text_reports(
        (
            (output_dir / "latest.json", report.model_dump_json(indent=2) + "\n"),
            (output_dir / "latest.md", render_markdown(report)),
        ),
        label="데이터 감사 보고서",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_audit(args)
        write_reports(result, args.output_dir)
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"데이터 감사 오류: {exc}", file=sys.stderr)
        return 2
    print(f"게시글 {result.total_posts}건 · 품질 경고 {len(result.issues)}건")
    return 1 if result.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`.gitignore`에 다음을 추가한다.

```gitignore
data/audit/reports/
```

- [ ] **Step 4: GREEN과 실제 현재 데이터 감사**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_audit_data_script.py backend/tests/test_reporting.py -q
backend/.venv/Scripts/python -m ruff check backend/scripts/audit_data.py backend/tests/test_audit_data_script.py
backend/.venv/Scripts/python -m backend.scripts.audit_data
```

Expected: tests/Ruff exit 0. 실제 감사는 현재 `seboard` 누락·오래된 `course_openings`·빈 `graduation` 때문에 보고서를 생성하고 quality exit 1.

- [ ] **Step 5: 보고서 보안·ignore 확인**

Run:

```powershell
git check-ignore -v data/audit/reports/latest.json data/audit/reports/latest.md
rg -n -i "API_KEY|PASSWORD|BEARER|OPENAI_API_KEY|비공개 테스트 본문" data/audit/reports/latest.json data/audit/reports/latest.md
```

Expected: 두 보고서 모두 ignore 규칙 출력. `rg`는 민감정보·본문 패턴을 찾지 못해 exit 1.

- [ ] **Step 6: 커밋**

```bash
git add .gitignore backend/scripts/audit_data.py backend/tests/test_audit_data_script.py
git commit -m "feat: add rag data audit cli"
```

### Task 9: 재인덱싱, 30/30 평가, 운영 문서와 인수인계

**Files:**
- Modify: `README.md`
- Modify: `docs/rag/operations-evaluation.md`
- Modify: `docs/PROJECT_STATUS.md`
- Create: `docs/superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md`

- [ ] **Step 1: normative 평가 데이터 불변 확인**

Run:

```powershell
git diff --exit-code main -- data/evaluation/questions.json
```

Expected: 출력 없이 exit 0. Task 4 Step 2에서 기록한 25/30 RED 결과와 실패 ID 5개를 인수인계 문서에 기록한다.

- [ ] **Step 2: 정책 변경 후 인덱스 재생성**

Run:

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

Expected: 게시글 46건, 청크 79개, exit 0.

- [ ] **Step 3: 실제 30문항 GREEN 확인**

Run:

```powershell
backend/.venv/Scripts/python -m backend.scripts.evaluate
```

Expected: exit 0, `total=30`, `passed=30`, `failed=0`; topic 30/30, grounded 30/30, latest-only 30/30, source-title 11/11.

- [ ] **Step 4: 전체 backend/frontend 회귀 실행**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m ruff check backend
npm --prefix frontend test
frontend/node_modules/.bin/tsc.cmd -p frontend/tsconfig.json --noEmit --incremental false
npm --prefix frontend run lint
npm --prefix frontend run build
```

Expected: 모든 명령 exit 0. Next.js build가 `frontend/next-env.d.ts`를 바꾸면 build 결과를 확인한 후 저장소 기준 내용으로 복원하고 변경이 없는지 확인한다.

- [ ] **Step 5: 운영 문서와 상태 갱신**

다음 내용을 실제 수치로 기록한다.

```markdown
- RAG 품질: 30/30, quality exit 0
- 근거 정책: 기간 충돌 거절, 제목 marker/동의어 검증, 일반 최신 날짜 우선
- 데이터 감사: 실행 명령, 현재 경고 코드와 source/topic 최신일
- 부분 수집: 운영 raw path가 아닌 data/raw/candidates/에 저장
- 외부 검증 대기: 공식 사이트 live 최신성·SE source 실제 수집 성공
```

handoff에는 각 task의 RED 이유, GREEN 명령, 커밋 hash, 생성 보고서 경로, 다음 하위 프로젝트 `백엔드 테스트 85%와 임베딩 fingerprint`를 기록한다.

- [ ] **Step 6: Git hygiene와 최종 diff 확인**

Run:

```powershell
git status --short
git diff --check
git diff --stat main...HEAD
git check-ignore -v chroma_db data/evaluation/reports/latest.json data/audit/reports/latest.json data/raw/candidates/posts-partial.json
```

Expected: 추적 변경은 코드·테스트·설정·문서뿐이며 생성물은 모두 ignore. `git diff --check` exit 0.

- [ ] **Step 7: 문서 커밋**

```bash
git add README.md docs/rag/operations-evaluation.md docs/PROJECT_STATUS.md docs/superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md
git commit -m "docs: record rag quality hardening"
```

## 최종 완료 판정

- [ ] 기존 `data/evaluation/questions.json`의 30개 normative expectation이 변경되지 않았다.
- [ ] false-positive 3건이 `grounded=false`이고 provider answer를 호출하지 않는다.
- [ ] false-negative 2건이 최신 URL·게시일을 포함한 `grounded=true`다.
- [ ] 실제 local 평가가 30/30과 exit 0이다.
- [ ] 부분 수집 실패가 운영 원본을 덮어쓰지 않는다.
- [ ] 감사 JSON·Markdown이 생성되고 본문·비밀값·로컬 절대 경로를 포함하지 않는다.
- [ ] backend 전체 pytest·Ruff와 frontend test·type·lint·build가 통과한다.
- [ ] 상태·인수인계 문서가 로컬 완료와 외부 검증 대기를 구분한다.

## 설계 요구사항 자체 검토

| 설계 요구사항 | 구현 task | 검토 결과 |
| --- | --- | --- |
| `topic_key`별 최신 1건 유지 | Task 4 | 기존 metadata filter를 유지하고 general 최신만 URL로 좁힘 |
| 연도·학기 충돌 거절 | Task 2·3 | `requested_year`, `requested_term`과 제목을 비교 |
| 제목 marker·동의어 적합성 | Task 1·2·3 | JSON 정책 → match terms → evidence decision으로 연결 |
| false-positive 3건·false-negative 2건 | Task 4 | 5개 동작을 독립 RED 테스트로 고정 |
| baseline 변경 없이 30/30 | Task 4·9 | 평가 데이터 diff와 실제 exit 0을 모두 확인 |
| 부분 수집 원본 보호 | Task 5 | 후보 경로 분리와 동일 경로 거절 테스트 포함 |
| 감사 JSON·Markdown·exit 0/1/2 | Task 7·8 | 순수 집계와 CLI 계약을 분리 |
| 보고서 원자적 교체·rollback | Task 6·8 | 기존 평가 backup 보존 계약을 공용 writer로 이전 |
| 본문·비밀값·절대경로 제외 | Task 7·8·9 | 모델 필드·패턴 검사·Git ignore로 검증 |
| 외부 검증 대기 분리 | Task 9 | PROJECT_STATUS와 handoff에 live source 검증을 별도 기록 |

자체 검토 결과 설계 요구사항 중 task에 연결되지 않은 항목은 없다. 함수명과 필드명은 `QueryIntent.requested_term`, `QueryIntent.match_terms`, `decide_evidence()`, `write_text_reports()`, `audit_posts()`로 모든 task에서 일치한다.
