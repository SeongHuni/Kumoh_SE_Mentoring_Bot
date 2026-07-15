# RAG 품질·최신성·데이터 감사 설계

> 기준일: 2026-07-13
> 대상 브랜치: `codex/rag-quality-hardening`
> 전체 백로그 진행 방식: 위험 우선 수직 완성형

## 1. 배경

자동 RAG 평가는 현재 30개 질문 중 25개를 통과한다. 주제 분류는 30/30이지만 grounded 25/30, latest-only 28/30, source-title 10/11로 검색 결과의 질문 적합성과 최신 공지 선택에 결함이 남아 있다.

실패는 다음 두 종류다.

- false-positive: `registration-period`, `capstone-second-semester`, `scholarship-apply`
- false-negative: `career-recruitment`, `general-recent-department`

현재 검색은 주제별 최신 게시글만 Chroma에서 찾은 뒤 단일 유사도 임계값으로 근거 여부를 결정한다. 이 방식은 질문에 명시된 연도·학기와 문서가 충돌해도 높은 유사도로 통과할 수 있고, 최신 공지 자체를 묻는 질문은 어휘가 다르다는 이유로 거절할 수 있다.

또한 `data/raw/posts.json`은 학과 게시판 중심 46건이며 `course_openings`의 최신 게시일이 2025-08-07이다. 검색 로직과 별개로 데이터 자체의 최신성·소스 누락·날짜 누락을 반복 검사할 수 있는 로컬 감사 도구가 필요하다.

## 2. 목표

1. 기존 30개 평가 기대값을 낮추거나 삭제하지 않고 30/30을 달성한다.
2. `topic_key`별 최신 게시글 1건만 답변 후보로 사용하는 기존 사용자 정책을 유지한다.
3. 질문의 연도·학기와 문서의 연도·학기가 충돌하면 해당 문서를 근거에서 제외한다.
4. 주제 최신 문서라도 제목이 질문의 주제나 구체 의도와 맞지 않으면 근거에서 제외한다.
5. “최근 학과 공지”처럼 최신성 자체가 핵심인 일반 질문은 의미 유사도보다 게시일을 우선한다.
6. 소스별 건수, 주제별 최신 문서, 오래된 자료, 날짜 누락, 분류 의심 항목을 JSON·Markdown으로 출력하는 데이터 감사 CLI를 제공한다.
7. 감사·평가 보고서에 게시글 본문, 환경 변수, 비밀값을 기록하지 않는다.

## 3. 비목표

- 공식 사이트의 라이브 데이터가 실제 최신인지 자동으로 확정하지 않는다.
- GitHub 보호 규칙, 운영 배포, OpenAI 임계값 튜닝을 이 하위 프로젝트에서 다루지 않는다.
- `freshness_scope_key`와 같이 한 주제 안에 여러 최신 문서를 유지하는 정책은 도입하지 않는다.
- 프론트엔드 응답 스키마나 화면 배치를 변경하지 않는다.
- PDF/HWP 첨부 본문 추출과 증분 삭제 감지는 후속 하위 프로젝트에서 다룬다.

## 4. 확정 정책

### 4.1 최신성 범위

“같은 주제”는 `data/topic_rules.json`의 `topic_key`로 정의한다. 인덱싱 시 유효한 `published_at`을 우선하고, 게시일이 없거나 파싱되지 않을 때만 `crawled_at`을 사용해 주제별 최신 게시글 1건을 표시한다.

이 정책은 넓은 주제에서 동시에 유효한 공지 일부를 제외할 수 있다. 이번 변경에서는 사용자가 지정한 “같은 주제의 최신 자료만 제공” 요구를 우선한다. 여러 문서를 동시에 최신으로 유지해야 한다는 운영 요구가 확인되면 별도 설계에서 문서 시리즈 단위 freshness scope를 도입한다.

### 4.2 근거 적합성

