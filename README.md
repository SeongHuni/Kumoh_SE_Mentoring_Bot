# 금오공대 소프트웨어전공 RAG 챗봇

학과 공지·강의평을 근거로 답하는 RAG 챗봇입니다. 청킹 전략 실험부터 배포까지 한 저장소에 있습니다.

```
프론트엔드 (Next.js, 3000)
      │  POST /api/chat  (컨테이너 내부에서는 상대경로 프록시)
      ▼
   백엔드 (FastAPI · Python, 8787)
      │
      ├─► Chroma (8000)      1,549 청크 · text-embedding-3-small
      └─► OpenAI              gpt-4o-mini (검색 계획기 · 답변 생성 동일 모델)
```

세 컨테이너(chroma / backend / frontend)를 Docker Compose로 함께 띄웁니다.

---

## 빠른 실행 (Docker — 권장)

```bash
docker compose up -d --build
```

**http://localhost:3000**

처음 클론한 팀원은 `chroma-data/`(벡터 DB, git에 없음)를 따로 받아야 합니다.
전체 절차·문제 해결은 `docs/팀원_실행하기.md`를 참고하세요.

```bash
curl http://localhost:8787/api/health   # indexed_chunks 가 1549 여야 정상
```

### 로컬 실행 (Docker 없이, 개발용)

```powershell
.\start-web.ps1
```

Chroma → 백엔드 → 프론트 순서로 띄우고 각 단계가 응답할 때까지 기다린 뒤 브라우저를 엽니다.

| 명령 | 하는 일 | 포트 |
| --- | --- | --- |
| `npm run chroma:py` | Chroma 서버 | 8000 |
| `npm run api` | 백엔드 (FastAPI) | 8787 |
| `npm run web` | 프론트엔드 개발 서버 | 3000 |

전부 종료: `Get-Process node,chroma,python | Stop-Process`

OpenAI 키는 프로젝트 루트 `.env`의 `OPENAI_API_KEY=sk-...`로 제공합니다 (`.gitignore`에 있어 커밋되지 않습니다).

---

## CLI로 쓰기

웹 없이 터미널에서 바로 대화할 수 있습니다. 이 CLI들은 **백엔드(backend/app)와 별개로 구현된 Node 버전**입니다 — 청킹 실험·평가를 스크립트만으로 빠르게 돌리려고 만든 것이라, 실제 서비스(FastAPI)와 로직이 100% 동일하지는 않습니다.

```powershell
.\start-chat.ps1              # Chroma 자동 기동 + 대화 시작
npm run chat                  # 대화형
npm run demo                  # 시연용 자동 실행
node scripts/chat.js "질문1" "질문2"   # 여러 질문을 한 세션으로
```

| 명령 | 설명 |
| --- | --- |
| `npm run chat` | 기본 (가중치 적용) |
| `npm run chat:k8` | top-k 8 |
| `npm run chat:noboost` | **대조군** — 중요도 가중치 미적용 |
| `npm run ask -- "질문"` | 단일 질문 (대화 맥락 없음) |

대화 중 명령: `/reset` `/debug` `/history` `/help` `/exit`

---

## 동작 방식 (`backend/app/rag.py`)

```
질문 + 대화 이력
      │
      ▼
 검색 계획기 (gpt-4o-mini, JSON 스키마 강제)   대화 이력은 여기서만 읽는다
   ├─ 후속 질문을 독립형 질의(standalone_query)로 재작성
   ├─ 출처·분류·시점 판단
   ├─ 대상 불명확 → 되묻기 (검색·생성 호출 안 함) — 아래 참고
   └─ 범위 밖 → 거절 (최후 수단으로만 사용)
      │
      ▼
 임베딩 (text-embedding-3-small, 재작성된 질의를 임베딩)
      │
      ▼
 Chroma 벡터 검색 (fetch_k=100 후보, 코사인 유사도)
      │
      ▼
 후처리 (전부 규칙 기반 산술 연산 — LLM 미사용)
   ├─ 이벤트 가중치 + 시간 감쇠 (decay_per_year 0.012, max_decay 0.04)
   ├─ 최신 우선 (유사도 0.05 이내면 최신순)
   └─ 다양성 필터 → top_k=5 (문서당 최대 2, 주제당 최대 2)
      │
      ▼
 답변 생성 (gpt-4o-mini, temperature 0)   현재 질문 + 검색 자료만 받는다
```

