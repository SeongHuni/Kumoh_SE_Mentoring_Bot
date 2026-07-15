# 백엔드 품질 게이트와 인덱스 호환성 설계

> 기준일: 2026-07-15
>
> 대상 브랜치: `codex/backend-quality-gates`
>
> 구현 묶음: 백엔드 커버리지, 임베딩·인덱스 fingerprint, GitHub Actions CI

## 1. 배경

현재 RAG 챗봇은 로컬 회귀 테스트 94개, Ruff, 프론트엔드 테스트 9개를 통과한다. 자동 평가도 기존 30개 질문을 통과하지만, 다음 운영 위험은 자동으로 차단되지 않는다.

- 임베딩 provider, 모델, 차원 또는 청킹 설정을 바꾼 뒤 예전 Chroma 인덱스를 그대로 사용할 수 있다.
- `data/raw/posts.json`이나 `data/topic_rules.json`이 갱신되어도 인덱스가 이전 자료인지 API가 구분하지 못한다.
- 인덱스가 일부만 기록되거나 manifest가 손상되어도 청크 수가 1개 이상이면 `/api/health`가 `ready`를 반환한다.
- 커버리지 기준과 GitHub Actions가 없어 로컬 검증을 생략한 변경이 병합될 수 있다.
- 현재 `--cov=backend` 기준 표시값은 86%지만 테스트 코드까지 측정한다. 제품 코드만 계산하고 요청 범위에서 제외된 `backend/app/crawling/seboard.py`를 빼면 기준선은 1,229/1,447줄, 약 84.93%다.

이번 변경은 인덱스를 생성한 조건과 현재 런타임 조건이 정확히 맞는 경우에만 채팅을 허용하고, 제품 코드 커버리지 85%와 양쪽 애플리케이션 검증을 CI에서 강제한다.

## 2. 핵심 결정 3개

1. Chroma 내부 metadata가 아닌 `chroma_path/index-manifest.json` sidecar를 호환성의 단일 증거로 사용한다. 사람이 열어 확인할 수 있고 Chroma 버전에 덜 결합되며, 인덱스 디렉터리와 함께 백업·복원할 수 있기 때문이다.
2. 호환성 오류는 경고만 남기지 않고 fail-closed로 처리한다. 인덱스가 비어 있거나 manifest가 없거나 현재 설정·입력과 다르면 `/api/chat`을 차단하고 재인덱싱 방법을 안내한다.
3. 커버리지는 테스트 파일을 제외한 `backend.app`과 `backend.scripts`만 측정한다. 사용자가 제외한 SE 게시판 수집 모듈만 명시적으로 omit하고, 나머지는 85% 미만이면 CI를 실패시킨다.

## 3. 목표

1. provider, 임베딩 모델, 차원, collection, 청킹 설정, 원본 게시글, 주제 규칙 중 하나라도 바뀌면 기존 인덱스를 사용할 수 없게 한다.
2. 완전히 성공한 인덱싱만 유효한 manifest를 남기고, 실패한 재구축은 이전 manifest로 위장하지 못하게 한다.
3. `/api/health`에서 설정 누락, 빈 인덱스, 재인덱싱 필요, 준비 완료를 구분한다.
4. 호환되지 않는 인덱스에서 provider 호출과 답변 생성을 모두 막는다.
5. backend 제품 코드 line coverage 85% 이상을 로컬과 CI에서 같은 명령으로 검증한다.
6. GitHub Actions에서 외부 API나 라이브 크롤링 없이 backend와 frontend 품질 검사를 재현한다.
7. 환경 변수, API key, 게시글 본문, 로컬 절대 경로를 manifest나 API 응답에 기록하지 않는다.

## 4. 비목표

- `backend/app/crawling/seboard.py` 구현, fixture, 권한, 라이브 수집 검증은 변경하지 않는다.
- 프론트엔드 Playwright E2E와 자동 접근성 검사는 별도 구현 묶음으로 둔다.
- rate limit, 구조화 로그, 요청 추적 ID, Docker healthcheck, 백업·복원 자동화는 별도 운영 강화 묶음으로 둔다.
- OpenAI 유료 API를 호출하는 품질 평가와 라이브 사이트 검증은 CI에 넣지 않는다.
- 증분 인덱싱, 여러 Chroma collection의 동시 운영, 무중단 blue/green 인덱스 교체는 도입하지 않는다.
- 생성된 Chroma DB, coverage 산출물, 로컬 환경 파일은 Git에 커밋하지 않는다.