최신 문서라는 사실만으로 답변 근거가 되지는 않는다. 후보는 다음 조건을 순서대로 통과해야 한다.

1. 질문에 연도나 학기가 있으면 문서 제목에 같은 값이 있어야 한다. 제목에 다른 연도·학기가 명시되면 제외한다.
2. 기본 주제인 `general`에서 “최근 학과 공지”처럼 최신 전체 공지를 요청하면 전체 주제 최신 문서 중 게시일이 가장 최근인 문서를 선택한다.
3. 구체 주제 후보는 제목의 `evidence_markers`가 질문의 원래 표현 또는 설정된 동의어와 연결될 때 적합한 것으로 인정한다.
4. 제목에 주제 marker가 없더라도 질문의 구별 가능한 단어가 제목과 두 개 이상 일치하면 적합한 것으로 인정한다.
5. 위 조건을 만족하지 않으면 유사도 점수가 임계값 이상이어도 제외한다.

본문은 답변 생성에 사용하지만 근거 적합성의 1차 판정에는 사용하지 않는다. 본문에 우연히 포함된 “신청”, “기간” 같은 단어가 무관한 공지를 통과시키는 것을 막기 위함이다.

### 4.3 실패 5건의 기대 동작

| 평가 ID | 현재 문제 | 변경 후 동작 |
| --- | --- | --- |
| `registration-period` | 조기취업자 출석인정 공지를 수강신청 기간 근거로 사용 | 제목에 수강신청 marker·구체 단어가 없어 거절 |
| `capstone-second-semester` | 2026년 1학기 문서를 2학기 질문에 사용 | 학기 충돌로 거절 |
| `scholarship-apply` | 부트캠프 설명회를 장학금 신청 공지로 사용 | 제목에 장학 marker·구체 단어가 없어 거절 |
| `career-recruitment` | “채용”과 “초빙” 표현 차이로 최신 공지를 놓침 | career marker·동의어로 인정 |
| `general-recent-department` | 일반 최신 질문이 낮은 의미 점수로 거절됨 | 최신 전체 공지 모드에서 게시일 우선 선택 |

## 5. 구성요소

### 5.1 주제·검색 정책 설정

`data/topic_rules.json`의 각 주제에 `evidence_markers`를 추가한다. 예시는 다음과 같다.

```json
{
  "key": "career",
  "label": "진로·취업",
  "keywords": ["취업", "채용", "인턴", "진로"],
  "evidence_markers": ["취업", "채용", "초빙", "인턴", "진로"],
  "suggested_questions": ["최근 취업 프로그램을 알려줘", "인턴 관련 공지가 있어?"]
}
```

최상위 `retrieval_policy`에는 다음 값을 둔다.

```json
{
  "recency_terms": ["최근", "최신", "이번"],
  "generic_terms": ["공지", "안내", "알려줘", "찾아줘", "관련", "방법", "뭐야"],
  "alias_groups": [
    ["채용", "초빙"],
    ["수강변경", "수강 변경"]
  ]
}
```

`TopicCatalog`는 이 값을 불변 tuple로 로딩한다. 빈 marker, 한 단어뿐인 alias group, 중복 주제 key, 존재하지 않는 기본 주제는 `ValueError`로 거절한다. 기존 설정 파일과 테스트 fixture를 위해 누락된 `retrieval_policy`와 `evidence_markers`는 빈 기본값으로 허용한다.

### 5.2 질문 의도 분석

신규 `backend/app/query_intent.py`는 다음 불변 값을 만든다.

```python
from typing import Literal

@dataclass(frozen=True)
class QueryIntent:
    topic_key: str
    requested_year: int | None
    requested_term: Literal["first", "second", "summer", "winter"] | None
    recency_requested: bool
    match_terms: tuple[str, ...]
    distinctive_terms: tuple[str, ...]
```

분석 규칙은 다음과 같다.

