# UI/UX 점검 로그 — 2026-08-22

## 결론

현재 UI는 초기 렌더링, 질문 제출, 로딩 잠금, 정상 답변 표시, 출처 새 탭 열기,
네트워크 오류 안내의 기본 흐름은 동작한다. 그러나 배포 전 수정이 필요한 높은 우선순위
결함이 있다. 특히 범위 밖 질문에 관련 없는 출처를 붙여 정상 답변으로 처리하는 문제,
공식 학과 사이트의 출처명 오표기, 실제 백엔드와 문서/UI 계약 불일치, 모바일에서 답변
첫 줄을 건너뛰는 자동 스크롤 문제가 재현됐다.

제품 코드는 수정하지 않았다. 이 문서와 사용자가 제공한 ChromaDB의 로컬 배치만 수행했다.

## 테스트 기준

- 기록 시각: 2026-08-22 14:42:15 +09:00
- 브랜치/커밋: `codex/askingtest` / `2e52e93`
- 프런트엔드: `http://localhost:3000/`
- 백엔드: `http://localhost:8000/`
- 브라우저: Codex in-app browser
- 화면 크기: 1280x720, 1280x600, 721x800, 720x800, 390x844, 320x568
- Node/npm/Python: v24.15.0 / 11.12.1 / 3.12.13

### 사용한 ChromaDB

- SHA-256: `54FA55C1FB151333F8CC78542132761C11034CEF03A721F93A50603B5369883C`
- 압축 크기: 29,198,286 bytes
- 배치 위치: `C:\Users\tjdgn\SummerSIG\Kumoh_SE_Mentoring_Bot\chroma-data`
- 압축 항목 19개, 절대 경로/`..` 경로 0개를 확인한 뒤 해제했다.
- `/api/health`: `ready`, `sw_notice_d500`, 1,474 chunks, `compatible`
- 실제 메타데이터 분포:
  - 총 850 documents / 1,474 chunks
  - `se게시판` 647 documents / 1,253 chunks
  - `에브리타임` 196 documents / 202 chunks
  - `학과공식사이트` 7 documents / 19 chunks
  - URL 없음 202 chunks, URL 있음 1,272 chunks, 고유 URL 654개
  - `document_type`은 1,474 chunks 모두 없음

주의: `docs/PROJECT_STATUS.md`의 현재 기준은 schema v5, 16 chunks, SE 게시판 비활성이다.
제공된 DB는 이 기준과 다르지만 현재 `inspect()`는 임베딩 모델/청크 크기/오버랩만 검사하여
`compatible`로 판정한다. 아래 실동작 결과는 사용자가 제공한 1,474-chunk DB 기준이다.

Chroma가 DB를 열 때 `chroma.sqlite3`의 내부 `acquire_write` bookkeeping 행이 증가했다
(원본 ZIP 9 → 사용 중 DB 20). SQLite `quick_check=ok`이고 collections, metadata,
segments, 1,474 embeddings, 20,353 embedding metadata, max sequence ID, migrations의 논리값은
원본과 동일하다. 원본 ZIP은 변경하지 않았다.

## 실제로 다닌 경로