## 5. 검토한 접근법

### 5.1 채택: sidecar manifest와 엄격한 런타임 차단

인덱스 생성 조건을 독립 JSON 파일로 기록하고 매 health·chat 요청에서 현재 조건과 비교한다. 구현과 테스트가 단순하고, 운영자가 파일만으로 생성 이력을 확인할 수 있다. manifest 기록 실패 시 채팅을 막는 보수적인 동작도 명확하다.

### 5.2 제외: Chroma collection metadata

collection metadata에 fingerprint를 넣으면 파일 수는 줄지만 Chroma 생성·reset 동작과 버전별 metadata 갱신 규칙에 더 강하게 결합된다. 인덱스가 손상된 상황에서 호환성 증거도 함께 읽지 못하며, 사람이 비교하기도 어렵다.

### 5.3 제외: 불일치 경고 후 계속 서비스

가용성은 높지만 최신 자료와 다른 모델 차원의 인덱스로 답할 수 있다. 이 챗봇은 공식 공지를 근거로 안내하므로, 오래되거나 호환되지 않는 근거로 답하는 것보다 명시적으로 재인덱싱을 요구하는 편이 안전하다.

## 6. 설정 계약

`backend/app/config.py`의 불변 `Settings`에 다음 값을 추가한다.

| 환경 변수 | 기본값 | 검증 |
| --- | ---: | --- |
| `EMBEDDING_DIMENSIONS` | `1536` | 256 이상 정수 |
| `CHUNK_SIZE` | `900` | 기존 청커 계약과 같은 200 이상 정수 |
| `CHUNK_OVERLAP` | `150` | 0 이상이며 `CHUNK_SIZE` 미만 |

정수 변환이나 범위 검증이 실패하면 시작·CLI 단계에서 변수명을 포함한 `ValueError`를 반환한다. 암묵적으로 최솟값으로 보정하지 않는다. 기존 `RAG_TOP_K`, crawler timeout과 같은 기존 설정 동작은 이번 범위에서 바꾸지 않는다.

`AI_PROVIDER=auto`는 기존처럼 API key가 있으면 `openai`, 없으면 `local`로 해석한다. manifest에는 `auto`가 아니라 실제 선택된 `local` 또는 `openai`를 기록한다.

provider 연결 규칙은 다음과 같다.

- `LocalHashProvider` 생성 시 `EMBEDDING_DIMENSIONS`를 전달한다.
- `OpenAIProvider` 생성 시 같은 차원을 전달하고 embeddings API의 `dimensions` 인자로 명시한다.
- 인덱싱 결과의 모든 벡터 길이가 설정값과 같지 않으면 저장 전에 실패한다.
- 채팅 query embedding도 같은 provider 설정을 사용하므로 manifest가 호환되는 동안 query와 document 차원이 일치한다.

청킹 설정의 단일 기준은 환경 변수다. 기존 CLI 호환성을 위해 `--chunk-size`, `--overlap`은 파싱하되, 지정한 값이 Settings와 다르면 exit 2로 종료하고 대응하는 환경 변수를 바꾸도록 안내한다. 이렇게 하면 CLI가 만든 manifest와 런타임 기대값이 즉시 충돌하는 숨은 설정을 만들지 않는다.

## 7. 인덱스 manifest

### 7.1 파일과 책임

신규 `backend/app/index_manifest.py`가 manifest 모델, 파일 hash, fingerprint 계산, 원자적 읽기·쓰기, 호환성 비교를 담당한다. 파일 경로는 `settings.chroma_path / "index-manifest.json"`이다.

이 프로젝트는 한 `CHROMA_PATH`에 한 collection만 둔다는 현재 운영 계약을 유지한다. 여러 collection이 필요해지면 manifest 파일명과 탐색 정책을 별도 schema version에서 확장한다.

manifest 모델은 Pydantic의 frozen model과 `extra="forbid"`를 사용한다. 숫자 범위, 64자리 소문자 hex, UTC timestamp, 허용 provider를 읽는 시점에 검증하며 알 수 없는 필드를 조용히 무시하지 않는다.

### 7.2 JSON schema

manifest는 다음 필드만 가진다.

```json
{
  "schema_version": 1,
  "collection": "se_mentor_posts",
  "provider": "local",
  "embedding_model": "local-hash-embedding-v1",
  "embedding_dimensions": 1536,
  "chunk_size": 900,
  "chunk_overlap": 150,
  "raw_posts_sha256": "64자리 소문자 hex",
  "topic_rules_sha256": "64자리 소문자 hex",
  "indexed_chunks": 46,
  "generated_at": "2026-07-15T12:34:56Z",
  "fingerprint": "64자리 소문자 hex"
}
```