- `20xx학년도`, `20xx년`, 독립된 `20xx`에서 연도를 추출한다.
- `1학기`, `2학기`, `여름계절`, `겨울계절`을 구분한다.
- 질문의 모든 의미 단어와 동의어 확장값을 `match_terms`에 보존해 제목 marker 비교에 사용한다.
- 주제 keywords, recency terms, generic terms를 제외한 2글자 이상의 단어를 구별 단어로 남긴다.
- alias group에 속한 단어는 같은 비교 집합으로 확장한다.
- 분석은 결정적이며 외부 모델을 호출하지 않는다.

### 5.3 근거 정책

신규 `backend/app/evidence_policy.py`는 `QueryIntent`, `TopicRule`, `RetrievedChunk`를 받아 후보 적합성을 판정한다.

판정 결과는 디버깅과 테스트를 위해 이유 코드를 포함한다.

```python
@dataclass(frozen=True)
class EvidenceDecision:
    accepted: bool
    reason: str
```

허용 reason은 `accepted_general_latest`, `accepted_topic_marker`, `accepted_title_overlap`이고 거절 reason은 `year_mismatch`, `semester_mismatch`, `missing_temporal_evidence`, `insufficient_title_evidence`다. API에는 reason을 노출하지 않고 서버 내부 진단에만 사용한다.

질문이 특정 연도·학기를 명시했는데 제목에 해당 값이 없으면 `missing_temporal_evidence`로 거절한다. 제목에 다른 값이 있으면 각각 `year_mismatch`, `semester_mismatch`로 거절한다. 날짜가 없는 문서는 특정 기간 질문의 근거로 인정하지 않는다.

### 5.4 RAG 연결

`RAGService.ask()`는 다음 순서로 동작한다.

1. 기존 `TopicCatalog.classify()`로 주제를 결정한다.
2. `analyze_query()`로 `QueryIntent`를 만든다.
3. 기본 주제의 최신 전체 질문이면 `posts`에서 가장 최근인 `is_latest_topic=true` 게시글 URL을 선택하고 Chroma `where`에 URL을 포함한다.
4. 나머지는 기존처럼 `is_latest_topic=true`와 구체 `topic_key`를 적용한다.
5. 의미 점수와 제목 hit로 재정렬한 뒤 `EvidencePolicy`로 부적합 후보를 제거한다.
6. 적합 후보가 없으면 provider answer를 호출하지 않고 기존 `NO_ANSWER` 응답을 반환한다.
7. 적합 후보가 있으면 기존 answer·source·추천 질문·최근 공지 계약을 유지한다.

기본 최신 전체 질문의 URL 필터는 Chroma metadata에 이미 저장되는 `url`을 사용한다. 새로운 벡터 저장 스키마는 필요하지 않다.

## 6. 데이터 감사

### 6.1 순수 감사 계층

신규 `backend/app/data_audit.py`는 `BoardPost` 목록과 `TopicCatalog`를 입력으로 받아 다음 정보만 반환한다.

- 총 게시글 수와 source별 건수
- 주제별 건수, 최신 제목·URL·게시일
- 게시일 누락·파싱 실패 건수
- 설정된 필수 source(`kumoh`, `seboard`) 누락
- 최신 게시일이 기준 시점보다 오래된 주제
- 기존 topic override와 현재 규칙 분류가 다른 항목의 ID·제목·URL

오래된 자료 기준은 CLI 기본 180일이며 `--stale-after-days`로 변경할 수 있다. 감사 결과에는 본문과 첨부 본문을 포함하지 않는다.

### 6.2 CLI

신규 `backend/scripts/audit_data.py`는 다음 계약을 갖는다.

```text
python -m backend.scripts.audit_data
  --posts data/raw/posts.json
  --topic-rules data/topic_rules.json
  --output-dir data/audit/reports
  --stale-after-days 180
  --required-source kumoh
  --required-source seboard
```