| ID  | 화면/동작                                             | 실제 결과                                                                           | 판정                         |
| --- | ----------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------- |
| P01 | DB 배치 전 `GET /api/health`                          | `unavailable`, 0 chunks                                                             | 기준 상태 확인               |
| P02 | ZIP 안전성 확인 → `chroma-data/` 해제 → health 재확인 | `ready`, 1,474 chunks, compatible                                                   | 통과                         |
| P03 | `/` 최초 진입, 1280x720                               | 제목, 안내, 추천 3개, 입력창, 비활성 전송 버튼 정상 표시                            | 통과                         |
| P04 | 추천 `최근 수강신청 공지를 알려줘` 클릭               | 사용자 말풍선, typing, 입력/추천 잠금, 답변, 출처 5개, 입력 포커스 복귀             | 기본 흐름 통과               |
| P05 | P04 출처 검사                                         | URL `46283`이 1번과 3번에 중복 노출                                                 | 실패                         |
| P06 | 한 글자 `가`, 빈 값, Enter                            | 전송 비활성, 메시지 추가 없음                                                       | 통과                         |
| P07 | `학사` 후 Shift+Enter, 4줄 입력                       | 전송되지 않고 줄바꿈은 됨. textarea 높이는 계속 38px, 내부 스크롤만 증가            | 수정 필요                    |
| P08 | `캡스톤디자인 신청 방법이 뭐야?` 입력 후 Enter        | 질문 추가, 입력 초기화, typing, 정상 답변, 포커스 복귀                              | 통과                         |
| P09 | `오늘 점심 메뉴 뭐야?`                                | `no_answer`가 아니라 정상 `answer`; 홈커밍데이/멘토링 등 무관한 출처 5개 노출       | 실패                         |
| P10 | 3001번 프런트엔드에서 질문 제출                       | CORS로 네트워크 실패, 안전한 연결 오류 문구 표시                                    | 오류 UI 통과, 설정 개선 필요 |
| P11 | `소프트웨어전공 교육과정을 알려줘`                    | 답변과 공식 `cs.kumoh.ac.kr` 링크가 표시됨                                          | 부분 통과                    |
| P12 | P11 출처명/중복 검사                                  | 공식 학과 사이트 5개가 모두 `SE 게시판`으로 오표기; URL도 1↔5, 2↔4 중복             | 실패                         |
| P13 | P11 첫 출처 클릭                                      | 새 탭에서 `https://cs.kumoh.ac.kr/cs/sub0101.do` 정상 열림                          | 통과                         |
| P14 | 390x844 최초 화면                                     | 페이지 가로 넘침 없음, 추천 칩 가로 스크롤, 입력창 표시                             | 통과                         |
| P15 | 390x844에서 추천 질문 후 응답                         | window `scrollY=585`; 최신 답변 시작점 `top=-109.7px`, 답변 중간부터 보임           | 실패                         |
| P16 | 320x568 긴 답변 화면                                  | 페이지 가로 넘침은 없으나 작은 높이에서 긴 답변/입력창 이동 부담이 큼               | 관찰                         |
| P17 | 721px ↔ 720px 반응형 경계                             | padding/border/status/소개 문구가 의도한 모바일 규칙으로 전환, 가로 넘침 없음       | 통과                         |
| P18 | 1280x600 최초 화면                                    | 문서 높이 705px, composer 하단 678px로 입력창 일부가 첫 화면 아래에 잘림            | 실패                         |
| P19 | 단일 이모지 `😀`                                      | JS 길이 2라 전송 활성화; API는 1문자로 422, UI는 `답변을 불러오지 못했습니다.` 표시 | 실패                         |
| P20 | `이현아 교수님의 C++프로그래밍 강의평이 어때?`        | `no_answer`; 제공 DB의 강의평 202 chunks는 URL 부재로 검색 결과에서 제거됨          | 실패                         |
| P21 | 존재하지 않는 `/not-a-real-route`                     | 영문 기본 404, 홈으로 이동 수단 없음                                                | 개선 필요                    |
| P22 | 정상/모바일/검증 탭 console error 확인                | 수집된 console error 0건                                                            | 통과                         |

## 발견 사항

### 높음

1. **범위 밖 질문을 근거 있는 정상 답변으로 오판한다.**
   - 재현: P09.
   - `backend/app/rag.py`는 관련성 임계값 없이 결과가 하나라도 있으면 `grounded=true`로
     답변하며, 명시 카테고리 검색이 비면 전체 후보로 후퇴한다.
   - UI의 “검색된 게시글만 근거로 답한다”는 신뢰 문구와 충돌한다.

