# RAG Operations And Evaluation

이 문서는 지원 설정, 운영 절차, health/readiness, 테스트·평가·데이터 감사 기준을 설명한다. 현재 건수·준비도·위험은 [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)를 단일 상태 문서로 확인한다.

## 주요 환경변수

`.env.example`은 비밀값이 없는 검증된 안전한 local sample이다. 애플리케이션 `config.py`는 환경변수가 없을 때 `AI_PROVIDER=auto`를 fallback으로 사용하며, `auto`는 key가 있으면 OpenAI, 없으면 local을 선택한다. 따라서 sample의 `AI_PROVIDER=local`과 application fallback `auto`를 같은 의미의 기본값으로 읽지 않는다.

| 환경변수 | `.env.example` sample | application fallback | 역할 |
| --- | --- | --- | --- |
| `AI_PROVIDER` | `local` | `auto` | `local`, `openai`, `auto` provider 선택 |
| `OPENAI_API_KEY` | 빈 값 | 없음 | OpenAI Embeddings/Responses 인증 |
| `OPENAI_CHAT_MODEL` | `gpt-5.6-luna` | `gpt-5.6-luna` | OpenAI 답변 모델; embedding signature와 무관 |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | `text-embedding-3-small` | OpenAI 임베딩 모델 |
| `EMBEDDING_DIMENSIONS` | `1536` | `1536` | 임베딩 벡터 차원 |
| `CHUNK_SIZE` | `900` | `900` | 문자 기준 청크 최대 크기 |
| `CHUNK_OVERLAP` | `150` | `150` | 인접 청크 중복 크기 |
| `CHROMA_PATH` | `./chroma_db` | `./chroma_db` | Chroma와 manifest 저장 위치 |
| `CHROMA_COLLECTION` | `se_mentor_posts` | `se_mentor_posts` | Chroma collection 이름 |
| `RAW_POSTS_PATH` | `./data/raw/posts.json` | `./data/raw/posts.json` | 원본 JSON snapshot |
| `TOPIC_RULES_PATH` | `./data/topic_rules.json` | `./data/topic_rules.json` | topic·keyword·evidence 규칙 |
| `RAG_TOP_K` | `5` | `5` | 초기 vector 검색 수 |
| `RAG_MIN_SCORE` | `0.10` | `0.10` | 최종 검색 절대 threshold |
| `CRAWLER_DELAY_SECONDS` | `1.0` | `1.0` | 요청 간격 |
| `CRAWLER_TIMEOUT_SECONDS` | `20.0` | `20.0` | crawler 요청 timeout |
| `SEBOARD_API_URL` | 빈 값 | 없음 | 승인된 SE JSON API 주소 |
| `SEBOARD_HEADLESS` | `true` | `true` | 허용된 Selenium 경로의 headless 실행 |
| `CORS_ORIGINS` | `http://localhost:3000` | `http://localhost:3000` | API 허용 frontend origin 목록 |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Compose build arg 기본값 | frontend가 호출할 API 주소 |
| `BACKEND_PORT` | `8000` | Compose mapping 기본값 | host의 backend port |
| `FRONTEND_PORT` | `3000` | Compose mapping 기본값 | host의 frontend port |

`NEXT_PUBLIC_API_URL`은 Next.js frontend 이미지 빌드 시 삽입되는 build-time 값이다. 값을 바꾸면 frontend 이미지를 반드시 rebuild해야 하며, 실행 중 컨테이너 환경변수만 바꾸어 이미 빌드된 UI의 API 주소를 변경할 수 없다.

`CHROMA_PATH/index-manifest.json`은 provider, embedding model/dimension, chunking, collection, raw/topic SHA-256, chunk count와 signature fingerprint를 기록한다. provider·모델·차원·collection·chunking·원본·topic rules가 바뀌면 `index --reset`을 실행하고, `OPENAI_CHAT_MODEL`만 바뀌면 재인덱싱하지 않는다.

## 운영 절차

