# SE Mentor Bot 주제별 최신성·추천 UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주제 규칙으로 게시글을 분류하고 같은 주제의 최신 자료만 RAG 답변에 사용하며, 답변 뒤 추천 질문과 최근 공지를 제공하는 읽기 쉬운 A형 채팅 UI를 구현한다.

**Architecture:** 원본 게시글은 `data/raw/posts.json`에 유지하고 `data/topic_rules.json`을 주제 분류의 유지보수 지점으로 둔다. 인덱싱 시 게시글을 주제화하고 `published_at`/`crawled_at`으로 `is_latest_topic`을 계산해 Chroma metadata에 저장한다. 온라인 질의는 주제와 최신 플래그로 검색 범위를 제한한 뒤 답변, 출처, 추천 질문, 최근 공지를 하나의 응답으로 반환한다.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, Chroma, pytest, Ruff, Next.js 15, React 19, TypeScript, Vitest, Testing Library.

---

## 파일 책임 지도

### 생성

- `data/topic_rules.json`: 주제 키, 라벨, 키워드, 주제별 추천 질문
- `backend/app/topic_rules.py`: 규칙 파일 로딩·검증·결정적 주제 분류
- `backend/app/topic_classifier.py`: 게시글 주제 보정과 주제별 최신 게시글 표시
- `backend/app/freshness.py`: 게시일 파싱과 최신성 비교 키
- `backend/app/recommendations.py`: 추천 질문·최근 공지 생성
- `backend/tests/test_topic_rules.py`: 규칙 로딩·분류 테스트
- `backend/tests/test_topic_classifier.py`: 게시글 enrichment 테스트
- `backend/tests/test_freshness.py`: 날짜 우선순위 테스트
- `backend/tests/test_recommendations.py`: 응답 보조 콘텐츠 테스트
- `frontend/app/components/types.ts`: 프론트엔드 응답 타입
- `frontend/app/components/RecommendationChips.tsx`: 추천 질문 버튼
- `frontend/app/components/RecentNoticeList.tsx`: 최근 공지 카드
- `frontend/app/components/ChatMessage.tsx`: 메시지·출처·보조 콘텐츠 렌더링
- `frontend/app/components/RecommendationChips.test.tsx`: 추천 질문 UI 테스트
- `frontend/app/components/RecentNoticeList.test.tsx`: 최근 공지 UI 테스트
- `frontend/app/components/ChatMessage.test.tsx`: 메시지 구성 UI 테스트
- `frontend/vitest.config.ts`: Vitest와 jsdom 설정
- `frontend/vitest.setup.ts`: Testing Library matcher 설정

### 수정

- `backend/app/domain.py`: topic metadata와 `RecentNotice` 모델
- `backend/app/config.py`: `TOPIC_RULES_PATH` 설정
- `backend/app/schemas.py`: `ChatResponse` 확장
- `backend/app/chunking.py`: chunk에 topic metadata 전달
- `backend/app/vector_store.py`: topic metadata 저장과 Chroma where 필터
- `backend/app/rag.py`: 최신 주제 검색·추천·최근 공지 조합
- `backend/app/main.py`: catalog·enriched posts를 RAG service에 주입
- `backend/scripts/index.py`: 규칙 적용과 최신 플래그 계산 후 인덱싱
- `backend/tests/test_chunking.py`: 새 chunk metadata 기대값
- `backend/tests/test_vector_store.py`: metadata·where query 기대값
- `backend/tests/test_rag.py`: 최신 필터·보조 응답 기대값
- `.env.example`: `TOPIC_RULES_PATH`
- `README.md`, `docs/RAG_ARCHITECTURE.md`, `docs/rag/retrieval-answering.md`, `docs/rag/operations-evaluation.md`, `docs/rag/overview.md`: 운영·재인덱싱 문서
- `frontend/app/page.tsx`: 새 타입과 컴포넌트 조합
- `frontend/app/globals.css`: 답변 후속 콘텐츠와 반응형 스타일
- `frontend/package.json`, `frontend/package-lock.json`: UI 테스트 명령·의존성

## Task 1: 주제 규칙과 도메인 모델 추가

**Files:**
- Create: `data/topic_rules.json`
- Create: `backend/app/topic_rules.py`
- Create: `backend/tests/test_topic_rules.py`
- Modify: `backend/app/domain.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/chunking.py`
- Modify: `backend/app/vector_store.py`
- Modify: `backend/tests/test_local_service.py`
- Modify: `.env.example`

- [ ] **Step 1: 규칙 로더의 실패 테스트 작성**

`backend/tests/test_topic_rules.py`에 다음 테스트를 작성한다.

```python
import json

import pytest

from backend.app.topic_rules import load_topic_catalog


def test_catalog_matches_longest_keyword_and_keeps_rule_order(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": "course",
                        "label": "수업",
                        "keywords": ["강좌", "개설강좌"],
                        "suggested_questions": ["개설강좌를 알려줘"],
                    },
                    {
                        "key": "general",
                        "label": "전체 공지",
                        "keywords": [],
                        "suggested_questions": ["최근 공지를 알려줘"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    catalog = load_topic_catalog(path)

    assert catalog.classify("이번 학기 개설강좌가 궁금해").key == "course"
    assert catalog.classify("무슨 공지가 있어?").key == "general"


def test_catalog_rejects_missing_default_topic(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps({"default_topic_key": "missing", "topics": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="default_topic_key"):
        load_topic_catalog(path)
```

- [ ] **Step 2: 테스트가 기능 부재로 실패하는지 확인**

Run: `backend/.venv/Scripts/python -m pytest backend/tests/test_topic_rules.py -q`