**핵심 분리** — 검색 계획기만 대화 이력을 읽습니다. 답변 생성기는 현재 질문과 검색 자료만 받으므로, 이전 답변에 오류가 있어도 다음 답변의 사실로 전파되지 않습니다.

**되묻기(clarify)는 두 경우로만 좁혔습니다** — (1) 한 질문에 여러 주제가 섞여 무엇을 찾을지 정할 수 없을 때, (2) 지시대명사가 가리키는 대상이 대화에 없을 때. "이름 없이 주제어만 있음"은 예전엔 되묻는 조건이었지만, 13건 비교(되묻기 10/13 양호 vs 그냥 검색 11/13 양호)에서 이득이 없어 제거했습니다.

### 답변 품질을 위해 적용한 것

| 단계 | 전략 |
| --- | --- |
| 청킹 | fixed-size 500 tokens, overlap 0 · 모든 청크에 `제목/출처/분류/작성일` 헤더 부착 |
| 검색 | 출처 분리(공지 ↔ 강의평) · 분류·연도·기간 필터 · 필터 충돌 자동 차단 |
| 순위 | 이벤트 가중치 · 시간 감쇠 · 주제 다양성 · 최신 우선 (전부 산술 재정렬, ML 리랭커 아님) |
| 질의 | 후속 질문 재작성 · 되묻기(두 경우로 한정) · 범위 밖 거절(최후 수단) · 오늘 날짜 주입 |
| 생성 | 근거 강제 · 출처 번호 표기 · 프롬프트 인젝션 방어 · temperature 0 |

### 중요도 가중치

임베딩이 알 수 없는 "학과에서 중요한 정보"는 `data/importance.json`에 사람이 지정합니다.

```json
{
  "recency": { "decay_per_year": 0.012, "max_decay": 0.04 },
  "rules": [
    { "name": "이정연 장학금", "match": { "title": "이정연" }, "boost": 0.05 }
  ]
}
```

최종 점수 = `유사도 + 이벤트 가중치 − 경과연수 × 0.012`

유사도가 0.45~0.65 구간에 몰려 있어 `+0.05`면 몇 계단, `+0.1`이면 과하게 올라갑니다. 컨테이너 재시작만 하면 반영됩니다 (`docker-compose.yml`에서 이 파일을 읽기 전용으로 마운트).

---

## API

`POST /api/chat`

```json
{ "question": "이정연 장학금 신청 어떻게 해", "session_id": "(선택)", "confirmed_intent_key": "(선택)" }
```

```json
{
  "response_type": "answer",
  "answer": "...[1]...",
  "sources": [
    { "index": 1, "title": "...", "url": "https://...", "source": "se게시판",
      "published_at": "2026-03-26", "score": 0.61, "kind": "notice" }
  ],
  "grounded": true,
  "interpreted_intent": null,
  "clarification_options": [],
  "suggested_questions": ["..."],
  "recent_notices": []
}
```

- `response_type`: `answer`(근거로 답함) · `clarification`(되물음, 검색·생성 호출 안 함) · `no_answer`(근거 없음/범위 밖)
- `sources[].url`은 걸러지거나 재정렬되지 않고 검색 순서 그대로입니다. 에브리타임 강의평은 원문 링크가 없어 `url: null`이지만 근거로는 사용됩니다 (`kind: "review"`, `course`/`professor` 필드로 표시).

`GET /api/health`, API 문서는 컨테이너 실행 후 http://localhost:8787/docs 에서 볼 수 있습니다.

