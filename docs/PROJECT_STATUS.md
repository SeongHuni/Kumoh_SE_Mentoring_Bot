# SE Mentor Bot 프로젝트 상태

> 기준일: 2026-07-16
>
> 기준 구현: accuracy-first RAG, index schema v2
>
> 다음 작업자 진입점: [`HANDOFF.md`](HANDOFF.md)

이 문서는 변동 가능한 데이터 건수, 구현 준비도, 검증 결과와 남은 위험의 단일 기준이다. 실행 명령은 [`rag/operations-evaluation.md`](rag/operations-evaluation.md), 구조적 불변조건은 [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md)를 따른다.

## 현재 결론

- 첫 질문은 곧바로 검색하지 않고 `clarification` 응답으로 해석한 의도와 최대 3개 예시 선택지를 제시한다. 사용자가 고른 `confirmed_intent_key`가 질문 분석 결과의 선택지와 일치할 때만 검색한다.
- 검색은 원질문·규칙 기반 rewrite·HyDE 문장을 사용한 BM25와 dense 검색을 함께 실행하고 RRF로 합친다. 이후 intent-aware reranker, CRAG식 관련성 판정, 점수 gate, intent별 날짜 최신성, 구체 요청 근거 gate, context compression 순으로 처리한다.
- 같은 intent에서는 게시일이 가장 최신인 근거를 먼저 확정한다. 최신 글이 사용자의 세부 요청과 맞지 않으면 오래된 유사 글로 후퇴하지 않고 `no_answer`를 반환한다.
- `최근 수강신청 공지` + `registration.main`은 더 최신인 출석인정 글을 배제하고 2026-02-11 일반 수강신청 안내만 사용한다. `컴퓨터 소프트웨어 공학과에 대해 알려줘`는 교원 초빙 글을 학과 소개 근거로 사용하지 않는다.
- 답변에는 출처·게시일·원문 링크, 다음 질문, 최근 공지가 표시된다. 최근 공지는 답변 출처와 별도 목록임을 UI에서 명시하고, 근거 없음 응답에서는 더욱 강한 참고용 라벨을 사용한다.
- SE 게시판은 운영자 서면 허가 또는 승인된 공식 API가 문서화되기 전까지 수집·제공하지 않는다.

핵심 결정 3개:

1. 속도보다 정확도를 우선해 모든 질문에 의도 확인 단계를 두고, 확인되지 않은 intent에서는 provider와 저장소를 호출하지 않는다.
2. “최신”은 topic 전체가 아니라 확인된 intent 안의 `published_at` 기준으로 판정하며, 최신 근거가 질문과 불일치하면 과거 자료로 대체하지 않는다.
3. 생성 답변보다 검색 근거 계약을 우선해 hybrid retrieval → reranker → CRAG → freshness → request-evidence → compression을 모두 통과한 문서만 provider에 전달한다.

## 구현 및 검증 진행도

| 영역 | 상태 | 2026-07-16 근거 | 남은 조건 |
| --- | --- | --- | --- |
| 의도 확인 API | 완료 | `clarification` / `answer` / `no_answer`, confirmed intent 검증 | 실제 사용자 질문 로그 기반 intent catalog 확장 |
| 정확도 우선 RAG | 완료 | BM25+dense RRF, deterministic reranker, CRAG, 최신성, compression | OpenAI provider 별도 평가·calibration |
| 로컬 인덱스 | 완료 | schema v2, 50 posts → 84 chunks, main fingerprint prefix `bdba760dc6cb` | 원본·규칙·provider 변경 시 재생성 |
| 평가 | 로컬 통과 | 31/31, topic 31/31, intent 31/31, grounded 31/31, latest-only 31/31 | 질문 다양성·실사용 로그 기반 세트 확대 |
| 백엔드 품질 gate | 통과 | 407 tests, 93.92% coverage, Ruff 통과 | 운영 부하·장애 주입 테스트 |
| 프론트엔드 품질 gate | 통과 | 6 files / 91 tests, typecheck, ESLint, Next production build | 390px 모바일 visual regression 자동화 |
| 브라우저 통합 검증 | 통과 | 의도 카드 → 선택 → 최신 근거 답변, 자동 스크롤, 출처·추천·최근 공지, console error 0 | 자동화된 cross-browser E2E |
| 데이터 감사 | 경고 있음 | 50 posts, 3 warnings, exit 1 | SE source 미수집, course_openings·graduation 비어 있음 |
| 의존성 | 통과 | `npm audit --omit=dev`: 0 vulnerabilities | 정기 재검증 |
| Docker runtime | 미검증 | 현재 호스트에 Docker executable 없음 | Docker host에서 config/build/health 검증 |
| 원격 CI·배포 | 미확인 | 로컬 검증만 수행 | push 후 GitHub Actions와 branch protection 확인 |

## 현재 데이터 snapshot

