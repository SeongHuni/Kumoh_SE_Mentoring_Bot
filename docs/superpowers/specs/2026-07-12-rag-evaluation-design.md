# SE Mentor Bot 자동 RAG 평가 설계

> 작성일: 2026-07-12
> 상태: 사용자 설계 승인 완료, 구현 계획 작성 전
> 기준 브랜치: `main`

## 1. 목적

현재 SE Mentor Bot은 주제 분류, 주제별 최신 게시글 필터, 근거 기반 답변, 추천 질문과 최근 공지를 구현했다. 그러나 품질 확인이 수동 질문과 단위 테스트에 의존해 데이터·규칙·검색 임계값이 바뀔 때 전체 품질 저하를 반복 측정하기 어렵다.

이번 작업은 현재 Chroma 인덱스와 RAG 경로를 실제로 실행해 다음 네 가지를 자동 검증하는 오프라인 평가 도구를 만든다.

1. 질문이 기대 주제로 분류되는가
2. 근거가 있어야 하는 질문과 거절해야 하는 질문을 구분하는가
3. 답변 source가 주제별 최신 게시글인가
4. 지정한 핵심 source 제목을 검색했는가

## 2. 범위

### 포함

- local provider 기반 End-to-End RAG 평가
- 최소 30개 구조화 평가 질문
- 평가 입력 스키마 검증
- 케이스별 검사 결과와 실패 이유
- JSON·Markdown 보고서 생성
- 성공·평가 실패·실행 오류를 구분하는 CLI 종료 코드
- 단위 테스트와 CLI 회귀 테스트
- README, 운영 문서, 프로젝트 상태와 인수인계 갱신

### 제외

- 실시간 공식 게시판 재수집
- OpenAI 품질 기준 또는 모델 간 A/B 평가
- 자동 임계값 최적화
- 웹 대시보드
- CI workflow 추가
- 런타임 `/api/chat` 응답 스키마 변경

OpenAI 평가는 CLI의 `configured` provider 선택으로 실행 가능하게 하되, 이번 완료 기준과 자동 테스트는 local provider만 사용한다.

## 3. 접근안 비교와 결정

### 접근안 A — End-to-End 평가

질문 분류부터 벡터 검색, 점수 필터, 답변과 source 생성까지 실제 `RAGService.ask()`를 실행한다. 사용자에게 보이는 결과를 가장 가깝게 검증하고 기존 RAG wiring을 재사용할 수 있어 이번 방식으로 선택한다.

### 접근안 B — 검색 전용 평가

Chroma 검색 결과만 검사하므로 빠르지만 `grounded`, source 중복 제거, 답변 거절 경로를 놓친다. 향후 검색 세부 지표가 필요하면 별도 evaluator로 확장한다.

### 접근안 C — Local/OpenAI 동시 평가

provider 비교에는 유용하지만 비용·quota·응답 변동이 자동 회귀 기준을 불안정하게 만든다. 이번 CLI는 확장 지점만 제공하고 기본 실행에서는 제외한다.

## 4. 파일 구조와 책임

| 파일 | 책임 |
| --- | --- |
| `backend/app/evaluation.py` | 평가 입력·결과 모델, 로더, 케이스 평가, 집계, Markdown 렌더링 |
| `backend/scripts/evaluate.py` | CLI 인자, local/configured provider 선택, 실제 RAG wiring, 보고서 저장, 종료 코드 |
| `backend/tests/test_evaluation.py` | 입력 검증, 개별 check, 집계, 보고서 단위 테스트 |
| `backend/tests/test_evaluate_script.py` | 빈 인덱스, 최소 케이스 수, 성공·실패 종료 코드 테스트 |
| `data/evaluation/questions.json` | 30개 이상의 구조화 평가 케이스 |
| `data/evaluation/reports/` | 생성 보고서 위치; Git 커밋 제외 |
| `.gitignore` | 평가 보고서 제외 규칙 |
| `docs/rag/operations-evaluation.md` | 실행 명령과 결과 해석 |
| `docs/PROJECT_STATUS.md` | P1-1 진행·완료 상태와 검증 근거 |
| `docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md` | 중간 진행도, 마지막 RED/GREEN, 다음 작업 |

`evaluation.py`는 FastAPI나 argparse에 의존하지 않는 순수 평가 계층으로 유지한다. CLI는 기존 `config`, `provider_factory`, `storage`, `topic_classifier`, `vector_store`, `RAGService`를 조합하는 얇은 wiring 계층이다.

## 5. 평가 입력 스키마

각 케이스는 다음 형태를 사용한다.