Expected: `ModuleNotFoundError` 또는 `ImportError`로 `backend.app.topic_rules`가 없어 실패한다.

- [ ] **Step 3: 규칙 파일과 최소 로더 구현**

`data/topic_rules.json`에 다음 규칙을 저장한다.

```json
{
  "default_topic_key": "general",
  "topics": [
    {
      "key": "course_openings",
      "label": "개설강좌조회",
      "keywords": ["개설강좌", "개설 과목", "수강 가능 과목"],
      "suggested_questions": ["이번 학기 개설강좌를 알려줘", "개설강좌 조회 방법은?"]
    },
    {
      "key": "registration",
      "label": "수강신청",
      "keywords": ["수강신청", "수강 신청", "수강변경"],
      "suggested_questions": ["수강신청 기간은 언제야?", "수강신청 변경 방법은?"]
    },
    {
      "key": "capstone",
      "label": "캡스톤디자인",
      "keywords": ["캡스톤디자인", "캡스톤 디자인"],
      "suggested_questions": ["캡스톤디자인 신청 방법은?", "캡스톤디자인 일정은?"]
    },
    {
      "key": "career",
      "label": "진로·취업",
      "keywords": ["취업", "채용", "인턴", "진로"],
      "suggested_questions": ["최근 취업 프로그램을 알려줘", "인턴 관련 공지가 있어?"]
    },
    {
      "key": "scholarship",
      "label": "장학금",
      "keywords": ["장학금", "장학생", "장학"],
      "suggested_questions": ["장학금 신청 공지를 알려줘", "장학생 선발 기준은?"]
    },
    {
      "key": "graduation",
      "label": "졸업요건",
      "keywords": ["졸업요건", "졸업 요건", "졸업인증"],
      "suggested_questions": ["졸업요건을 확인해줘", "졸업인증 기준은?"]
    },
    {
      "key": "general",
      "label": "전체 공지",
      "keywords": [],
      "suggested_questions": ["최근 학과 공지를 알려줘", "소프트웨어전공 공지를 알려줘"]
    }
  ]
}
```

`backend/app/topic_rules.py`는 다음 인터페이스를 구현한다.

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TopicRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    suggested_questions: tuple[str, ...]


@dataclass(frozen=True)
class TopicCatalog:
    default_topic_key: str
    rules: tuple[TopicRule, ...]

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


def load_topic_catalog(path: Path) -> TopicCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise ValueError("주제 규칙은 topics 배열을 포함해야 합니다.")
    rules = tuple(
        TopicRule(
            key=str(item["key"]),
            label=str(item["label"]),
            keywords=tuple(str(value) for value in item.get("keywords", [])),
            suggested_questions=tuple(
                str(value) for value in item.get("suggested_questions", [])
            ),
        )
        for item in payload["topics"]
    )
    catalog = TopicCatalog(
        default_topic_key=str(payload.get("default_topic_key", "general")),
        rules=rules,
    )
    if catalog.rule_for(catalog.default_topic_key) is None:
        raise ValueError("default_topic_key에 해당하는 규칙이 없습니다.")
    return catalog
```

`domain.py`의 `BoardPost`에는 다음 선택 필드를 추가하고, `TextChunk`에는 계산된 값을 필수로 둔다.

```python
# BoardPost
topic_key: str | None = None
topic_label: str | None = None
is_latest_topic: bool = False

# TextChunk
topic_key: str
topic_label: str
is_latest_topic: bool
```

새 필수가 된 `TextChunk`을 생성하는 기존 `chunking.py`와 `vector_store.py`에는 각각 `post` 또는 Chroma metadata에서 `topic_key`, `topic_label`, `is_latest_topic`을 전달한다. 이 단계에서는 vector upsert metadata와 where 필터를 추가하지 않고, 해당 저장·검색 동작은 Task 3에서 구현한다. 기존 `test_rag.py`, `test_local_service.py`, `test_vector_store.py` fixture에는 `topic_key="general"`, `topic_label="전체 공지"`, `is_latest_topic=False`를 함께 넣는다. Task 4에서 추가하는 RAG fixture만 `course_openings` 값을 사용한다.

기존 생성 지점은 다음 최소 필드를 전달한다.

```python
# chunking.py
topic_key=post.topic_key or "general",
topic_label=post.topic_label or "전체 공지",
is_latest_topic=post.is_latest_topic,

# vector_store.py, until Task 3 stores metadata
topic_key=str(metadata.get("topic_key", "general")),
topic_label=str(metadata.get("topic_label", "전체 공지")),
is_latest_topic=bool(metadata.get("is_latest_topic", False)),
```

`config.py`에는 `topic_rules_path: Path`를 추가하고 기본값을 `_resolve_path(os.getenv("TOPIC_RULES_PATH", "./data/topic_rules.json"))`로 설정한다. `.env.example`에도 `TOPIC_RULES_PATH=./data/topic_rules.json`을 추가한다.

- [ ] **Step 4: 규칙 테스트 통과 확인**

Run: `backend/.venv/Scripts/python -m pytest backend/tests/test_topic_rules.py -q`

Expected: `2 passed`.

- [ ] **Step 5: 커밋**

```powershell
git add data/topic_rules.json backend/app/topic_rules.py backend/app/domain.py backend/app/config.py backend/tests/test_topic_rules.py .env.example
git commit -m "feat: add configurable topic rules"
```

## Task 2: 날짜 기반 최신 게시글 enrichment 구현

**Files:**
- Create: `backend/app/freshness.py`
- Create: `backend/app/topic_classifier.py`
- Create: `backend/tests/test_freshness.py`
- Create: `backend/tests/test_topic_classifier.py`
- Modify: `backend/app/chunking.py`
- Modify: `backend/tests/test_chunking.py`

- [ ] **Step 1: 날짜 비교와 topic enrichment 실패 테스트 작성**

`backend/tests/test_freshness.py`:

```python
from datetime import UTC, datetime

