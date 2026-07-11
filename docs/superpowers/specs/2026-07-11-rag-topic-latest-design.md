# SE Mentor Bot 주제별 최신성·추천 UX 설계

> 상태: 대화에서 최종 설계 승인 완료, 구현 계획 작성 전 문서 검토 단계

## 목표

금오공과대학교 소프트웨어전공 공개 게시글을 근거로 답변하는 RAG 챗봇에 주제별 최신성 관리와 답변 후속 UX를 추가한다. 특히 `개설강좌조회`처럼 같은 주제로 게시글이 반복되는 경우 게시일에 근거해 최신 게시글만 답변 근거로 사용하고, 답변 뒤에 추천 질문과 최근 공지를 함께 제공한다.

## 현재 기준선

- 백엔드: FastAPI, Chroma, 로컬 해시 임베딩/추출형 답변과 OpenAI provider
- 프론트엔드: Next.js 단일 채팅 화면
- 원본 데이터: `data/raw/posts.json`
- 청크와 검색 결과에는 제목, URL, 게시일, 출처가 있지만 주제 키가 없다.
- `ChatResponse`는 `answer`, `sources`, `grounded`만 반환한다.
- 기존 UI는 출처 카드와 초기 추천 질문을 제공하지만 답변별 추천 질문과 최근 공지는 제공하지 않는다.

## 요구사항

1. 유지보수자는 코드가 아닌 `data/topic_rules.json`에서 주제명, 키워드, 추천 질문을 수정할 수 있어야 한다.
2. 게시글과 사용자 질문을 동일한 `topic_key` 체계로 분류한다.
3. 동일한 주제에서는 `published_at`이 가장 최신인 게시글만 답변 검색 대상이 된다.
4. `published_at`이 없거나 유효하지 않으면 `crawled_at`으로 최신성을 비교한다.
5. 인덱스 재생성 시 이전 게시글의 최신 플래그가 남지 않아야 한다.
6. 답변 API는 답변, 출처, 추천 질문, 최근 공지를 함께 반환한다.
7. 추천 질문과 최근 공지는 답변 뒤에 읽기 쉬운 UI로 표시한다.
8. 근거가 부족할 때는 답변 provider를 호출하지 않고 추측하지 않는다.
9. 중요한 학사 정보는 원문 링크와 게시일을 통해 재확인할 수 있어야 한다.

## 범위 밖

- 과거 특정 연도 자료를 검색하는 날짜 의도 분석
- 데이터베이스를 Chroma 외부 서비스로 교체
- 첨부파일 본문 추출
- 로그인·접근제어 우회
- 실시간 스트리밍 답변

## 주제 규칙 데이터

`data/topic_rules.json`은 다음 형태를 사용한다.

```json
{
  "default_topic_key": "general",
  "topics": [
    {
      "key": "course_openings",
      "label": "개설강좌조회",
      "keywords": ["개설강좌", "개설 과목", "수강 가능 과목"],
      "suggested_questions": [
        "이번 학기 개설강좌를 알려줘",
        "개설강좌 조회 방법은?"
      ]
    },
    {
      "key": "general",
      "label": "전체 공지",
      "keywords": [],
      "suggested_questions": [
        "최근 학과 공지를 알려줘"
      ]
    }
  ]
}
```

분류 규칙은 결정적이어야 한다.

- 질문과 게시글 제목·본문을 공백 정규화 후 소문자 기준으로 비교한다.
- 일치하는 키워드가 있으면 가장 긴 키워드가 포함된 주제를 우선한다.
- 길이가 같으면 `topics` 배열에서 먼저 선언된 주제를 선택한다.
- 일치하는 주제가 없으면 `default_topic_key`인 `general`을 사용한다.
- 원본 게시글에 유효한 `topic_key`가 명시되어 있으면 자동 분류보다 우선해 수동 보정을 허용한다.

## 데이터 모델과 인덱싱

`BoardPost`와 `TextChunk`에 다음 필드를 추가한다.

```text
topic_key: str
topic_label: str
is_latest_topic: bool
```

인덱싱 순서:

```text
load posts
  → topic_key/topic_label 보정
  → topic_key별 최신 post_id 계산
  → chunk 생성
  → Chroma metadata에 topic과 최신 여부 저장
  → vector upsert
```

최신성 비교 키는 다음과 같다.

```text
유효한 published_at: (1, published_at, crawled_at)
그 외:                (0, crawled_at)
```

같은 주제의 게시글 중 비교 키가 가장 큰 게시글을 최신본으로 표시한다. 같은 게시글의 여러 청크는 모두 `is_latest_topic=true`가 되지만, 답변 출처는 URL 기준으로 중복 제거한다.

인덱스는 데이터 집합이 변경될 때 `backend.scripts.index --reset`으로 전체 재생성한다. 이렇게 해야 삭제되거나 최신본이 바뀐 게시글의 오래된 Chroma metadata가 남지 않는다. README와 운영 문서에 주제 규칙·원본 변경 후 재인덱싱 절차를 명시한다.

## 온라인 RAG 흐름

```text
question
  → question topic classification
  → latest-topic vector query
  → title rerank and score threshold
  → no result: grounded=false, provider not called
  → answer provider
  → related suggestions + latest notices
  → ChatResponse
```