| 항목 | 값 |
| --- | --- |
| canonical 원본 | `data/raw/posts.json` |
| 게시글 | 50 (`kumoh=50`, `seboard=0`) |
| 인덱스 | local hash, schema v2, 84 chunks |
| 인덱스 생성 시각 | 2026-07-16T07:10:26Z |
| 평가 | 31/31, exit 0 |
| 데이터 감사 | 3 warnings, exit 1 |

감사 기준 topic 분포는 `registration=13`, `capstone=2`, `career=14`, `scholarship=6`, `general=15`, `course_openings=0`, `graduation=0`이다. 감사 경고는 다음과 같다.

- `missing_source`: SE 게시판 미수집. 현재는 의도된 안전 제한이지만 데이터 범위는 좁다.
- `empty_topic`: `course_openings` 직접 근거 없음.
- `empty_topic`: `graduation` 직접 근거 없음.

이 snapshot은 저장된 원본의 상태일 뿐 공식 사이트의 실시간 최신성을 보증하지 않는다. 중요한 일정은 응답의 canonical URL과 게시일을 원문에서 다시 확인한다.

## 실제 회귀 시나리오

| 질문 | 확인 intent | 기대 결과 |
| --- | --- | --- |
| 최근 수강신청 공지를 알려줘 | `registration.main` | 2026-02-11 일반 수강신청 안내, 출석인정 글 배제 |
| 최근 수강변경 공지를 알려줘 | `registration.change` | 2026-02-26 변경·정정 안내 |
| 2026학년도 2학기 캡스톤디자인 공지 | `capstone.general` | 현재 1학기 근거뿐이므로 `no_answer` |
| 최근 취업 프로그램을 알려줘 | `career.general` | 최신 career 글이 교원 초빙이므로 과거 프로그램으로 후퇴하지 않고 `no_answer` |
| 장학금 신청 공지를 알려줘 | `scholarship.general` | 최신 scholarship 글에 신청 직접 근거가 없어 `no_answer` |
| 오늘 학생식당 메뉴를 알려줘 | `general.recent` | 수집 범위 밖이므로 `no_answer` |
| 컴퓨터 소프트웨어 공학과에 대해 알려줘 | `department.overview` | 학과 소개 직접 근거가 없어 `no_answer` |

## API와 UI 계약

- 최초 `/api/chat` 요청은 `confirmed_intent_key`가 없으면 `response_type=clarification`, `grounded=false`, 빈 `sources`, `interpreted_intent`, `clarification_options`를 반환한다.
- 선택 후 동일 질문과 `confirmed_intent_key`를 보내며 사용자 질문 말풍선을 중복 추가하지 않는다.
- 근거가 있으면 `answer`, 없으면 `no_answer`; `no_answer`는 항상 빈 `sources`를 유지한다.
- frontend는 API payload와 HTTP/HTTPS 링크를 runtime에서 검증하며 timeout·network·non-JSON 오류를 사용자용 문장으로 바꾼다.
- 새 assistant 결과가 생기면 채팅 컨테이너를 결과의 시작 위치로 이동해 답변 첫 줄이 바로 보인다.
- local 답변은 장식 문자를 제거하고 공지 제목·분류·게시일·핵심 내용·자료 번호·원문 확인을 시각적으로 구분한다.
- `recent_notices`는 답변 근거와 별도 보조 정보다. 같은 URL이 포함되더라도 source card의 근거 계약을 대신하지 않는다.

## 남은 우선순위

1. 공식 source 보강: `course_openings`, `graduation`의 승인된 원문을 확보하고 intent 규칙·평가를 함께 갱신한다.
2. OpenAI provider 검증: provider-matched reindex → 31건 이상 평가 → raw candidate 분포 수집 → threshold calibration을 수행한다.
3. 운영 검증: Docker Compose runtime, 원격 CI, 390px 모바일·다른 브라우저 E2E를 증거와 함께 기록한다.
4. 운영성: 개인정보 없는 검색 지연·intent·거절 사유 telemetry, rate limit, backup/restore, 증분 update/delete를 설계한다.
5. 데이터 권한: SE 게시판은 서면 허가 또는 승인된 공식 API가 확보된 뒤에만 별도 source 계약 테스트와 함께 활성화한다.

## 유지보수 규칙

- intent, topic keyword, evidence/exclusion marker, 추천 질문은 `data/topic_rules.json`에서 함께 관리한다.
- intent 또는 topic 규칙, 원본, 임베딩 provider/model/dimension, collection, 청킹 설정을 바꾸면 `index --reset` 후 평가·감사를 다시 실행한다.
- 인덱스 의미를 바꾸는 metadata/청킹 계약 변경은 `INDEX_SCHEMA_VERSION`과 Pydantic `Literal[...]`을 함께 올린다.
- 데이터·평가·테스트 수치를 재실행하지 않았으면 최신 값처럼 문서에 쓰지 않는다.
- `.env`, API key, password, bearer token은 커밋·문서·로그에 기록하지 않는다.