from backend.app.domain import BoardPost
from backend.app.freshness import freshness_key, latest_post_keys


def post(post_id: str, published_at: str | None, crawled_at: datetime) -> BoardPost:
    return BoardPost(
        id=post_id,
        source="kumoh",
        title="개설강좌 안내",
        content="내용",
        url=f"https://example.com/{post_id}",
        published_at=published_at,
        crawled_at=crawled_at,
    )


def test_published_at_wins_over_crawled_at() -> None:
    older_crawl = post("old", "2026-03-10", datetime(2026, 7, 1, tzinfo=UTC))
    newer_publish = post("new", "2026-03-20", datetime(2026, 3, 21, tzinfo=UTC))

    assert freshness_key(newer_publish) > freshness_key(older_crawl)


def test_missing_published_at_falls_back_to_crawled_at() -> None:
    first = post("first", None, datetime(2026, 3, 20, tzinfo=UTC))
    second = post("second", None, datetime(2026, 3, 21, tzinfo=UTC))

    assert latest_post_keys([first, second]) == {("kumoh", "second")}
```

`backend/tests/test_topic_classifier.py`:

```python
from datetime import UTC, datetime

from backend.app.domain import BoardPost
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import TopicCatalog, TopicRule


def test_enrich_posts_marks_only_latest_post_per_topic() -> None:
    catalog = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course", "수업", ("개설강좌",), ()),
            TopicRule("general", "전체 공지", (), ()),
        ),
    )
    posts = [
        BoardPost(
            id="old",
            source="kumoh",
            title="개설강좌 안내",
            content="이전 내용",
            url="https://example.com/old",
            published_at="2026-03-10",
            crawled_at=datetime(2026, 3, 10, tzinfo=UTC),
        ),
        BoardPost(
            id="new",
            source="kumoh",
            title="개설강좌 안내",
            content="최신 내용",
            url="https://example.com/new",
            published_at="2026-03-20",
            crawled_at=datetime(2026, 3, 20, tzinfo=UTC),
        ),
    ]

    enriched = enrich_posts(posts, catalog)

    assert [(item.id, item.topic_key, item.is_latest_topic) for item in enriched] == [
        ("old", "course", False),
        ("new", "course", True),
    ]
```

- [ ] **Step 2: 실패 원인이 새 함수 부재인지 확인**

Run: `backend/.venv/Scripts/python -m pytest backend/tests/test_freshness.py backend/tests/test_topic_classifier.py -q`

Expected: `ModuleNotFoundError`로 `freshness` 또는 `topic_classifier`가 없어 실패한다.

- [ ] **Step 3: freshness와 enrichment 구현**

`backend/app/freshness.py`는 날짜 없는 자료와 timezone 없는 ISO 문자열을 안전하게 처리한다.

```python
from __future__ import annotations

from datetime import UTC, datetime

from backend.app.domain import BoardPost


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware(parsed)


def freshness_key(post: BoardPost) -> tuple[int, datetime, datetime]:
    crawled_at = _aware(post.crawled_at)
    published_at = parse_published_at(post.published_at)
    if published_at is None:
        return (0, crawled_at, crawled_at)
    return (1, published_at, crawled_at)


def latest_post_keys(posts: list[BoardPost]) -> set[tuple[str, str]]:
    latest: dict[str, BoardPost] = {}
    for post in posts:
        current = latest.get(post.topic_key or "general")
        if current is None or freshness_key(post) > freshness_key(current):
            latest[post.topic_key or "general"] = post
    return {(post.source, post.id) for post in latest.values()}
```

`backend/app/topic_classifier.py`:

```python
from __future__ import annotations

from backend.app.domain import BoardPost
from backend.app.freshness import latest_post_keys
from backend.app.topic_rules import TopicCatalog


def enrich_posts(posts: list[BoardPost], catalog: TopicCatalog) -> list[BoardPost]:
    topicized: list[BoardPost] = []
    for post in posts:
        override = catalog.rule_for(post.topic_key or "")
        rule = override or catalog.classify(f"{post.title}\n{post.content}")
        topicized.append(
            post.model_copy(
                update={"topic_key": rule.key, "topic_label": rule.label}
            )
        )
    latest_keys = latest_post_keys(topicized)
    return [
        post.model_copy(
            update={"is_latest_topic": (post.source, post.id) in latest_keys}
        )
        for post in topicized
    ]
```

Update `chunk_post` to copy the enriched values into `TextChunk`:

```python
topic_key=post.topic_key or "general",
topic_label=post.topic_label or "전체 공지",
is_latest_topic=post.is_latest_topic,
```

Update the existing chunk test expected object with `topic_key="general"`, `topic_label="전체 공지"`, and `is_latest_topic=False` for an unenriched fixture. Add an enriched fixture assertion with `is_latest_topic=True`.

- [ ] **Step 4: freshness·enrichment·chunking 테스트 통과 확인**

Run: `backend/.venv/Scripts/python -m pytest backend/tests/test_freshness.py backend/tests/test_topic_classifier.py backend/tests/test_chunking.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: 커밋**

```powershell
git add backend/app/freshness.py backend/app/topic_classifier.py backend/app/chunking.py backend/tests/test_freshness.py backend/tests/test_topic_classifier.py backend/tests/test_chunking.py
git commit -m "feat: mark latest posts by topic"
```

## Task 3: Chroma metadata와 최신 주제 필터 연결