- exit 0: 필수 source·날짜·staleness 경고가 없음
- exit 1: 감사를 완료했으나 품질 경고가 있음
- exit 2: 입력 파일·설정·보고서 기록 오류

`latest.json`과 `latest.md`는 임시 파일에 먼저 쓴 뒤 둘 다 성공할 때 교체한다. 기존 평가 CLI의 rollback 동작을 `backend/app/reporting.py` 공용 writer로 추출해 평가와 감사가 같은 원자적 기록 계약을 사용한다. 보고서 경로는 Git에서 제외한다.

### 6.3 수집 데이터 보호

기존 crawl 기본 동작은 한 source라도 실패하면 `posts.json`을 덮어쓰지 않는다. 이 하위 프로젝트에서 `--allow-partial` 결과는 기본적으로 `data/raw/candidates/posts-partial.json`에 저장하고 운영 원본과 구분한다. `--partial-output`으로 후보 경로를 바꿀 수 있지만 운영 `RAW_POSTS_PATH`와 같은 경로는 거절한다. 일부 결과를 저장해도 source 실패가 있었으므로 CLI는 기존 계약대로 exit 2를 반환한다. `data/raw/candidates/`는 Git에서 제외한다.

감사 exit 0은 라이브 원문이 실제 최신임을 보증하지 않으며, 사람이 공식 URL과 날짜를 대조하기 전에는 기존 baseline을 자동 변경하지 않는다.

## 7. 오류 처리

- 잘못된 topic·retrieval 정책 JSON은 명확한 `ValueError`로 중단한다.
- 질문 의도 분석 실패는 묵살하지 않는다. 지원 형식이 아닌 날짜 표현은 기간 조건 없음으로 처리하되 테스트된 형식만 계약으로 문서화한다.
- 후보가 기간·제목 검증에서 모두 제외되면 정상적인 `grounded=false` 응답을 반환한다.
- 근거 없음 응답에서도 추천 질문과 최근 공지는 유지한다.
- 감사 입력이 없거나 비어 있으면 exit 2로 종료하고 기존 보고서를 교체하지 않는다.
- 감사 품질 경고는 실행 오류와 구분해 exit 1로 반환한다.

## 8. 파일 경계

| 파일 | 책임 |
| --- | --- |
| `backend/app/query_intent.py` | 질문의 날짜·학기·최근성·구별 단어 분석 |
| `backend/app/evidence_policy.py` | 검색 후보의 기간·제목 적합성 판정 |
| `backend/app/data_audit.py` | 게시글 데이터 감사 모델·집계·렌더링 |
| `backend/app/reporting.py` | 평가·감사 JSON/Markdown 쌍의 원자적 기록과 rollback |
| `backend/scripts/audit_data.py` | 감사 CLI 인자·입출력·종료 코드 |
| `backend/scripts/evaluate.py` | 기존 보고서 기록을 공용 writer에 위임 |
| `backend/scripts/crawl.py` | 부분 수집 후보와 운영 원본의 출력 경로 분리 |
| `backend/app/topic_rules.py` | retrieval policy와 evidence marker 검증·로딩 |
| `backend/app/rag.py` | 의도 분석과 근거 정책을 기존 RAG 흐름에 연결 |
| `data/topic_rules.json` | 사람이 관리하는 주제 marker·동의어·일반 표현 |
| `backend/tests/test_query_intent.py` | 질문 의도 분석 단위 계약 |
| `backend/tests/test_evidence_policy.py` | 기간 충돌·marker·제목 overlap 계약 |
| `backend/tests/test_data_audit.py` | 감사 집계·보안·Markdown 계약 |
| `backend/tests/test_audit_data_script.py` | CLI exit·보고서 트랜잭션 계약 |
| `backend/tests/test_crawl_script.py` | 부분 수집이 운영 원본을 덮어쓰지 않는 계약 |
| `backend/tests/test_rag.py` | RAG 연결과 provider 미호출 회귀 |
| `.gitignore` | 감사 보고서·부분 수집 후보 제외 |