---

## 구조

```
├── frontend/            Next.js 15 + React 19 UI
├── backend/             FastAPI — 실제 서비스가 도는 곳
│   └── app/
│       ├── rag.py               파이프라인 오케스트레이션
│       ├── query_planner.py     질의 재작성 · 되묻기/거절 판정
│       ├── ranking.py           중요도 가중치 · 시간 감쇠 · 다양성 (규칙 기반)
│       ├── vector_store.py      Chroma 검색
│       ├── openai_service.py    OpenAI 호출 (임베딩 · 계획 · 생성)
│       ├── answer_rules.py      답변 생성 프롬프트 규칙
│       ├── suggestions.py       추천 질문 풀 (요청마다 LLM 호출 안 함)
│       └── conversation_log.py  사용자(세션)별 대화 기록
├── scripts/
│   ├── collect/             데이터 수집·변환 (게시글 → 코퍼스, 규칙 기반 분류)
│   ├── chat.js, ask.js 등   평가·실험용 Node CLI (백엔드와 별개 구현)
│   ├── create-chunks*.js    청킹 실험 A~R
│   ├── eval-*.js            평가 (검색·생성·리랭킹 비교)
│   ├── generate_qr.py       발표 현장용 접속 QR 재생성
│   └── build-*.py           발표 PPTX 생성
├── data/
│   ├── document통합파일(에타리뷰분리).json   원본 코퍼스 907문서
│   └── importance.json                      중요도 가중치
├── outputs/
│   ├── chunking_experiments/   18개 청킹 실험 산출물
│   ├── golden_set/             80문항 평가셋 (LLM 생성 — 편향 있음, docs 참고)
│   ├── human_made_data/        300문항 평가셋
│   └── eval_results/           평가 결과
└── docs/                       실험 리포트 · 발표 자료 · 팀원 실행 안내
```

---

## 실험 결과 요약

청킹 전략 18종을 비교해 **fixed-size 500 tokens, overlap 0**을 채택했습니다.

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 청크 크기 | 500 tokens | 문서 길이 중앙값과 정합 |
| Overlap | 미채택 | 4단계 감사(구현 정합성·가설 검증·경계 감사·대체 요인 통제) 끝에 유의미한 이득을 재현하지 못함 |
| 리랭킹 | 현 단계 보류 | 과거 측정 결과가 있으나 원본 로그가 유실돼 재현 불가 — 재현 가능한 벤치마크 없이는 프로덕션에 반영하지 않는다는 원칙으로 보류 |

검색 성능 (`human_made_data` 300문항): **Recall@1 0.373 / Recall@3 0.593 / Recall@5 0.740**

> 평가셋(golden_set, human_made_data)은 모두 LLM으로 생성했고, 문항 자체에 제목 유출·근거 원문 그대로 인용 같은 편향이 섞여 있습니다. 자세한 수치와 완화 방법은 `docs/PPT_종합정리본.md`를 참고하세요.

상세 분석은 `docs/` 참고:

- `chunking_experiment_report.md` — 청킹 실험 전체
- `PROMPT_STRATEGY.md` — 프롬프트 설계
- `후속질문_구현.md` — 대화 맥락 처리
- `팀원_실행하기.md` — 빈 PC에서 클론부터 실행까지
- `PPT_종합정리본.md`, `PPT_핵심4부.md` — 발표 자료 원본

### 데이터 복구

`chroma-data/`가 없거나 손상되면 재적재하면 됩니다. 재임베딩 비용은 들지 않습니다.

```powershell
npm run chroma:py
npm run load        # outputs/chunking_experiments/D_500/ 에서 복구
npm run eval        # 골든셋으로 검증
```

직접 새로 만들려면(권장하지 않음 — 임베딩이 미묘하게 달라져 검색 순위가 어긋날 수 있음):

```bash
node scripts/embed-chunks.js D_500    # 임베딩 생성 (본인 키로 약 $0.03)
npm run load
```