호환성 필드는 `schema_version`, `collection`, `provider`, `embedding_model`, `embedding_dimensions`, `chunk_size`, `chunk_overlap`, `raw_posts_sha256`, `topic_rules_sha256`다. `indexed_chunks`와 `generated_at`은 생성 증거이지만 fingerprint 입력에는 포함하지 않는다.

입력 파일 hash는 파일의 원시 byte 전체를 SHA-256으로 계산한다. 따라서 JSON 내용뿐 아니라 사람이 파일을 다시 포맷한 경우도 명시적 재인덱싱을 요구한다. 이 보수적 정책은 “현재 파일로 만든 인덱스인지”를 모호함 없이 증명한다.

fingerprint는 호환성 필드만 key 오름차순, UTF-8, 공백 없는 canonical JSON으로 직렬화한 뒤 SHA-256으로 계산한다. 읽을 때 저장된 fingerprint를 먼저 재계산해 manifest 자체 변조나 부분 기록을 검출한다.

`schema_version`은 인덱스 생성 코드의 수동 호환성 경계다. chunk text·ID·metadata 구성, 주제 enrich 방식, Chroma 거리 설정처럼 같은 입력과 설정에서도 저장 결과가 달라지는 변경에는 반드시 값을 올리고 전체 reset을 요구한다. 로컬 hash embedding 알고리즘이 바뀌면 `local-hash-embedding-v1` 모델 식별자도 함께 올린다.

manifest에는 다음 정보를 넣지 않는다.

- `OPENAI_API_KEY`와 기타 비밀값
- 게시글 제목·본문·질문·답변
- 로컬 절대 경로와 사용자명
- 실제 embedding vector

### 7.3 원자적 기록

writer는 같은 디렉터리의 임시 파일에 UTF-8 JSON을 쓰고 flush와 close를 끝낸 뒤 `os.replace`로 최종 파일을 교체한다. 디렉터리가 없으면 먼저 생성한다. 임시 파일이나 교체에 실패하면 예외를 전파하고 유효 manifest를 남기지 않는다.

reader는 파일 없음과 JSON/schema/fingerprint 오류를 구분하되 예외를 API까지 노출하지 않고 호환성 결과로 변환한다. 내부 로그 강화는 별도 운영 묶음이므로 이 단계에서는 반환 reason과 테스트 가능한 예외 경계만 둔다.

## 8. 호환성 판정

`IndexCompatibility`는 `compatible: bool`과 아래 reason 중 하나를 반환한다.

| reason | 의미 |
| --- | --- |
| `compatible` | 모든 조건과 실제 청크 수가 일치 |
| `empty_index` | Chroma 청크 수가 0 |
| `index_unavailable` | Chroma collection을 열거나 count를 읽지 못함 |
| `missing_manifest` | 청크는 있지만 manifest가 없음 |
| `invalid_manifest` | JSON, schema 또는 자체 fingerprint가 잘못됨 |
| `settings_mismatch` | collection, provider, model, dimension 또는 청킹 설정이 다름 |
| `content_mismatch` | 현재 원본 게시글·주제 규칙을 읽을 수 없거나 hash가 다름 |
| `chunk_count_mismatch` | Chroma count와 `indexed_chunks`가 다름 |

판정 순서는 다음과 같다.

1. Chroma collection 또는 count 조회가 실패하면 `index_unavailable`이다.
2. Chroma count가 0이면 `empty_index`다.
3. manifest가 없거나 파싱·schema·자체 fingerprint 검증에 실패하면 각각 `missing_manifest` 또는 `invalid_manifest`다.
4. 현재 Settings에서 계산한 collection·provider·모델·차원·청킹 값과 비교한다.
5. 현재 `posts.json`, `topic_rules.json`의 byte hash와 비교한다.
6. 실제 Chroma count와 manifest의 `indexed_chunks`를 비교한다.
7. 모두 같을 때만 `compatible`이다.

비교 결과와 입력 hash는 요청 간 cache하지 않는다. 운영자가 raw posts나 topic rules를 갱신하면 프로세스를 재시작하지 않아도 다음 health·chat 요청에서 `needs_reindex`가 되어야 한다. 현재 데이터 크기가 작으므로 요청당 두 파일의 SHA-256 비용을 안전성보다 우선하지 않는다.

