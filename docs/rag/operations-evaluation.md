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
| `RAG_TOP_K` | `5` | 초기 벡터 검색 수 |
| `RAG_MIN_SCORE` | `0.20` | 절대 임계값 |
| `CRAWLER_DELAY_SECONDS` | `1.0` | 사이트 요청 간격 |
| `SEBOARD_API_URL` | 빈 값 | 확인된 공개 API 주소 |

## 운영 절차

일반 작업 순서:

```powershell
# 1. 데이터 수집; SE 실패를 허용하려면 --allow-partial
backend/.venv/Scripts/python -m backend.scripts.crawl --kumoh-limit 50 --seboard-limit 50 --allow-partial

# 2. provider 또는 데이터 변경 후 전체 인덱싱
backend/.venv/Scripts/python -m backend.scripts.index --reset

# 3. 서버 재기동
docker compose up -d --build

# 4. 상태 확인
Invoke-RestMethod http://localhost:8000/api/health
```

`/api/health`에서 provider, 모델명, 인덱싱 청크 수를 확인한다. 인덱스가 비어 있으면 채팅 API는 `409`, OpenAI 호출 실패는 `502`를 반환한다.

## 테스트와 평가

현재 단위 테스트는 청킹, 학과 게시판 파싱, 저장 중복 제거, Chroma 최근접 검색, RAG 임계값, 로컬 임베딩 결정성 및 출처 표기를 검사한다.

```powershell
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m pytest backend/tests
```

검색 품질 변경 시 `data/evaluation/questions.json`을 확장해 다음을 기록한다.

- 기대 문서가 Top-1/Top-3/Top-5에 포함되는지
- 범위 밖 질문이 `grounded=false`인지
- 답변의 날짜·대상·신청 경로가 원문과 일치하는지
- 표시한 `[자료 N]`과 source 카드가 일치하는지
- provider별 지연시간, API 비용, 실패율

임계값은 소수의 성공 예시가 아니라 최소 30개 이상의 대표 질문으로 결정한다.