```json
{
  "id": "course-openings-current-semester",
  "question": "이번 학기 개설강좌를 알려줘",
  "category": "개설강좌",
  "expected_topic_key": "course_openings",
  "expected_grounded": true,
  "expected_latest_only": true,
  "expected_source_title_contains": ["수강신청 안내"],
  "notes": "현재 저장 데이터 기준 최신 개설강좌 공지"
}
```

필수 필드:

- `id`: kebab-case 고유 식별자
- `question`: 2~500자 질문
- `category`: 사람이 읽는 평가 분류
- `expected_topic_key`: `data/topic_rules.json`에 존재하는 주제 키
- `expected_grounded`: 기대 근거 여부
- `expected_latest_only`: 최신 source 검사 수행 여부

선택 필드:

- `expected_source_title_contains`: 각 문자열이 source 제목 중 하나에 포함돼야 하는 목록
- `notes`: 데이터 변경 시 기대값을 갱신할 이유와 배경

로더는 JSON 배열, 빈 값, 중복 `id`, 잘못된 id 형식, 필수 필드, 질문 길이를 검증한다. `expected_grounded=false`인데 source 제목 기대값이 있으면 모순된 케이스로 거절한다. `expected_topic_key`가 실제 catalog에 존재하는지는 evaluator 생성 단계에서 검증한다.

## 6. 평가 데이터 구성

최소 30개를 다음 분포로 구성한다.

| 영역 | 최소 개수 | 주요 검증 |
| --- | ---: | --- |
| 개설강좌 | 4 | 주제 분류, 최신 학기 source, 조회 방법 |
| 수강신청 | 5 | 일정·변경·출석인정, 현재 최신 공지 한계 |
| 캡스톤 | 4 | 신청·운영 계획·대상 |
| 진로·취업 | 4 | 프로그램·인턴·현재 최신 career 공지 |
| 장학금 | 4 | 신청·선발·현재 최신 scholarship 공지 |
| 졸업요건 | 3 | 데이터 부재 시 거절과 추천 유지 |
| 일반 공지 | 3 | default topic과 최신 일반 공지 |
| 범위 밖 | 3 | 식단·기숙사·날씨 등 추측 거절 |

평가셋은 현재 저장 데이터의 baseline이다. 공식 데이터를 재수집하면 source 제목과 `expected_grounded`를 사람이 원문과 대조해 갱신한다. 데이터가 오래됐다는 사실을 숨기기 위해 기대값을 임의로 성공 처리하지 않는다.

CLI 구현이 완료돼도 실제 품질 실패가 남을 수 있다. 이 경우 도구 구현은 완료로 기록하되 실행 결과는 exit code 1과 보고서에 남기고, 기대값을 실제 오답에 맞춰 낮추지 않는다. RAG 개선은 실패 케이스를 근거로 별도 TDD 작업으로 진행한다.

## 7. 평가 모델

### EvaluationCase

입력 한 건을 표현하는 Pydantic 모델이다. 문자열 trim, id 형식, 질문 길이와 source 제목 fragment의 빈 값을 검증한다.

### EvaluationChecks

각 검사 결과를 다음 필드로 보존한다.

- `topic_match`
- `grounded_match`
- `latest_only_match`
- `source_title_match`

기대 source 제목이 없으면 `source_title_match`는 적용 대상이 아니므로 `null`을 사용한다. `expected_latest_only=false`도 같은 방식으로 `latest_only_match=null`을 사용한다.

### EvaluationResult

다음을 포함한다.

- 입력 식별자·질문·category
- 기대값과 실제 topic·grounded
- 실제 source 제목·URL·게시일
- `EvaluationChecks`
- 사람이 바로 원인을 알 수 있는 `failures`
- 모든 적용 가능한 check가 통과했는지를 나타내는 `passed`

### EvaluationReport

다음을 포함한다.

- 생성 시각, provider, embedding/chat model, 인덱스 청크 수
- 전체·통과·실패 케이스 수
- topic accuracy
- grounded accuracy
- latest-only compliance
- source-title accuracy
- 케이스별 `EvaluationResult`

각 metric은 적용 가능한 케이스만 분모로 사용한다. 분모가 0이면 `null`을 기록한다.

## 8. 검사 규칙

### Topic

`TopicCatalog.classify(question).key`가 `expected_topic_key`와 같아야 한다.

### Grounded

`RAGService.ask(question).grounded`가 `expected_grounded`와 같아야 한다. `grounded=false`인데 source가 있거나 `grounded=true`인데 source가 없으면 별도 실패 이유를 추가한다.

### Latest-only

인덱싱 전과 같은 `enrich_posts()` 결과에서 `is_latest_topic=true`인 게시글 URL 집합을 만든다.