반면 provider, topic catalog, enriched posts, RAG service는 매 요청마다 다시 만들 필요가 없다. `compatible` 결과의 fingerprint를 `get_rag_service(fingerprint)`와 하위 loader의 bounded `lru_cache` key로 사용한다. 입력·설정이 바뀌어 재인덱싱되면 fingerprint도 바뀌어 새 cache 세대가 만들어지고, 같은 fingerprint의 반복 요청만 기존 객체를 재사용한다. 이 규칙으로 vector index는 최신인데 추천 질문·최근 공지는 이전 posts를 보는 cache 불일치를 막는다.

## 9. 인덱싱 lifecycle

`backend/scripts/index.py`는 테스트 가능한 `parse_args(argv: Sequence[str] | None)`와 `main(argv: Sequence[str] | None)` 계약으로 바꾼다. 인덱싱은 다음 순서를 따른다.

1. Settings와 CLI 값을 검증하고 topic rules·posts를 읽는다.
2. 주제 분류와 청킹을 수행한다.
3. 현재 Chroma count를 읽는다.
4. count가 1 이상인데 `--reset`이 없으면 데이터에 손대지 않고 exit 2로 종료하며 `python -m backend.scripts.index --reset`을 안내한다.
5. 모든 chunk embedding을 생성하고 각 vector 차원이 설정과 같은지 검증한다.
6. 파괴적 reset 또는 빈 collection upsert 직전에 기존 manifest를 제거한다.
7. `--reset`이면 collection을 초기화하고 전체 chunk를 upsert한다.
8. 저장 후 Chroma count가 생성한 chunk 수와 같은지 검증한다.
9. 마지막 단계에서만 새 manifest를 원자적으로 기록하고 성공 메시지에 fingerprint 앞 12자리와 청크 수를 출력한다.

embedding 생성 전에 reset하지 않으므로 외부 provider 실패 시 기존 Chroma 데이터는 보존된다. 반면 reset 이후 upsert·count·manifest 기록 중 하나라도 실패하면 manifest가 없는 상태가 되어 런타임이 불완전한 인덱스를 사용하지 않는다.

증분 upsert는 이번 계약에서 허용하지 않는다. 입력과 규칙이 바뀌면 항상 전체 `--reset`으로 다시 생성한다. 이는 삭제된 게시글의 orphan chunk와 서로 다른 청킹 설정의 혼합을 막는다.

빈 posts로 0개 chunk가 생성되면 성공 manifest를 만들지 않고 exit 2로 종료한다.

## 10. API 동작

### 10.1 health 상태

`HealthResponse.status`에 `needs_reindex`, `unavailable`을 추가하고 다음 필드를 더한다.

```python
index_compatible: bool
index_reason: Literal[
    "compatible",
    "empty_index",
    "index_unavailable",
    "missing_manifest",
    "invalid_manifest",
    "settings_mismatch",
    "content_mismatch",
    "chunk_count_mismatch",
]
```

상태 우선순위는 다음과 같다.

| 조건 | status | index_compatible |
| --- | --- | --- |
| `AI_PROVIDER=openai`이며 key 없음 | `needs_configuration` | 실제 판정값 유지 |
| provider 설정 가능, Chroma 조회 실패 | `unavailable` | `false` |
| provider 설정 가능, Chroma count 0 | `needs_index` | `false` |
| provider 설정 가능, count > 0, 호환성 오류 | `needs_reindex` | `false` |
| provider 설정 가능, 완전 호환 | `ready` | `true` |

`openai_configured`, provider·model 이름, `indexed_chunks`의 기존 필드는 유지한다. `openai_configured`는 이름대로 API key 존재 여부만 뜻하며 local provider의 준비 상태는 `status`로 표현한다. health 응답은 hash, fingerprint, 경로, 비밀값을 노출하지 않는다.

### 10.2 chat 차단

`/api/chat`은 RAG service와 provider를 만들기 전에 같은 호환성 판정을 수행한다.

- 명시적 OpenAI 모드에 key가 없으면 HTTP 503과 설정 안내를 반환한다.
- `index_unavailable`이면 HTTP 503과 잠시 후 상태 확인 안내를 반환한다.
- `empty_index`면 기존 HTTP 409 의미를 유지하고 최초 인덱싱 명령을 안내한다.
- 나머지 비호환 reason은 HTTP 409와 `python -m backend.scripts.index --reset` 안내를 반환한다.
- `compatible`일 때만 `get_rag_service(compatibility.fingerprint).ask()`를 호출한다.
- 기존 OpenAI `APIError`의 HTTP 502 처리와 `ChatResponse` schema는 유지한다.