**Files:**
- Modify: `backend/app/vector_store.py`
- Modify: `backend/scripts/index.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/rag.py`
- Modify: `backend/tests/test_vector_store.py`
- Create: `backend/tests/test_main.py`

- [ ] **Step 1: metadata와 where 필터 실패 테스트 작성**

Extend `backend/tests/test_vector_store.py` with a fake collection and assertions that `upsert` metadata contains topic fields and `query` forwards `where`.

```python
def test_upsert_stores_topic_metadata() -> None:
    chunks = [
        TextChunk(
            id="kumoh:1:0",
            post_id="1",
            source="kumoh",
            title="개설강좌",
            text="최신",
            url="https://example.com/1",
            published_at="2026-03-20",
            chunk_index=0,
            topic_key="course_openings",
            topic_label="개설강좌조회",
            is_latest_topic=True,
        )
    ]
    store.upsert(chunks, [[1.0, 0.0]])

    metadata = store.collection.upsert.call_args.kwargs["metadatas"][0]
    assert metadata["topic_key"] == "course_openings"
    assert metadata["is_latest_topic"] is True


def test_query_forwards_latest_topic_filter() -> None:
    store.query([1.0, 0.0], top_k=3, where={"is_latest_topic": True})

    assert store.collection.query.call_args.kwargs["where"] == {
        "is_latest_topic": True
    }
```

- [ ] **Step 2: 테스트가 새 metadata/query 계약 부재로 실패하는지 확인**

Run: `backend/.venv/Scripts/python -m pytest backend/tests/test_vector_store.py -q`

Expected: `TextChunk` 생성 인자 또는 `query(..., where=...)` 미지원으로 실패한다.

- [ ] **Step 3: vector store에 metadata와 where 전달 구현**

`upsert` metadata에 다음 값을 추가한다.

```python
"topic_key": chunk.topic_key,
"topic_label": chunk.topic_label,
"is_latest_topic": chunk.is_latest_topic,
```

`query` 시그니처를 다음으로 바꾼다.

```python
def query(
    self,
    embedding: Sequence[float],
    top_k: int,
    where: dict[str, object] | None = None,
) -> list[RetrievedChunk]:
```

Chroma 호출은 다음처럼 조건부 인자를 전달한다.

```python
query_kwargs = {
    "query_embeddings": [list(embedding)],
    "n_results": min(top_k, self.count()),
    "include": ["documents", "metadatas", "distances"],
}
if where is not None:
    query_kwargs["where"] = where
result = self.collection.query(**query_kwargs)
```

metadata를 `TextChunk`으로 되돌릴 때 `topic_key`, `topic_label`, `is_latest_topic`을 각각 기본값 없이 저장된 값으로 변환한다.

`backend/scripts/index.py`는 `load_topic_catalog(settings.topic_rules_path)`와 `enrich_posts(load_posts(...), catalog)`를 호출한 뒤 enriched posts를 `chunk_posts`에 전달한다. `--reset`이 주어지면 upsert 전에 기존 collection을 삭제한다.

`backend/app/main.py`에는 다음 캐시를 추가한다.

```python
@lru_cache(maxsize=1)
def get_topic_catalog() -> TopicCatalog:
    return load_topic_catalog(settings.topic_rules_path)


@lru_cache(maxsize=1)
def get_enriched_posts() -> list[BoardPost]:
    return enrich_posts(load_posts(settings.raw_posts_path), get_topic_catalog())
```

RAG service 생성 시 `topic_catalog=get_topic_catalog()`과 `posts=get_enriched_posts()`를 전달한다. 원본 파일이 없어 health만 확인하는 상황에서는 `get_enriched_posts`가 빈 목록을 반환하도록 `FileNotFoundError`를 잡고, 채팅은 기존 벡터 검색 결과로 계속 동작하게 한다.

이 단계에서는 `RAGService.__init__`가 해당 두 값을 optional context로 받아 저장할 수 있게만 한다. 주제 filter 적용과 추천·최근 공지 사용은 Task 4에서 구현한다. `main.py`가 실제로 service를 초기화할 수 있는지 테스트로 확인한다.

`backend/tests/test_main.py`에는 `get_rag_service()`를 monkeypatch된 settings·provider·vector store로 호출해 `RAGService`가 생성되고 `posts` 46건과 catalog가 주입되는 회귀 테스트를 추가한다.

- [ ] **Step 4: vector store 관련 테스트 통과 확인**

Run: `backend/.venv/Scripts/python -m pytest backend/tests/test_vector_store.py backend/tests/test_storage.py -q`

Expected: selected tests pass.

- [ ] **Step 5: 커밋**

```powershell
git add backend/app/vector_store.py backend/scripts/index.py backend/app/main.py backend/tests/test_vector_store.py
git commit -m "feat: filter vector search by latest topic"
```

## Task 4: 추천 질문·최근 공지와 RAG 응답 확장

**Files:**
- Create: `backend/app/recommendations.py`
- Create: `backend/tests/test_recommendations.py`
- Modify: `backend/app/domain.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/rag.py`
- Modify: `backend/tests/test_rag.py`

- [ ] **Step 1: 응답 보조 콘텐츠와 최신 필터 실패 테스트 작성**

`domain.py`에 다음 모델을 추가하기 전에 테스트를 작성한다.

`backend/tests/test_rag.py`의 기존 fixture 아래에 테스트 전용 helper를 먼저 추가한다.