- 구체 주제는 기대 주제의 최신 URL만 허용한다.
- `general`은 모든 주제의 최신 URL을 허용한다.
- source가 없고 `expected_grounded=false`이면 통과한다.
- source URL이 허용 집합 밖이면 과거 또는 잘못된 주제 source로 실패한다.

### Source title

`expected_source_title_contains`의 각 fragment가 실제 source 제목 중 적어도 하나에 포함돼야 한다. fragment별 누락 내용을 실패 이유에 기록한다.

## 9. CLI 인터페이스

기본 실행:

```powershell
backend/.venv/Scripts/python -m backend.scripts.evaluate
```

지원 인자:

- `--questions PATH`: 기본 `data/evaluation/questions.json`
- `--output-dir PATH`: 기본 `data/evaluation/reports`
- `--provider local|configured`: 기본 `local`
- `--minimum-cases N`: 기본 `30`
- `--limit N`: 첫 N개 smoke 실행; 최소 케이스 검사는 원본 전체 데이터에 적용

보고서는 `latest.json`, `latest.md` 두 파일로 원자적으로 교체한다. 터미널에는 전체·통과·실패 수와 각 metric을 출력한다.

종료 코드:

| 코드 | 의미 |
| ---: | --- |
| `0` | 모든 케이스 통과 |
| `1` | 실행은 완료됐으나 하나 이상의 평가 케이스 실패 |
| `2` | 입력·설정·데이터·인덱스 오류로 평가를 완료하지 못함 |

빈 인덱스, 평가 파일 없음, 30개 미만, 중복 id, 존재하지 않는 topic key는 답변 생성 전에 종료 코드 2로 실패한다.

## 10. 데이터 흐름

```text
questions.json
  → schema validation
  → topic catalog validation
  → raw posts enrichment
  → local/configured provider + Chroma + RAGService
  → case evaluation
  → aggregate metrics
  → latest.json + latest.md
  → exit 0/1/2
```

평가 CLI는 게시글이나 인덱스를 수정하지 않는다. 인덱스 재생성은 기존 `backend.scripts.index --reset` 명령의 책임이다.

## 11. 오류 처리와 보안

- 평가 질문과 source metadata만 보고서에 기록하고 답변 전문은 기본 보고서에서 제외한다.
- API key, 환경변수 전체 값, 원문 게시글 본문은 기록하지 않는다.
- `configured`가 OpenAI를 선택했는데 키가 없으면 종료 코드 2와 명확한 설정 오류를 반환한다.
- 보고서 저장은 임시 파일 작성 후 replace하여 중간 파일을 남기지 않는다.
- 생성 보고서 디렉터리는 Git에서 제외한다.

## 12. 테스트 전략

TDD 순서로 다음을 검증한다.

1. 유효한 평가셋 로딩과 중복·잘못된 입력 거절
2. topic·grounded 검사 성공/실패
3. 구체 주제와 general의 최신 URL 허용 범위
4. source 제목 fragment 검사
5. metric 분모와 성공률 집계
6. Markdown 보고서의 요약·실패 이유
7. CLI 최소 케이스 수와 빈 인덱스 오류
8. CLI 평가 실패 exit 1, 성공 exit 0, 실행 오류 exit 2
9. 현재 30개 평가셋 local 실행
10. backend 전체 pytest·Ruff와 기존 frontend 회귀

테스트는 fake RAG callable과 임시 JSON·임시 Chroma 경로를 사용한다. 외부 게시판과 유료 API를 호출하지 않는다.

## 13. 완료 조건

- 구조화된 평가 케이스가 30개 이상이다.
- local provider 기본 실행이 JSON·Markdown 보고서를 만든다.
- 케이스 실패와 실행 오류의 종료 코드가 구분된다.
- topic·grounded·latest-only·source-title 검사 결과가 보고서에 나타난다.
- 생성 보고서와 민감정보가 Git에 포함되지 않는다.
- 신규 테스트가 RED→GREEN으로 검증된다.
- backend 전체 pytest·Ruff, frontend test·lint·type·build가 통과한다.
- `PROJECT_STATUS.md`, 운영 문서, 인수인계 문서에 결과와 다음 작업이 기록된다.

## 14. 후속 확장

이번 범위 완료 후 독립 작업으로 진행한다.

1. 검색 Top-K·점수·기대 문서 rank를 측정하는 retrieval evaluator
2. Local/OpenAI 결과 비교와 비용·지연시간 기록
3. CI에서 local 평가를 품질 gate로 실행
4. 공식 데이터 재수집 후 baseline 갱신 승인 절차
5. 평가 추세를 비교하는 history report