오류 문구는 사용자가 해결할 명령을 포함하되 내부 hash나 절대 경로를 포함하지 않는다. 프론트엔드는 현재 `detail` 문자열을 그대로 표시하므로 별도 frontend 변경 없이 안내가 전달된다.

## 11. 커버리지와 테스트

### 11.1 측정 설정

`backend/pyproject.toml`에 다음 원칙을 설정한다.

- source: `backend.app`, `backend.scripts`
- omit: `backend/app/crawling/seboard.py`, package `__init__.py`
- line coverage `fail_under = 85`
- `show_missing = true`
- 테스트 파일과 생성 파일은 source에 포함하지 않음
- 커버리지 무시 pragma나 광범위한 디렉터리 제외를 추가하지 않음

SE 게시판 모듈 제외 사유를 설정 주석과 상태 문서에 명시한다. `backend/app/crawling/kumoh.py`, CLI, API endpoint, provider factory 등 나머지 제품 코드는 모두 gate 대상이다.

로컬·CI 표준 명령은 저장소 root에서 다음 형태로 통일한다.

```bash
python -m pytest -c backend/pyproject.toml backend/tests \
  --cov=backend.app --cov=backend.scripts \
  --cov-config=backend/pyproject.toml --cov-report=term-missing
```

### 11.2 TDD 테스트 묶음

구현은 각 동작마다 RED를 확인한 뒤 최소 구현과 전체 회귀 검증을 수행한다.

| 테스트 파일 | 핵심 계약 |
| --- | --- |
| `backend/tests/test_index_manifest.py` | canonical fingerprint 결정성, byte hash, round-trip, 원자적 기록 실패, 누락·손상·각 mismatch reason |
| `backend/tests/test_config.py` | 새 기본값, 환경 변수 override, dimension·chunk 경계 오류 |
| `backend/tests/test_provider_factory.py` | auto/local/openai 선택, key 누락, 모델·차원 전달 |
| `backend/tests/test_openai_service.py` | fake client로 embeddings `dimensions` 전달과 응답 변환, 외부 호출 없음 |
| `backend/tests/test_index_script.py` | argv 파싱, reset 강제, 차원 불일치, 실패 시 manifest 부재, 성공 시 manifest와 count 일치 |
| `backend/tests/test_main.py` | health 다섯 상태, 각 reason, chat 409/503, 비호환 시 provider 미호출, fingerprint 변경 시 cache 교체, 호환 시 정상 위임 |
| 기존 vector store 테스트 | count·reset·upsert 경계가 script 계약을 지지하는지 확인 |

FastAPI endpoint는 `TestClient`와 dependency/cache monkeypatch를 사용한다. OpenAI와 크롤러는 fake로 대체해 네트워크와 유료 API에 의존하지 않는다.

## 12. GitHub Actions CI

신규 `.github/workflows/quality.yml`은 `pull_request`와 `main` push에서 실행하며 권한은 `contents: read`만 사용한다. backend와 frontend를 독립 job으로 실행해 어느 영역이 실패했는지 바로 알 수 있게 한다.

### 12.1 backend job

- Ubuntu 최신 runner
- Python 3.13과 pip cache
- `backend/requirements-dev.txt` 설치
- 제품 코드 coverage 85% gate를 포함한 pytest
- `ruff check backend`

### 12.2 frontend job

- Ubuntu 최신 runner
- Node.js 22와 npm cache
- `npm --prefix frontend ci`
- `npm --prefix frontend test`
- `npm --prefix frontend exec tsc -- --noEmit`
- `npm --prefix frontend run lint`
- `npm --prefix frontend run build`

CI는 API key를 설정하지 않고 `AI_PROVIDER=local` 기본 경로만 사용한다. 라이브 크롤링, Chroma 운영 데이터, 평가 보고서 업로드를 수행하지 않는다. frontend build는 현재 기본 API URL 처리로 외부 서버 없이 완료되어야 한다.

## 13. 문서와 유지보수

구현과 함께 다음 문서를 갱신한다.

| 파일 | 반영 내용 |
| --- | --- |
| `.env.example` | dimension·chunk 환경 변수와 변경 시 재인덱싱 필요 주석 |
| `README.md` | 최초 인덱싱, 설정·데이터 변경 후 reset, health 상태, 표준 검증 명령 |
| `docs/rag/operations-evaluation.md` | manifest 확인·재구축·오류 reason별 대응 |
| `docs/PROJECT_STATUS.md` | 완료 범위, 측정된 coverage, CI 상태, 분리된 후속 묶음 |
| handoff 문서 | 구현 커밋, 검증 결과, 남은 외부 확인과 다음 진입점 |
| `.gitignore` | `.coverage`, `coverage.xml`, `htmlcov/`과 기존 Chroma 산출물 제외 확인 |