질문에 주제가 분류되면 `topic_key`와 `is_latest_topic=true`를 함께 사용해 해당 주제의 최신 게시글만 검색한다. `general` 질문은 모든 주제의 최신 게시글을 대상으로 검색한다. 따라서 같은 주제의 과거 게시글은 검색 Top-K 안에 섞이지 않는다.

추천 질문은 분류된 주제의 `suggested_questions`를 우선 사용하고, 부족하면 `general` 추천 질문으로 채운다. 최근 공지는 최신 게시글 중 URL을 중복 제거하고 게시일 내림차순으로 최대 3건을 반환한다. 관련 주제가 있으면 해당 주제 공지를 먼저 배치한다.

## API 계약

```json
{
  "answer": "개설강좌는 ... [자료 1]",
  "sources": [
    {
      "title": "2026학년도 개설강좌 안내",
      "url": "https://example.com/post",
      "source": "kumoh",
      "published_at": "2026-03-19",
      "score": 0.81
    }
  ],
  "grounded": true,
  "suggested_questions": ["이번 학기 수강신청 기간은?"],
  "recent_notices": [
    {
      "title": "2026학년도 개설강좌 안내",
      "url": "https://example.com/post",
      "source": "kumoh",
      "published_at": "2026-03-19",
      "topic_key": "course_openings",
      "topic_label": "개설강좌조회"
    }
  ]
}
```

기존 `answer`, `sources`, `grounded` 필드는 유지해 API 호환성을 보존한다. 새 응답 모델에는 `suggested_questions`와 `recent_notices`를 빈 배열 기본값으로 둔다.

## 프론트엔드 설계

A안인 집중형 채팅을 유지하고, 각 assistant message의 하단을 다음 순서로 구성한다.

```text
답변 본문
  → 참고한 게시글 source 카드
  → 다음 질문 추천 칩
  → 최근 공지 카드
```

컴포넌트 책임:

- `ChatMessage`: 사용자/assistant 말풍선, 답변 본문, 하위 콘텐츠 배치
- `RecommendationChips`: 추천 질문을 버튼으로 렌더링하고 재질문 실행
- `RecentNoticeList`: 주제 라벨·게시일·원문 링크를 카드로 렌더링
- `page.tsx`: 대화 상태, API 요청, 로딩·오류 상태 조합

답변 텍스트는 줄바꿈과 목록을 보존하고, 출처 번호와 source 카드를 함께 보여준다. React의 기본 텍스트 렌더링을 사용해 API가 전달한 HTML을 실행하지 않는다. 데스크톱에서는 본문과 카드의 폭을 제한하고, 모바일에서는 카드와 추천 칩을 세로 또는 가로 스크롤로 배치한다.

## 오류 및 안전성

- 인덱스가 비어 있으면 기존 `409` 응답을 유지한다.
- 검색 결과가 임계값보다 낮으면 provider를 호출하지 않고 `grounded=false`를 반환한다.
- OpenAI 호출 실패는 기존 `502` 응답을 유지한다.
- 날짜 파싱 실패는 `crawled_at` fallback을 사용하되, 사용자에게는 확인 가능한 날짜만 표시한다.
- 주제 규칙에 없는 수동 `topic_key`는 무시하고 자동 분류한다.
- canonical URL과 원문 게시일은 원본 metadata에서만 생성한다. 모델이 URL을 만들어 내지 않는다.
- API 키와 비밀값은 로그·응답·문서에 기록하지 않는다.

## 테스트 전략

백엔드 pytest:

- 주제 키워드 우선순위와 `general` fallback
- 수동 topic override와 잘못된 override 처리
- 유효한 `published_at` 우선 비교
- 게시일 누락 시 `crawled_at` fallback
- 같은 주제의 최신 게시글만 `is_latest_topic`으로 남는지 확인
- Chroma query filter가 오래된 주제를 제외하는지 확인
- 추천 질문·최근 공지 생성 및 URL 중복 제거
- 근거 부족 시 provider 미호출
- `ChatResponse` 새 필드의 기본값과 직렬화

프론트엔드:

- assistant 답변에 source 카드, 추천 질문, 최근 공지가 표시되는지 확인
- 추천 질문 클릭이 입력 제출로 이어지는지 확인
- 빈 배열일 때 보조 영역이 숨겨지는지 확인
- 로딩·오류·모바일 레이아웃의 기본 상태를 확인

검증 명령:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests
backend/.venv/Scripts/python -m ruff check backend
npm --prefix frontend run lint
npm --prefix frontend run build
```

## 완료 기준

1. `개설강좌조회` 질문이 같은 주제의 최신 게시글만 source로 반환한다.
2. 답변 응답에 추천 질문과 최근 공지가 포함된다.
3. A 집중형 채팅 UI에서 두 영역이 답변 뒤에 읽기 쉽게 표시된다.
4. 주제 규칙 파일만 수정해 주제명·키워드·추천 질문을 관리할 수 있다.
5. 원본 또는 주제 규칙 변경 후 재인덱싱 절차가 README와 RAG 운영 문서에 설명된다.
6. 백엔드 테스트, 린트, 프론트엔드 린트와 빌드가 통과한다.