## 9. TDD 검증 전략

구현 순서는 항상 RED → GREEN → 전체 회귀다.

1. `QueryIntent` import와 연도·학기·최근성·동의어 테스트를 작성하고 모듈 부재 RED를 확인한다.
2. `EvidencePolicy`의 기간 충돌과 제목 근거 테스트를 작성하고 symbol 부재 RED를 확인한다.
3. 실패 5건과 같은 형태의 RAG service 테스트를 작성해 현재 잘못된 grounded 결과를 재현한다.
4. 최소 구현으로 각 테스트를 통과시킨다.
5. 부분 수집 후보 경로 테스트를 작성해 기존 원본 덮어쓰기 RED를 확인한 뒤 crawl CLI를 강화한다.
6. 감사 순수 계층과 CLI 테스트를 먼저 작성하고 RED를 확인한 뒤 구현한다.
7. 인덱스를 재생성하고 기존 30문항 평가를 실행한다.

완료 검증은 다음을 모두 포함한다.

- backend pytest 전체 통과
- backend Ruff 통과
- frontend Vitest·TypeScript·ESLint·production build 통과
- 평가 30/30, quality exit 0
- 감사 보고서 생성 및 현재 데이터 경고의 정확한 기록
- `git diff --check` 통과
- 평가·감사 보고서와 Chroma DB가 Git에서 제외됨
- 보고서 민감정보·게시글 본문 패턴 검사 통과

## 10. 보안과 개인정보

- 질문과 게시글 본문은 감사 보고서에 저장하지 않는다.
- 평가 보고서의 기존 question·source metadata 계약은 유지하되 answer와 본문은 추가하지 않는다.
- 환경 변수, API key, provider secret, 로컬 절대 경로를 보고서에 기록하지 않는다.
- 감사 분류 의심 항목은 ID·제목·공개 URL·주제 key만 포함한다.

## 11. 배포·되돌리기

이 변경은 API schema와 프론트엔드 계약을 바꾸지 않는다. 새 근거 정책 때문에 일부 질문이 `grounded=true`에서 `false`로 바뀌는 것은 의도된 안전성 강화다.

문제가 생기면 RAG 연결 커밋만 되돌려 기존 검색 경로로 복귀할 수 있다. 주제 규칙 확장은 기존 필드와 하위 호환되므로 설정 파일 전체를 되돌릴 필요가 없다. 감사 CLI는 런타임 요청 경로와 독립적이어서 별도로 비활성화할 수 있다.

## 12. 전체 백로그에서의 위치

이 설계가 완료되면 다음 하위 프로젝트를 순서대로 진행한다.

1. 백엔드 테스트 85%와 임베딩 fingerprint
2. API 보호와 관측성
3. 프론트엔드 통합/E2E와 접근성
4. CI, Docker healthcheck, 의존성 정리
5. 데이터 수명주기와 첨부 문서 처리

각 하위 프로젝트는 독립 설계·계획·검증 기록을 갖는다. 외부 계정이나 라이브 사이트 상태가 필요한 단계는 로컬 구현과 fixture 검증을 완료한 뒤 외부 검증 대기로 명확히 표시한다.

## 13. 완료 조건

- 사용자 승인 정책이 코드·설정·문서에 일관되게 반영된다.
- 기존 평가 기대값 변경 없이 30개 질문이 모두 통과한다.
- false-positive 3건은 provider를 호출하지 않는 근거 없음 응답이 된다.
- false-negative 2건은 최신 URL과 게시일을 포함한 근거 응답이 된다.
- 현재 데이터 감사 결과가 재현 가능한 JSON·Markdown으로 생성된다.
- 부분 수집 실패 시 운영 `posts.json`은 유지되고 후보 파일만 별도 생성된다.
- 라이브 데이터 확인이 필요한 항목과 로컬에서 완료한 항목이 상태 문서에서 분리된다.
