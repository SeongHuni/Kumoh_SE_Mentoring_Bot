# RAG Operations And Evaluation

이 문서는 구성값, 운영 절차, 테스트와 평가 기준을 설명한다.

## 구성값

| 환경변수 | 기본값 | 역할 |
| --- | --- | --- |
| `AI_PROVIDER` | `auto` | provider 선택 |
| `OPENAI_CHAT_MODEL` | `gpt-5.6-luna` | OpenAI 답변 모델 |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI 임베딩 모델 |
| `CHROMA_PATH` | `./chroma_db` | 벡터 저장 위치 |
| `CHROMA_COLLECTION` | `se_mentor_posts` | 컬렉션 이름 |
| `RAW_POSTS_PATH` | `./data/raw/posts.json` | 원본 JSON |
| `TOPIC_RULES_PATH` | `./data/topic_rules.json` | 주제·키워드·추천 질문 규칙 |
| `RAG_TOP_K` | `5` | 초기 벡터 검색 수 |
| `RAG_MIN_SCORE` | `0.09` | 절대 임계값(로컬 해시 임베딩 보정값) |
| `CRAWLER_DELAY_SECONDS` | `1.0` | 사이트 요청 간격 |
| `SEBOARD_API_URL` | 빈 값 | 확인된 공개 API 주소 |

## 운영 절차

일반 작업 순서:

```powershell
# 1. 데이터 수집; SE 실패를 허용한 점검용 후보는 --allow-partial
backend/.venv/Scripts/python -m backend.scripts.crawl --kumoh-limit 50 --seboard-limit 50 --allow-partial

# 2. provider 또는 데이터 변경 후 전체 인덱싱
backend/.venv/Scripts/python -m backend.scripts.index --reset

# 3. 서버 재기동
docker compose up -d --build

# 4. 상태 확인
Invoke-RestMethod http://localhost:8000/api/health
```

`/api/health`에서 provider, 모델명, 인덱싱 청크 수를 확인한다. 인덱스가 비어 있으면 채팅 API는 `409`, OpenAI 호출 실패는 `502`를 반환한다.

`--allow-partial` 실행에서 일부 소스가 실패하면 결과는 `data/raw/candidates/posts-partial.json`에 저장된다. 이 후보 파일은 Git에서 제외되며, 운영 원본 `data/raw/posts.json`은 변경하지 않는다. 두 소스 성공 또는 사람이 수행한 원문 URL·게시일 검증 없이 후보를 운영 원본으로 자동 승격하지 않는다.

`data/topic_rules.json`은 주제 관리의 단일 유지보수 지점이다. 주제 키·표시명·키워드·추천 질문·근거 marker·동의어 또는 원본 게시글을 변경하면 반드시 `--reset`으로 전체 재인덱싱한다. 최신성은 유효한 `published_at`을 우선하고, 누락되거나 파싱할 수 없을 때 `crawled_at`을 사용한다. 온라인 검색은 `is_latest_topic=true`를 적용해 같은 주제의 이전 게시글을 제외한다.

검색된 최신 문서라도 질문과 문서의 연도·학기가 충돌하면 근거로 인정하지 않는다. 제목 marker나 동의어는 질문 표현과 연결될 때만 유효하며, 일반적인 “최근 학과 공지” 질문은 주제 점수보다 게시일이 가장 최신인 문서를 우선한다. 이 근거 게이트를 통과하지 못하면 provider 답변을 호출하지 않고 `grounded=false`를 반환한다.

규칙 변경 후에는 `/api/chat` 응답에서 다음을 함께 점검한다.

- `sources`가 분류된 주제의 최신 게시글만 가리키는지
- `suggested_questions`가 해당 주제 또는 `general` 규칙과 일치하는지
- `recent_notices`에 주제 라벨·게시일·canonical URL이 있는지
- 근거가 없을 때 `grounded=false`이고 추측성 답변을 만들지 않는지

## 테스트와 평가

현재 단위 테스트는 청킹, 학과 게시판 파싱, 저장 중복 제거, Chroma 최근접 검색, RAG 임계값, 로컬 임베딩 결정성 및 출처 표기를 검사한다.

```powershell
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m pytest backend/tests
```

### 자동 평가

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
backend/.venv/Scripts/python -m backend.scripts.evaluate
```

- 기본 provider는 `local`이다.
- `--provider configured`는 현재 `.env` provider를 사용한다.
- `latest.json`, `latest.md`는 `data/evaluation/reports/`에 생성된다.
- exit 0은 전체 통과, exit 1은 품질 assertion 실패, exit 2는 실행 오류다.
- 데이터 재수집 후 30개 baseline 기대값을 공식 원문과 재검토한다.

| 인자 | 기본값 | 용도 |
| --- | --- | --- |
| `--questions` | `data/evaluation/questions.json` | 평가 입력 파일 |
| `--output-dir` | `data/evaluation/reports` | JSON·Markdown 보고서 위치 |
| `--provider` | `local` | `local` 또는 현재 환경의 `configured` provider 선택 |
| `--minimum-cases` | `30` | 전체 입력 파일의 최소 케이스 수 |
| `--limit` | 없음 | schema·최소 수 검증 후 첫 N개만 smoke 실행 |

검색 품질 변경 시 `data/evaluation/questions.json`을 확장해 다음을 기록한다.

- 기대 문서가 Top-1/Top-3/Top-5에 포함되는지
- 범위 밖 질문이 `grounded=false`인지
- `expected_topic_key`와 실제 주제 분류가 일치하는지
- `expected_latest_only=true` 질문의 모든 출처가 주제별 최신 게시글인지
- 답변의 날짜·대상·신청 경로가 원문과 일치하는지
- 표시한 `[자료 N]`과 source 카드가 일치하는지
- provider별 지연시간, API 비용, 실패율

임계값은 소수의 성공 예시가 아니라 최소 30개 이상의 대표 질문으로 결정한다.

현재 로컬 검증 스냅샷(2026-07-15)은 게시글 46건·청크 79개, 평가 30/30(exit 0)이다. 세부 지표는 topic 30/30, grounded 30/30, latest-only 30/30, source-title 11/11이다. 이 수치는 현재 저장 데이터에 대한 회귀 기준이며 공식 사이트의 실제 최신성을 보증하지 않는다.

## 데이터 품질 감사

```powershell
backend/.venv/Scripts/python -m backend.scripts.audit_data
```

감사 보고서는 `data/audit/reports/latest.json`, `latest.md`에 원자적으로 저장되고 Git에서 제외된다. 게시글 본문, 비밀값, 로컬 절대 경로는 보고서에 포함하지 않는다.

| exit | 의미 | 운영 조치 |
| ---: | --- | --- |
| 0 | 품질 경고 없음 | 재인덱싱·평가 진행 |
| 1 | 품질 경고 있음 | 경고 코드를 검토하고 공식 원문과 대조 |
| 2 | 입력·설정 오류 | 원본 JSON·주제 규칙·출력 권한 복구 후 재실행 |

현재 데이터에서는 `missing_source=seboard`, `stale_topic=course_openings`, `empty_topic=graduation`이 각 1건이다. 따라서 감사는 exit 1이며 의도된 운영 경고다. 특히 `course_openings`의 현재 최신 게시일 2025-08-07과 SE 소스 부재는 공식 사이트 live crawl 및 수동 URL·날짜 대조 전까지 해결 완료로 표시하지 않는다.