문서의 모든 명령은 비밀값 없이 복사 실행할 수 있어야 한다. Windows PowerShell과 CI용 bash에서 경로 차이가 없는 `python -m ...`, `npm --prefix ...` 형태를 우선한다.

## 14. 보안과 실패 처리

- manifest는 공개 가능한 구성 이름과 hash만 포함하며 원문과 secret은 저장하지 않는다.
- hash는 변경 검출용이며 원문 기밀성을 보장하는 수단으로 설명하지 않는다. 현재 입력은 공개 공지 데이터다.
- 손상되거나 알 수 없는 schema version은 추측해서 복구하지 않고 `invalid_manifest`로 차단한다.
- 이전 schema를 자동 승인하지 않는다. 새 version 도입 시 migration 또는 전체 reset을 별도 명시한다.
- Chroma count 조회가 실패하면 ready나 빈 인덱스로 간주하지 않는다. health는 `unavailable`, chat은 503으로 응답한다.
- API 예외에는 사용자명, 로컬 경로, provider 원문 오류, key 존재 형태 외의 민감한 설정을 포함하지 않는다.
- CI 로그에 `.env` 내용이나 manifest 원본을 출력하지 않는다.

## 15. 전환과 되돌리기

기존 인덱스에는 manifest가 없으므로 코드 배포 직후 health는 `needs_reindex`, chat은 409가 된다. 배포 전에 또는 직후 아래 명령으로 한 번 전체 재구축해야 한다.

```bash
python -m backend.scripts.index --reset
```

재구축 성공 후 manifest와 Chroma count가 일치할 때만 ready가 된다. 생성된 `index-manifest.json`은 `chroma_db`와 함께 Git에서 제외하며, 운영 백업 시에는 같은 단위로 보존한다.

문제가 생겼을 때 코드만 되돌리면 기존 런타임은 manifest를 무시하고 Chroma 데이터를 읽을 수 있다. 데이터까지 되돌릴 필요가 있는 경우에는 배포 전 백업한 Chroma 디렉터리를 복원한다. 자동 backup 명령과 복원 훈련은 운영 강화 묶음에서 구현한다.

## 16. 완료 조건

- 기존 backend 94개와 frontend 9개 테스트를 포함한 전체 회귀가 통과한다.
- 신규 manifest·config·provider·index CLI·endpoint 테스트가 통과한다.
- SE 게시판 모듈과 package initializer만 제외한 backend 제품 코드 line coverage가 85% 이상이며 낮으면 명령이 비정상 종료한다.
- `ruff check backend`, frontend TypeScript·ESLint·Vitest·production build가 통과한다.
- 저장소 조회 실패, 빈 인덱스, manifest 누락·손상, 설정 변경, 입력 변경, count 불일치가 각각 기대 reason으로 재현된다.
- 비호환 상태에서는 provider가 호출되지 않고 chat이 409 또는 설정 누락 시 503을 반환한다.
- 로컬 provider로 `python -m backend.scripts.index --reset`을 실행하면 유효 manifest가 생성되고 health가 `ready`가 된다.
- 기존 30문항 평가가 기대값 변경 없이 30/30을 유지한다.
- 데이터 감사 CLI는 현재 알려진 경고 3건과 exit 1을 동일하게 유지한다.
- GitHub Actions workflow 문법과 두 job의 모든 명령이 로컬 대응 명령으로 검증된다.
- `git diff --check`가 통과하고 secret·게시글 본문·절대 경로가 새 manifest·문서·테스트 fixture에 포함되지 않는다.

## 17. 후속 구현 묶음

이 설계를 완료한 뒤 범위가 섞이지 않도록 다음 순서로 별도 설계·계획을 만든다.

1. 프론트엔드 Playwright E2E, API 오류 화면 회귀, axe 기반 접근성 검사
2. rate limit, 구조화 로그, request ID, 오류 관측성
3. Docker healthcheck/readiness, Chroma·manifest 백업 및 복원 검증
4. 의존성 취약점 분류와 안전한 버전 갱신

SE 게시판 관련 수집·권한·fixture 작업은 사용자 요청에 따라 이 목록에서도 제외 상태를 유지한다.