```python
from datetime import UTC, datetime

from backend.app.domain import BoardPost, RetrievedChunk, TextChunk
from backend.app.topic_rules import TopicCatalog, TopicRule


def course_catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule(
                "course_openings",
                "개설강좌조회",
                ("개설강좌",),
                ("이번 학기 개설강좌를 알려줘",),
            ),
            TopicRule("general", "전체 공지", (), ("최근 학과 공지를 알려줘",)),
        ),
    )


def retrieved_post(post_id: str, published_at: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id=f"kumoh:{post_id}:0",
            post_id=post_id,
            source="kumoh",
            title="개설강좌 안내",
            text=f"게시글 {post_id} 내용",
            url=f"https://example.com/{post_id}",
            published_at=published_at,
            chunk_index=0,
            topic_key="course_openings",
            topic_label="개설강좌조회",
            is_latest_topic=post_id == "new",
        ),
        score=score,
    )


def retrieved_old() -> RetrievedChunk:
    return retrieved_post("old", "2026-03-10", 0.95)


def retrieved_latest() -> RetrievedChunk:
    return retrieved_post("new", "2026-03-20", 0.9)


def enriched_posts() -> list[BoardPost]:
    return [
        BoardPost(
            id="old",
            source="kumoh",
            title="개설강좌 안내",
            content="이전 내용",
            url="https://example.com/old",
            published_at="2026-03-10",
            crawled_at=datetime(2026, 3, 10, tzinfo=UTC),
            topic_key="course_openings",
            topic_label="개설강좌조회",
            is_latest_topic=False,
        ),
        BoardPost(
            id="new",
            source="kumoh",
            title="개설강좌 안내",
            content="최신 내용",
            url="https://example.com/new",
            published_at="2026-03-20",
            crawled_at=datetime(2026, 3, 20, tzinfo=UTC),
            topic_key="course_openings",
            topic_label="개설강좌조회",
            is_latest_topic=True,
        ),
    ]
```

그 다음 다음 테스트를 작성한다.

```python
def test_rag_keeps_only_latest_topic_and_returns_followups() -> None:
    provider = FakeProvider()
    store = FakeStore([retrieved_old(), retrieved_latest()])
    service = RAGService(
        provider=provider,
        vector_store=store,
        topic_catalog=course_catalog(),
        posts=enriched_posts(),
    )

    result = service.ask("개설강좌를 알려줘")

    assert result.grounded is True
    assert result.suggested_questions == ["이번 학기 개설강좌를 알려줘"]
    assert result.recent_notices[0].topic_key == "course_openings"
    assert store.last_where == {
        "$and": [
            {"is_latest_topic": True},
            {"topic_key": "course_openings"},
        ]
    }
```

`FakeStore.query`를 `query(self, embedding, top_k, where=None)`으로 바꾸고 `last_where`를 저장해 filter contract를 검증한다.

- [ ] **Step 2: 새 테스트가 응답 필드·filter 부재로 실패하는지 확인**

Run: `backend/.venv/Scripts/python -m pytest backend/tests/test_rag.py backend/tests/test_recommendations.py -q`

Expected: 새 `ChatResponse` 필드와 `RAGService` 생성 인자가 없어 실패한다.

- [ ] **Step 3: 추천 모델과 생성 함수를 구현**

`domain.py`에 다음을 추가한다.

```python
class RecentNotice(BaseModel):
    title: str
    url: str
    source: str
    published_at: str | None = None
    topic_key: str
    topic_label: str
```

`schemas.py`의 `ChatResponse`를 다음처럼 확장한다.

```python
class ChatResponse(BaseModel):
    answer: str
    sources: list[AnswerSource]
    grounded: bool
    suggested_questions: list[str] = Field(default_factory=list)
    recent_notices: list[RecentNotice] = Field(default_factory=list)
```

`backend/app/recommendations.py`:

```python
from __future__ import annotations

from backend.app.domain import BoardPost, RecentNotice
from backend.app.freshness import freshness_key
from backend.app.topic_rules import TopicCatalog


def suggested_questions(
    catalog: TopicCatalog, topic_key: str, limit: int = 3
) -> list[str]:
    rule = catalog.rule_for(topic_key) or catalog.rule_for(catalog.default_topic_key)
    return list(rule.suggested_questions[:limit]) if rule else []


def recent_notices(
    posts: list[BoardPost], topic_key: str, catalog: TopicCatalog, limit: int = 3
) -> list[RecentNotice]:
    latest = [post for post in posts if post.is_latest_topic]
    related = [post for post in latest if post.topic_key == topic_key]
    others = [post for post in latest if post.topic_key != topic_key]
    ordered = sorted(related, key=freshness_key, reverse=True) + sorted(
        others, key=freshness_key, reverse=True
    )
    result: list[RecentNotice] = []
    seen_urls: set[str] = set()
    for post in ordered:
        if post.url in seen_urls:
            continue
        rule = catalog.rule_for(post.topic_key or catalog.default_topic_key)
        if rule is None:
            continue
        seen_urls.add(post.url)
        result.append(
            RecentNotice(
                title=post.title,
                url=post.url,
                source=post.source,
                published_at=post.published_at,
                topic_key=rule.key,
                topic_label=rule.label,
            )
        )
        if len(result) == limit:
            break
    return result
```

- [ ] **Step 4: RAGService에 최신 filter와 보조 응답 연결**

RAGService 생성자에 다음 의존성을 추가한다.

```python
def __init__(
    self,
    *,
    provider: AIProvider,
    vector_store: ChromaVectorStore,
    topic_catalog: TopicCatalog,
    posts: list[BoardPost],
    top_k: int = 5,
    min_score: float = 0.2,
) -> None:
    self.topic_catalog = topic_catalog
    self.posts = posts
```

`ask`는 query embedding 전에 `topic = self.topic_catalog.classify(question)`을 호출한다. 기본 주제가 아니면 다음 filter를 사용하고, 기본 주제면 최신 게시글 전체를 사용한다.

