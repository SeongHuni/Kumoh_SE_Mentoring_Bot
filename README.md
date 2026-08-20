# 금오공대 소프트웨어전공 RAG 챗봇

학과 공지·강의평을 근거로 답하는 RAG 챗봇입니다. 청킹 전략 실험부터 웹 서비스까지 한 저장소에 있습니다.

```
프론트엔드 (Next.js, 3000)
      │  POST /api/chat
      ▼
   API 서버 (Node, 8787)
      │
      ├─► Chroma (8000)      1,474 청크 · text-embedding-3-small
      └─► OpenAI              gpt-4o-mini
```

---

## 빠른 실행

```powershell
.\start-web.ps1
```

Chroma → API → 웹 순서로 띄우고 각 단계가 응답할 때까지 기다린 뒤 브라우저를 엽니다.

개별 실행이 필요하면:

| 명령 | 하는 일 | 포트 |
| --- | --- | --- |
| `npm run chroma:py` | Chroma 서버 (Python) | 8000 |
| `npm run chroma` | Chroma 서버 (Docker) | 8000 |
| `npm run api` | API 서버 | 8787 |
| `npm run web` | 프론트엔드 개발 서버 | 3000 |

전부 종료: `Get-Process node,chroma | Stop-Process`

### 사전 준비

```powershell
npm install                      # API 서버용
npm --prefix frontend install    # 프론트엔드용
python -m pip install chromadb   # Chroma 서버 (Docker 안 쓸 때)
```

OpenAI 키는 `.secrets/embedding-api-key.txt` 또는 환경변수 `OPENAI_API_KEY`로 제공합니다.

---

## CLI로 쓰기

웹 없이 터미널에서 바로 대화할 수 있습니다.

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

## 동작 방식

```
질문 + 대화 이력
      │
      ▼
 검색 계획기          대화 이력은 여기서만 읽는다
   ├─ 후속 질문을 독립형 질의로 재작성
   ├─ 출처·분류·시점 판단
   ├─ 대상 불명확 → 되묻기 (검색·생성 호출 안 함)
   └─ 범위 밖 → 거절
      │
      ▼
 Chroma 검색 (후보 100개)
      │
      ▼
 후처리
   ├─ 이벤트 가중치 + 시간 감쇠
   ├─ 최신 우선 (유사도 0.05 이내면 최신순)
   └─ 다양성 (주제당 2개, 문서당 2개)
      │
      ▼
 답변 생성            현재 질문 + 검색 자료만 받는다
```

**핵심 분리** — 검색 계획기만 대화 이력을 읽습니다. 답변 생성기는 현재 질문과 검색 자료만 받으므로, 이전 답변에 오류가 있어도 다음 답변의 사실로 전파되지 않습니다.

### 답변 품질을 위해 적용한 것

| 단계 | 전략 |
| --- | --- |
| 청킹 | fixed-size 500 tokens, overlap 0 · 모든 청크에 `제목/출처/분류/작성일` 헤더 부착 |
| 검색 | 출처 분리(공지 ↔ 강의평) · 분류·연도·기간 필터 · 필터 충돌 자동 차단 |
| 순위 | 이벤트 가중치 · 시간 감쇠 · 주제 다양성 · 최신 우선 |
| 질의 | 후속 질문 재작성 · 되묻기(fail-closed) · 범위 밖 거절 · 오늘 날짜 주입 |
| 생성 | 근거 강제 · 출처 번호 표기 · 프롬프트 인젝션 방어 |

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

유사도가 0.45~0.65 구간에 몰려 있어 `+0.05`면 몇 계단, `+0.1`이면 과하게 올라갑니다. 재시작만 하면 반영됩니다.

---

## API

`POST /api/chat`

```json
{ "question": "이정연 장학금 신청 어떻게 해", "confirmed_intent_key": "(선택)" }
```

```json
{
  "response_type": "answer | clarification | no_answer",
  "answer": "...",
  "grounded": true,
  "sources": [{ "title": "...", "url": "https://...", "source": "se게시판",
                "published_at": "2026-03-26", "score": 0.61 }],
  "interpreted_intent": null,
  "clarification_options": [],
  "suggested_questions": ["..."],
  "recent_notices": []
}
```

`GET /api/health` · `GET /api/live` 도 있습니다.

> `sources[].url`은 유효한 http(s) URL이어야 프론트 검증을 통과합니다. 에브리타임 강의평은 URL이 없어 출처 목록에서 제외되지만 답변 근거로는 사용됩니다.

---

## 구조

```
├── frontend/            Next.js 15 + React 19 (팀원 구현 UI)
├── server/index.js      HTTP API — 프론트 계약에 맞춘 응답
├── scripts/
│   ├── chat.js              대화형 CLI (기본)
│   ├── chat-noboost.js      대조군 — 가중치 미적용
│   ├── ask.js               단일 질문 CLI
│   ├── load-chroma.js       Chroma 적재
│   ├── lib/
│   │   ├── session.js               대화 이력 (최근 3쌍, 1,200토큰)
│   │   ├── query-planner.js         후속 질문 재작성 · 되묻기 판단
│   │   ├── retrieval-postprocess.js 다양성 · 최신 우선
│   │   ├── importance.js            이벤트 가중치 · 시간 감쇠
│   │   ├── chroma-store.js          검색 · 필터
│   │   └── rag-core.js              임베딩 · 생성 공용
│   ├── create-chunks*.js    청킹 실험 A~R
│   └── eval-*.js            평가
├── data/
│   ├── document통합파일(에타리뷰분리).json   원본 850문서
│   └── importance.json                      중요도 가중치
├── outputs/
│   ├── chunking_experiments/   18개 실험 산출물
│   ├── golden_set/             80문항 평가셋
│   ├── human_made_data/        300문항 평가셋
│   └── eval_results/           평가 결과
└── docs/                       실험 리포트 · 발표 자료
```

---

## 실험 결과 요약

청킹 전략 18종을 비교해 **fixed-size 500 tokens, overlap 0**을 채택했습니다.

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 청크 크기 | 500 tokens | 문서 길이 중앙값 445토큰과 정합 |
| Overlap | **미채택** | 4개 설정에서 차이 0.01 미만, McNemar p > 0.9 |
| 리랭킹 | 현 단계 미채택 | 지표 개선 미미, 지연 +2.2초 |

검색 성능 (300문항 평가셋): **Recall@1 0.373 / Recall@3 0.593 / Recall@5 0.740**

상세 분석은 `docs/` 참고:

- `chunking_experiment_report.md` — 청킹 실험 전체
- `PPT_SOURCE.md` · `발표대본.md` — 발표 자료
- `PROMPT_STRATEGY.md` — 프롬프트 설계
- `후속질문_구현.md` — 대화 맥락 처리

### 데이터 복구

`chroma-data/`가 없거나 손상되면 재적재하면 됩니다. 재임베딩 비용은 들지 않습니다.

```powershell
npm run chroma:py
npm run load        # outputs/chunking_experiments/D_500/ 에서 복구
npm run eval        # 골든셋으로 검증
```