허용된 학과 source만 수집하는 기본 명령은 다음과 같다. SE 게시판은 권한과 승인된 API가 확인되기 전까지 `--seboard-limit 0`을 유지한다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-limit 50 --seboard-limit 0
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
```

원본 변경, topic rule 변경, provider/embedding 변경, collection·chunking 변경 후에는 index → evaluation → audit 순서로 재검증한다. 인덱싱은 임베딩 수·차원과 입력 signature를 먼저 확인하고, 성공한 Chroma 저장 뒤 manifest를 기록한다. manifest 누락·손상, 설정·content hash·실제 chunk count 불일치는 전체 재인덱싱으로 복구한다.

`--allow-partial` 수집 결과는 `data/raw/candidates/posts-partial.json`에만 저장한다. source·canonical URL·게시일을 사람 검토로 확인해 운영 원본에 반영한 뒤 다시 인덱싱한다.

## Liveness와 readiness

| endpoint/status | 의미 | 조치 |
| --- | --- | --- |
| `/api/live` → `alive` | FastAPI process가 요청을 처리할 수 있음; Chroma readiness는 검사하지 않음 | process/container liveness 확인 |
| `/api/health` → `ready` / `compatible` | 현재 설정·데이터·manifest·chunk count가 일치해 RAG 사용 가능 | 채팅 제공 |
| `/api/health` → `needs_configuration` | 선택 provider에 필요한 설정이 없음 | OpenAI key 또는 provider 설정 복구 |
| `/api/health` → `needs_index` / `empty_index` | collection이 비어 있음 | 전체 인덱싱 실행 |
| `/api/health` → `needs_reindex` | `missing_manifest`, `invalid_manifest`, `settings_mismatch`, `content_mismatch`, `chunk_count_mismatch` | 전체 재인덱싱 실행 |
| `/api/health` → `unavailable` / `index_unavailable` | 저장소를 열 수 없음 | 경로·권한·Chroma 상태 복구 |

호환되지 않는 index는 `/api/chat`에서 provider 호출 전에 차단된다. `needs_index`·`needs_reindex`는 `409`, provider 설정·저장소 문제는 `503`, OpenAI 호출 실패는 `502`다.

## Compose 검증

Docker Desktop 또는 Docker Engine과 Compose plugin이 필요하다. 검증 명령은 다음과 같다.

```powershell
docker compose config
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/api/live
Invoke-RestMethod http://localhost:8000/api/health
```

Compose backend healthcheck는 `/api/live`를 사용하고 frontend는 root HTTP 응답을 확인한다. frontend는 backend healthcheck가 healthy가 된 뒤 시작하도록 설정되어 있다. 이 healthcheck와 `depends_on`은 startup ordering과 상태 보고를 위한 것이며 unhealthy 컨테이너를 자동으로 고치는 autoheal을 보장하지 않는다. 현재 작업 호스트에서 Docker runtime을 사용할 수 없다면 위 명령의 runtime 결과를 완료 근거로 주장하지 않는다.

## 테스트와 데이터 감사

```powershell
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
```

데이터 감사는 명시 옵션이 없으면 설정된 `RAW_POSTS_PATH`와 `TOPIC_RULES_PATH`를 읽고 `data/audit/reports/latest.json`, `latest.md`에 보고서를 쓴다. 기본 required source는 `kumoh`와 `seboard`이며 `--posts`, `--topic-rules`, `--output-dir`, `--stale-after-days`, `--required-source`로 조정할 수 있다.

| exit | 의미 | 조치 |
| ---: | --- | --- |
| `0` | 품질 경고 없음 | 다음 단계 진행 |
| `1` | 게시글 source 누락, stale topic, empty topic 등 품질 경고 존재 | 경고를 공식 원문과 대조하고 승인·해결 여부 기록 |
| `2` | 입력·설정·출력 오류 | 경로·JSON·topic rules·권한을 복구한 뒤 재실행 |

감사 보고서는 본문과 비밀값을 기록하지 않으며 생성물은 Git에 포함하지 않는다.

## 평가

provider-matched 평가의 정확한 순서는 다음과 같다.

```powershell
$env:AI_PROVIDER="local"
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured
```

`--provider configured`는 현재 설정에서 선택된 provider를 사용한다. `AI_PROVIDER=auto`라면 key 유무로 실제 selected provider가 정해진다. `--provider local`은 local 설정으로 만든 local index만 평가할 때 사용한다. 평가 CLI는 첫 질문을 실행하거나 provider를 생성하기 전에 strict manifest를 검사하며, provider·model·dimension·collection·chunking·content 또는 chunk count가 일치하지 않으면 exit 2로 종료한다.

평가 exit 의미는 다음과 같다.

- `0`: 모든 품질 assertion 통과
- `1`: 평가 실행은 끝났지만 품질 assertion 실패
- `2`: 질문 파일·설정·index manifest 등 입력/실행 오류로 평가를 완료하지 못함

### Threshold calibration

`RAG_MIN_SCORE=0.10`은 local hash embedding의 과거 46건 historical tuning snapshot에서만 조정된 값이며 OpenAI embedding에 검증되지 않았다. 이 숫자를 OpenAI의 기본 threshold나 현재 status로 해석하지 않는다.

provider 또는 데이터가 바뀌면 최소 30문항에서 positive/negative retrieval score distribution을 따로 수집한다. threshold를 정할 때 false-positive 최고 점수와 true-positive 최저 점수, 두 값 사이의 margin을 기록하고 그 근거로 선택한다. 평가 pass count만으로 calibration이 끝났다고 하지 않는다. OpenAI로 전환할 때는 provider-matched reindex/evaluation과 별도 threshold 기록을 남긴다.

평가 질문은 기대 topic, Top-K 문서 포함 여부, latest-only, grounded 거절, source metadata와 날짜·대상·신청 경로 일치 여부를 확인해야 한다. 세부 수치와 현재 snapshot은 [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) 및 생성 report를 참조한다.