```python
where = {"is_latest_topic": True}
if topic.key != self.topic_catalog.default_topic_key:
    where = {
        "$and": [
            {"is_latest_topic": True},
            {"topic_key": topic.key},
        ]
    }
retrieved = self._rerank(
    question,
    self.vector_store.query(query_embedding, self.top_k, where=where),
)
```

`relevant`가 비어도 다음 값을 계산해 반환한다.

```python
suggestions = suggested_questions(self.topic_catalog, topic.key)
notices = recent_notices(self.posts, topic.key, self.topic_catalog)
```

근거가 없을 때는 `ChatResponse(answer=NO_ANSWER, sources=[], grounded=False, suggested_questions=suggestions, recent_notices=notices)`를 반환한다. 근거가 있을 때도 같은 두 값을 답변과 함께 반환한다.

- [ ] **Step 5: RAG 관련 테스트 통과 확인**

Run: `backend/.venv/Scripts/python -m pytest backend/tests/test_rag.py backend/tests/test_recommendations.py -q`

Expected: selected tests pass, including the no-answer provider-not-called test.

- [ ] **Step 6: 커밋**

```powershell
git add backend/app/domain.py backend/app/schemas.py backend/app/recommendations.py backend/app/rag.py backend/tests/test_rag.py backend/tests/test_recommendations.py
git commit -m "feat: return topic-aware chat follow-ups"
```

## Task 5: 프론트엔드 후속 콘텐츠 컴포넌트 TDD

**Files:**
- Create: `frontend/app/components/types.ts`
- Create: `frontend/app/components/RecommendationChips.tsx`
- Create: `frontend/app/components/RecentNoticeList.tsx`
- Create: `frontend/app/components/ChatMessage.tsx`
- Create: `frontend/app/components/RecommendationChips.test.tsx`
- Create: `frontend/app/components/RecentNoticeList.test.tsx`
- Create: `frontend/app/components/ChatMessage.test.tsx`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/vitest.setup.ts`
- Modify: `frontend/package.json`
- Modify: `.gitignore`

- [ ] **Step 1: 테스트 도구 설정과 실패 테스트 작성**

`frontend/package.json` scripts에 다음을 추가한다.

```json
"test": "vitest run"
```

devDependencies에는 다음 패키지를 추가한다.

```json
"@testing-library/jest-dom": "^6.6.3",
"@testing-library/react": "^16.1.0",
"@vitejs/plugin-react": "^4.3.4",
"jsdom": "^25.0.1",
"vitest": "^2.1.8"
```

Install: `npm --prefix frontend install`

TypeScript와 Next.js가 생성하는 `*.tsbuildinfo`는 빌드 캐시이므로 `.gitignore`에 추가하고 커밋 대상에서 제외한다.

`frontend/vitest.config.ts`:

```typescript
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
  },
});
```

`frontend/vitest.setup.ts`:

```typescript
import "@testing-library/jest-dom/vitest";
```

`frontend/app/components/types.ts`:

```typescript
export type Source = {
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  score: number;
};

export type RecentNotice = {
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  topic_key: string;
  topic_label: string;
};

export type AssistantMessage = {
  id: number;
  role: "assistant";
  content: string;
  sources: Source[];
  grounded?: boolean;
  suggested_questions: string[];
  recent_notices: RecentNotice[];
};

export type UserMessage = {
  id: number;
  role: "user";
  content: string;
};

export type Message = AssistantMessage | UserMessage;
```

Write the three failing tests with concrete props before adding the components.

`frontend/app/components/RecommendationChips.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RecommendationChips } from "./RecommendationChips";

describe("RecommendationChips", () => {
  it("calls onSelect with the clicked question", () => {
    const onSelect = vi.fn();
    render(
      <RecommendationChips
        questions={["이번 학기 개설강좌를 알려줘"]}
        disabled={false}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "이번 학기 개설강좌를 알려줘" }));

    expect(onSelect).toHaveBeenCalledWith("이번 학기 개설강좌를 알려줘");
  });
});
```

`frontend/app/components/RecentNoticeList.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecentNoticeList } from "./RecentNoticeList";

describe("RecentNoticeList", () => {
  it("renders a notice title, topic label, date, and canonical link", () => {
    render(
      <RecentNoticeList
        notices={[
          {
            title: "2026학년도 개설강좌 안내",
            url: "https://example.com/course",
            source: "kumoh",
            published_at: "2026-03-20",
            topic_key: "course_openings",
            topic_label: "개설강좌조회",
          },
        ]}
      />,
    );

    expect(screen.getByRole("region", { name: "최근 공지" })).toBeInTheDocument();
    expect(screen.getByText("2026학년도 개설강좌 안내")).toBeInTheDocument();
    expect(screen.getByText("개설강좌조회 · 2026-03-20")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /2026학년도 개설강좌 안내/ })).toHaveAttribute(
      "href",
      "https://example.com/course",
    );
  });
});
```

`frontend/app/components/ChatMessage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatMessage } from "./ChatMessage";