2. **출처 유형이 실제 데이터와 다르게 표시된다.**
   - 재현: P12.
   - `frontend/app/components/ChatMessage.tsx`가 `source === "kumoh"`만 학과 게시판으로,
     나머지는 모두 SE 게시판으로 표시한다. 실제 값 `학과공식사이트`도 SE 게시판이 된다.
   - 에브리타임 자료가 UI에 도달하면 마찬가지로 SE 게시판으로 오표기될 수 있다.

3. **문서에 적힌 핵심 UX와 실제 백엔드 계약이 다르다.**
   - `docs/PROJECT_STATUS.md`는 첫 질문의 clarification, 확인 intent 검색, 다음 질문,
     최근 공지를 현재 계약으로 정의한다.
   - 실제 `backend/app/schemas.py`는 `answer|no_answer`만 허용하고,
     `backend/app/main.py`는 `confirmed_intent_key`를 검색에 전달하지 않으며,
     `suggested_questions`/`recent_notices`는 항상 빈 기본값이다.
   - 결과적으로 의도 확인 카드, 의도 선택, 후속 추천, 최근 공지 UI는 실제 통합 경로에서
     도달할 수 없다.

4. **제공 DB를 현재 인덱스로 잘못 호환 판정한다.**
   - canonical 상태는 schema v5 16 chunks지만 제공 DB는 1,474 chunks이며
     `document_type`/schema 식별 메타데이터가 없다.
   - SE 게시판 비활성 정책과 달리 SE 게시판/에브리타임 데이터가 대부분이다.
   - `backend/app/chroma_store.py::inspect`가 스키마 버전과 필수 메타데이터를 검증하지 않는다.

5. **모바일 응답 후 답변 첫 줄을 건너뛴다.**
   - 재현: P15.
   - 모바일 CSS에서 message list가 내부 스크롤 영역이 아니지만 코드는 그 요소에
     `scrollTo()`를 호출한다. 이후 textarea focus가 window를 하단으로 이동시켜 답변 시작이
     화면 위로 사라진다.

### 중간

6. **같은 원문이 출처 카드에 여러 번 나온다.** P05/P12에서 실제 재현됐다. 검색 청크를
   URL 기준으로 합치지 않아 근거가 많아 보이는 착시와 불필요한 스크롤을 만든다.

7. **README가 약속한 강의평 경로가 동작하지 않는다.** 제공 DB에는 강의평 202 chunks가
   있으나 모두 `source_url`이 없고 `ChromaDataStore.search()`가 URL 없는 문서를 버린다.

8. **상태 점이 실제 health와 무관하게 항상 초록색이다.** DB 배치 전 백엔드가
   `unavailable`일 때도 화면은 동일한 초록 점과 `RAG prototype`을 표시했다.

9. **오류와 근거 없음이 같은 표현 상태다.** 모든 통신/검증 오류가
   `responseType="no_answer"`로 렌더링되고 재시도 버튼이 없다. P19는 입력 규칙 불일치까지
   겹쳐 원인을 알 수 없는 일반 오류만 보인다.

10. **긴 질문 입력창이 자동 확장되지 않는다.** Shift+Enter와 4줄 입력 모두 높이 38px로
    유지됐다. 최대 500자 입력을 한 줄 높이 내부 스크롤로 편집해야 한다.

11. **접근성 의미 구조와 대비가 부족하다.** 답변 제목/불릿을 모두 `span`으로 렌더링하고
    메시지 article에 작성자 접근성 이름이 없다. 정적 대비 계산에서 placeholder 2.63:1,
    disclaimer 3.02:1, intent focus border 약 2.35:1로 확인됐다.

12. **한국어 IME 조합 확정 Enter의 조기 제출 위험이 있다.** keydown 처리에
    `isComposing` 방어가 없다. 실제 OS IME 입력 자동화는 이번 환경에서 수행하지 못했다.