describe("ChatMessage", () => {
  it("shows sources, recommendations, and recent notices for assistant messages", () => {
    render(
      <ChatMessage
        message={{
          id: 1,
          role: "assistant",
          content: "개설강좌는 공지에서 확인할 수 있습니다. [자료 1]",
          sources: [
            {
              title: "개설강좌 안내",
              url: "https://example.com/source",
              source: "kumoh",
              published_at: "2026-03-20",
              score: 0.9,
            },
          ],
          grounded: true,
          suggested_questions: ["수강신청 기간은?"],
          recent_notices: [
            {
              title: "최근 공지",
              url: "https://example.com/recent",
              source: "kumoh",
              published_at: "2026-03-21",
              topic_key: "course_openings",
              topic_label: "개설강좌조회",
            },
          ],
        }}
        isLoading={false}
        onSuggestion={vi.fn()}
      />,
    );

    expect(screen.getByText("개설강좌 안내")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "수강신청 기간은?" })).toBeInTheDocument();
    expect(screen.getByText("최근 공지")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: UI tests fail for missing components**

Run: `npm --prefix frontend run test -- --run`

Expected: module resolution errors for the three new component files.

- [ ] **Step 3: Implement minimal components**

`RecommendationChips.tsx`:

```tsx
"use client";

type Props = {
  questions: string[];
  disabled: boolean;
  onSelect: (question: string) => void;
};

export function RecommendationChips({ questions, disabled, onSelect }: Props) {
  if (questions.length === 0) return null;
  return (
    <section className="follow-up-section" aria-label="다음 질문 추천">
      <p className="follow-up-heading">다음 질문</p>
      <div className="recommendation-chips">
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(question)}
          >
            {question}
          </button>
        ))}
      </div>
    </section>
  );
}
```

`RecentNoticeList.tsx`는 `recent_notices.length === 0`일 때 `null`을 반환하고, 각 notice를 `target="_blank"`, `rel="noreferrer"` 링크 카드로 렌더링한다.

`ChatMessage.tsx`는 기존 `page.tsx`의 말풍선·출처 카드 구조를 이동하고 assistant일 때만 다음을 호출한다.

```tsx
<RecommendationChips
  questions={message.suggested_questions}
  disabled={isLoading}
  onSelect={onSuggestion}
/>
<RecentNoticeList notices={message.recent_notices} />
```

- [ ] **Step 4: UI 테스트 통과 확인**

Run: `npm --prefix frontend run test -- --run`

Expected: 3 component test files pass.

- [ ] **Step 5: 커밋**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/vitest.setup.ts frontend/app/components
git commit -m "test: add frontend follow-up components"
```

## Task 6: 채팅 페이지 통합과 읽기 쉬운 스타일 구현

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: 페이지 통합 테스트 작성**

`page.tsx`에서 fetch 응답의 `suggested_questions`와 `recent_notices`를 message state에 저장하도록 바꾸기 전에, `ChatMessage.test.tsx`에 다음 회귀 assertion을 추가한다.

```tsx
expect(screen.getByRole("region", { name: "다음 질문 추천" })).toBeInTheDocument();
expect(screen.getByRole("region", { name: "최근 공지" })).toBeInTheDocument();
```

- [ ] **Step 2: 기존 페이지가 새 응답 필드를 무시하는 상태를 확인**

Run: `npm --prefix frontend run test -- --run`

Expected: 새 assertion이 실패한다.

- [ ] **Step 3: page.tsx에 API 필드와 컴포넌트 연결**

`page.tsx`에서 중복 타입 정의를 제거하고 `components/types.ts`를 import한다. `initialMessage`에는 다음 기본값을 추가한다.

```tsx
suggested_questions: suggestions,
recent_notices: [],
```

API 응답을 assistant message로 저장하는 부분을 다음처럼 확장한다.

```tsx
{
  id: Date.now() + 1,
  role: "assistant",
  content: payload.answer,
  sources: payload.sources ?? [],
  grounded: payload.grounded,
  suggested_questions: payload.suggested_questions ?? [],
  recent_notices: payload.recent_notices ?? [],
}
```

오류 assistant message에는 두 배열을 빈 배열로 저장한다. `messages.map`은 기존 말풍선·로딩 마크업 대신 다음을 사용한다.

```tsx
<ChatMessage
  key={message.id}
  message={message}
  isLoading={isLoading}
  onSuggestion={(suggestion) => void submitQuestion(suggestion)}
/>
```

`ChatMessage`의 `onSuggestion`은 `submitQuestion`과 동일한 입력 검증·로딩 잠금 경로를 사용한다.

- [ ] **Step 4: 답변·카드 스타일 구현**

`globals.css`에 다음 스타일을 추가한다.

```css
.follow-up-section {
  margin-top: 12px;
}

.follow-up-heading,
.notice-heading {
  margin: 0 0 8px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
}

.recommendation-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.recommendation-chips button {
  padding: 8px 11px;
  color: var(--green-dark);
  border: 1px solid rgba(0, 102, 79, .2);
  border-radius: 999px;
  background: rgba(183, 237, 207, .25);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.recommendation-chips button:hover:not(:disabled) {
  background: rgba(183, 237, 207, .55);
}

.recommendation-chips button:disabled {
  cursor: wait;
  opacity: .5;
}

.recent-notice-list {
  display: grid;
  gap: 7px;
}

.notice-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 5px 12px;
  padding: 11px 13px;
  color: var(--ink);
  text-decoration: none;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: rgba(246, 248, 240, .9);
}

.notice-card:hover {
  border-color: rgba(0, 102, 79, .34);
  background: white;
}

.notice-card strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.notice-card small {
  color: var(--muted);
  font-size: 11px;
}

.notice-arrow {
  grid-row: 1 / span 2;
  grid-column: 2;
  color: var(--green);
  align-self: center;
}

@media (max-width: 720px) {
  .recommendation-chips {
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .recommendation-chips button {
    flex: 0 0 auto;
  }
}
```

메시지 본문에는 `white-space: pre-wrap`과 `overflow-wrap: anywhere`를 적용해 provider가 반환한 문단·목록과 긴 제목을 보존한다. `RecentNoticeList`에는 `aria-label="최근 공지"`를 둔다.

- [ ] **Step 5: 통합 UI 테스트 통과 확인**

Run: `npm --prefix frontend run test -- --run`

Expected: all component and integration assertions pass.

- [ ] **Step 6: 커밋**

```powershell
git add frontend/app/page.tsx frontend/app/globals.css frontend/app/components
git commit -m "feat: show chat recommendations and recent notices"
```

## Task 7: API·운영 문서와 평가 질문 반영

**Files:**
- Modify: `README.md`
- Modify: `docs/RAG_ARCHITECTURE.md`
- Modify: `docs/rag/data-pipeline.md`
- Modify: `docs/rag/retrieval-answering.md`
- Modify: `docs/rag/operations-evaluation.md`
- Modify: `docs/rag/overview.md`
- Modify: `data/evaluation/questions.json`

- [ ] **Step 1: 문서 회귀 기준 작성**

`data/evaluation/questions.json`에 최소한 다음 두 질문을 추가한다.

```json
{
  "question": "이번 학기 개설강좌를 알려줘",
  "expected_topic_key": "course_openings",
  "expected_latest_only": true,
  "expected_grounded": true
}
```

```json
{
  "question": "데이터에 없는 기숙사 식단을 알려줘",
  "expected_topic_key": "general",
  "expected_latest_only": true,
  "expected_grounded": false
}
```

- [ ] **Step 2: 문서 변경 전 기준 명령 실행**

Run: `git diff --check`

Expected: exit code `0`.

- [ ] **Step 3: 운영 명령과 최신성 규칙 문서화**

README와 `docs/rag/operations-evaluation.md`에 다음 명령을 추가한다.

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

문서에 다음 사실을 명시한다.

- `data/topic_rules.json`이 주제 관리의 단일 유지보수 지점이다.
- 원본 게시글 또는 규칙을 변경하면 `--reset` 전체 재인덱싱이 필요하다.
- `published_at` 우선, 누락 시 `crawled_at` fallback이다.
- 같은 주제의 이전 게시글은 답변 검색에서 제외된다.
- API 응답은 추천 질문과 최근 공지를 함께 반환한다.

`docs/rag/retrieval-answering.md`에는 Chroma where filter와 `is_latest_topic` metadata를 추가하고, `docs/rag/data-pipeline.md`에는 topic enrichment와 최신 post 계산을 추가한다.

- [ ] **Step 4: 문서·평가 파일 검증**

Run: `git diff --check`

Expected: exit code `0`.

- [ ] **Step 5: 커밋**

```powershell
git add README.md docs/RAG_ARCHITECTURE.md docs/rag data/evaluation/questions.json
git commit -m "docs: document topic freshness operations"
```

## Task 8: 전체 TDD 회귀 검증과 수동 UI 확인

**Files:**
- Verify: `backend/tests/`
- Verify: `frontend/app/components/`
- Verify: `README.md`

- [ ] **Step 1: 백엔드 전체 테스트 실행**

Run: `backend/.venv/Scripts/python -m pytest backend/tests -q`

Expected: all backend tests pass with zero failures.

- [ ] **Step 2: 백엔드 린트 실행**

Run: `backend/.venv/Scripts/python -m ruff check backend`

Expected: no Ruff errors.

- [ ] **Step 3: 프론트엔드 테스트 실행**

Run: `npm --prefix frontend run test -- --run`

Expected: all Vitest tests pass.

- [ ] **Step 4: 프론트엔드 린트 실행**

Run: `npm --prefix frontend run lint`

Expected: ESLint exits with code `0`.

- [ ] **Step 5: 프론트엔드 production build 실행**

Run: `npm --prefix frontend run build`

Expected: Next.js build completes with code `0`.

- [ ] **Step 6: 실제 로컬 흐름 확인**

Run backend and frontend with:

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
backend/.venv/Scripts/python -m uvicorn backend.app.main:app --reload
npm --prefix frontend run dev
```

Manual checklist:

- `개설강좌` 질문 답변의 source가 최신 게시글인지 확인
- 답변 뒤 추천 질문 칩이 보이고 클릭 시 새 질문이 전송되는지 확인
- 최근 공지 카드에 주제 라벨·게시일·원문 링크가 보이는지 확인
- 근거 부족 질문이 추측하지 않고 `grounded=false` 안내를 보이는지 확인
- 모바일 viewport에서 답변·칩·공지 카드가 가로로 잘리지 않는지 확인

- [ ] **Step 7: 최종 diff·상태 검토**

Run: `git diff --check; git status --short; git log -5 --oneline`

Expected: whitespace 오류 없음, 의도한 파일만 변경, 테스트·문서 커밋이 최근 기록에 존재한다.

- [ ] **Step 8: 최종 커밋 상태 확인**

```powershell
git status --short --branch
```

Expected: 구현 작업 관련 미커밋 변경이 없거나, 남은 변경이 사용자에게 명시된다.

## Plan Self-Review

- 주제 규칙 파일, 게시일 우선 최신성, Chroma filter, API 확장, A형 UI, 추천 질문, 최근 공지, 오류 처리, 백엔드·프론트엔드 테스트가 각각 Task 1~8에 연결되어 있다.
- 모든 신규 함수와 컴포넌트는 먼저 실패 테스트를 작성하는 순서를 갖는다.
- `topic_key`, `topic_label`, `is_latest_topic`, `suggested_questions`, `recent_notices` 이름을 계획 전체에서 일관되게 사용한다.
- `published_at`이 없는 자료의 fallback과 `general` 주제의 전체 최신 검색 동작을 명시했다.
- 생성 인덱스·로컬 DB·비밀값은 기존 `.gitignore` 규칙을 유지하며 커밋하지 않는다.
- 계획에는 미완성 표기나 임의의 “적절히 처리” 지시를 두지 않았다.