13. **좁은 높이에서 입력창이 첫 화면 아래로 밀린다.** 1280x600에서 composer의 상당 부분이
    fold 아래에 있었다. `min-height:340px`인 메시지 영역과 헤더/소개/입력 높이 합이 viewport를
    초과한다.

14. **historical 자료임을 표시할 계약이 없다.** frontend `Source`에 `document_type`이 없고,
    날짜가 없으면 생략한다. 제공 DB 자체에도 이 필드가 없다.

15. **프런트엔드 lint가 실패한다.** Next가 생성한 `frontend/next-env.d.ts`의 triple-slash
    reference를 ESLint가 검사한다. 실제 앱/테스트 소스를 그 파일 없이 검사하면 통과했다.

### 낮음

16. `prefers-reduced-motion` 대응이 없어 typing bounce와 smooth scroll이 항상 실행된다.
17. 새 탭 출처 링크에 시각적 화살표만 있고 접근 가능한 “새 탭에서 열림” 안내가 없다.
18. 404가 영문 기본 화면이며 챗봇으로 돌아가는 링크가 없다.
19. 1280x720에서 문서 높이가 viewport보다 5px 커 불필요한 바깥 스크롤이 생겼다.

## 자동 검증

| 명령                                                                                 | 결과                                          |
| ------------------------------------------------------------------------------------ | --------------------------------------------- |
| `npm --prefix frontend test`                                                         | 통과 — 6 files, 91 tests                      |
| `npm --prefix frontend run typecheck`                                                | 통과                                          |
| `npm --prefix frontend run build`                                                    | 통과 — `/`, `/_not-found` 정적 생성           |
| `npm --prefix frontend run lint`                                                     | 실패 — `frontend/next-env.d.ts:3` 1건, 경고 0 |
| `npm --prefix frontend exec eslint app` 상당 검사                                    | 실제 앱/테스트 소스 추가 오류 없음            |
| `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests` | 통과 — 8 tests, deprecation warning 1건       |
| `backend/.venv/Scripts/python.exe -m ruff check backend`                             | 통과 — All checks passed                      |

브라우저 E2E, visual regression, axe, 실제 IME 자동화는 저장소에 없다. Vitest의 mock 기반
clarification/추천/최근 공지 테스트는 통과하지만 현재 백엔드 통합 계약을 검증하지 않는다.

## 권장 수정 순서

1. 제공 DB를 운영에 사용할지 canonical schema v5 인덱스를 사용할지 먼저 결정하고,
   index schema/source policy/필수 메타데이터를 health 호환성 검사에 포함한다.
2. 실제 백엔드를 canonical clarification/no-answer/추천/최근 공지 계약에 맞추고 관련성 gate를
   복원한다.
3. 출처 종류를 명시적으로 매핑하고 URL 기준으로 중복 청크를 합친 뒤 historical을 표시한다.
4. 모바일에서는 최신 assistant 시작점을 window 기준으로 보이게 하고, 입력 focus가 답변 중간으로
   점프시키지 않도록 스크롤/레이아웃을 수정한다.
5. textarea auto-grow, IME composition guard, Unicode code point 기준 길이 검증, 오류별 시각 상태와
   재시도 동작을 추가한다.
6. 대비, semantic heading/list, 메시지 작성자 이름, reduced-motion, 낮은 viewport 높이,
   한국어 404를 보완한다.
7. `next-env.d.ts`를 lint ignore에 추가하고 390px/320px 브라우저 회귀 테스트를 CI에 추가한다.

## 변경 기록

- 추가: 이 점검 로그
- 로컬 배치: 사용자가 제공한 ZIP을 `chroma-data/`에 해제하고 실제 Chroma runtime으로 사용
- DB 참고: Chroma runtime bookkeeping만 증가했으며 컬렉션 논리 데이터는 원본과 동일
- 미수정: frontend/backend 제품 코드, canonical `data/raw/posts.json`
