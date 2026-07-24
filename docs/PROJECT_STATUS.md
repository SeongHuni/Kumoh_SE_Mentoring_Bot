# SE Mentor Bot 프로젝트 상태

> 기준일: 2026-07-24
>
> 기준 구현: accuracy-first RAG, index schema v5
>
> 다음 작업자 진입점: [`HANDOFF.md`](HANDOFF.md)

이 문서는 변동 가능한 데이터 건수, 구현 준비도, 검증 결과와 남은 위험의 단일 기준이다. 실행 명령은 [`rag/operations-evaluation.md`](rag/operations-evaluation.md), 구조적 불변조건은 [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md)를 따른다.

## 현재 결론

- 첫 질문은 곧바로 검색하지 않고 `clarification` 응답으로 해석한 의도와 최대 3개 예시 선택지를 제시한다. 사용자가 고른 `confirmed_intent_key`가 질문 분석 결과의 선택지와 일치할 때만 검색한다.
- 검색은 원질문·규칙 기반 rewrite·HyDE 문장을 사용한 BM25와 dense 검색을 함께 실행하고 RRF로 합친다. 이후 intent-aware reranker, CRAG식 관련성 판정, 점수 gate, intent별 날짜 최신성, 구체 요청 근거 gate, context compression 순으로 처리한다.
- 같은 intent에서는 게시일이 가장 최신인 근거를 먼저 확정한다. 최신 글이 사용자의 세부 요청과 맞지 않으면 오래된 유사 글로 후퇴하지 않고 `no_answer`를 반환한다. 단, `general.recent`는 category를 가로질러 최신 공식 공지를 찾고 제목의 고유어를 명시한 조회는 직접 근거를 우선한다.
- 게시글은 검색 topic·intent와 별개로 멘토링 category와 `notice_kind`를 보존한다. 신청·행사·제도 요청은 호환되는 공지 성격만 답변 근거로 남긴다.
- `최근 수강신청 공지` + `registration.main`은 더 최신인 출석인정 글을 배제하고 2026-02-11 일반 수강신청 안내만 사용한다. `컴퓨터 소프트웨어 공학과에 대해 알려줘`는 교원 초빙 글을 학과 소개 근거로 사용하지 않는다.
- 답변에는 출처·게시일·원문 링크, 다음 질문, 최근 공지가 표시된다. 최근 공지는 답변 출처와 별도 목록임을 UI에서 명시하고, 근거 없음 응답에서는 더욱 강한 참고용 라벨을 사용한다.
- SE 게시판은 운영자 서면 허가 또는 승인된 공식 API가 문서화되기 전까지 수집·제공하지 않는다.
- 학과 사이트 수집 범위는 전공소개(`sub0101`)·교육목표(`sub0102`)·교육과정(`sub0105_2`)·주요성과(`sub0103`)·졸업 후 진로(`sub0104`)·비식별 교수소개(`sub0401`)·비식별 조교소개(`sub0402`)·동아리명/동아리 소개(`sub0504`)의 정적 8페이지뿐이다. 전공소개 페이지에서는 전공소개·교육목표·교육과정·연혁·오시는길의 본문 블록을 보존하고, 상세 교육목표·교육과정과 의미 중복을 제거한다. 주요성과와 졸업 후 진로는 `historical` 참고 문서로 저장해 최신성·최근 공지에 사용하지 않는다. 학과 게시판 전체와 나머지 학과 페이지는 crawler가 거절한다.
- 금오공과대학교 학사안내 사이트(`www.kumoh.ac.kr/ko/sub06_01_*`)도 수집·저장하지 않는다. 게시판·정적 안내 crawler 모두에서 URL 계열을 거절하며, 현재 원본·후보·로컬 인덱스에서 관련 데이터는 0건이다.
- 교수·조교 소개에서는 이름·전화·이메일을 제거하고 역할·소속·전공 분야만 남긴다. 동아리 페이지에서는 회장·부회장·연락처 대신 동아리명과 동아리 소개만 남긴다.
- 최신 공개 페이지를 다시 수집한 8개 allowlist 원본을 canonical snapshot으로 승격했고, local provider로 schema v5 Chroma 인덱스 16청크를 재생성했다. SE source는 여전히 비활성 상태다.

핵심 결정 3개:

1. 속도보다 정확도를 우선해 모든 질문에 의도 확인 단계를 두고, 확인되지 않은 intent에서는 provider와 저장소를 호출하지 않는다.
2. “최신”은 기본적으로 확인된 intent 안의 `published_at` 기준으로 판정하며, 최신 근거가 질문과 불일치하면 과거 자료로 대체하지 않는다. 전체 최신 공지만 예외적으로 category 전체를 탐색한다.
3. 생성 답변보다 검색 근거 계약을 우선해 hybrid retrieval → reranker → CRAG → freshness → request-evidence → compression을 모두 통과한 문서만 provider에 전달한다.

## 구현 및 검증 진행도

| 영역 | 상태 | 2026-07-24 근거 | 남은 조건 |
| --- | --- | --- | --- |
| 의도 확인 API | 완료 | `clarification` / `answer` / `no_answer`, confirmed intent 검증 | 실제 사용자 질문 로그 기반 intent catalog 확장 |
| 정확도 우선 RAG | 완료 | BM25+dense RRF, deterministic reranker, CRAG, 최신성, compression | OpenAI provider 별도 평가·calibration |
| 로컬 인덱스 | 완료 | schema v5, canonical 8 posts, Chroma 16 chunks, local manifest 생성 | 현재 8건 기준 평가 baseline 생성 |
| 평가 | 대기 | 기존 31/31은 공지사항 삭제 전의 역사 결과이며 현재 8건 원본에는 적용하지 않음 | 현재 원본·인덱스 기준 재평가 |
| 백엔드 품질 gate | 통과 | 462 tests, Ruff 통과 (`llm_category` 입력 계약 포함); coverage 93.82%는 이전 측정 | 현재 coverage 재측정, 운영 부하·장애 주입 테스트 |
| 프론트엔드 품질 gate | 통과 | 6 files / 91 tests, typecheck, ESLint, Next production build | 390px 모바일 visual regression 자동화 |
| 브라우저 통합 검증 | 통과 | 의도 카드 → 선택 → 최신 근거 답변, 자동 스크롤, 출처·추천·최근 공지, console error 0 | 자동화된 cross-browser E2E |
| 데이터 감사 | 경고 있음 | canonical 8건 감사 결과 `empty_topic` 10건; 정적 8페이지 allowlist의 의도된 범위 경고 | 정적 자료의 topic/category 매핑 검토 |
| 의존성 | 통과 | `npm audit --omit=dev`: 0 vulnerabilities | 정기 재검증 |
| Docker runtime | 미검증 | 현재 호스트에 Docker executable 없음 | Docker host에서 config/build/health 검증 |
| 원격 CI·배포 | 미확인 | 로컬 검증만 수행 | push 후 GitHub Actions와 branch protection 확인 |

## 현재 데이터 snapshot

| 항목 | 값 |
| --- | --- |
| canonical 원본 | `data/raw/posts.json` |
| 게시글 | 8 (`data/raw/posts.json`) |
| 인덱스 | schema v5, 16 chunks, local provider manifest 생성 |
| 인덱스 생성 시각 | 2026-07-24T08:03:19.901237Z |
| 평가 | 대기 — 기존 31/31은 삭제 전 역사 결과 |
| 데이터 감사 | canonical 8건, `--required-source kumoh` 기준 `empty_topic` 10 warnings, exit 1 |

검토 후보 `data/raw/candidates/kumoh-static-expanded-with-achievements-assistants-2026-07-24.json` 8건을 `data/raw/posts.json`으로 승격했다. 전공소개(`sub0101`)는 전공소개·교육목표·교육과정·연혁·오시는길 블록을 의미 중복 제거 뒤 1,435자로 보존했고, 교육목표(`sub0102`)·교육과정(`sub0105_2`)·비식별 교수소개(`sub0401`)·비식별 조교소개(`sub0402`)·동아리명·동아리 소개(`sub0504`)는 허용 본문만 보존했다. 주요성과(`sub0103`)와 졸업 후 진로(`sub0104`)는 `document_type=historical`로 표시한다. 모든 학과 게시판, 대학원·학생회·퇴임교수 등 나머지 학과 페이지, 금오공과대학교 학사안내 URL 계열은 0건이다. 교수·조교의 이름·전화·이메일과 동아리 회장·부회장·연락처는 저장하지 않는다. 인덱스에는 분류·intent metadata를 파생해 반영했다.

현재 canonical 감사는 10건의 `empty_topic` 경고를 냈다. `--required-source kumoh`로 SE 비활성 정책을 반영했으며, allowlist가 멘토링용 정적 8페이지로 제한되어 공지·신청·모집 중심 topic에 직접 근거가 없는 것이 원인이다. 이는 허용 범위의 의도된 한계다.

이 snapshot은 저장된 원본의 상태일 뿐 공식 사이트의 실시간 최신성을 보증하지 않는다. 중요한 일정은 응답의 canonical URL과 게시일을 원문에서 다시 확인한다.

## 기존 회귀 시나리오 (삭제 전 역사 기록)

아래 결과는 삭제 전 canonical 50건·84 청크 인덱스에서의 회귀 기록이다. 현재 8건·16청크 원본과 인덱스에서 재현 가능한 현재 결과로 해석하지 않는다.

| 질문 | 확인 intent | 기대 결과 |
| --- | --- | --- |
| 최근 수강신청 공지를 알려줘 | `registration.main` | 2026-02-11 일반 수강신청 안내, 출석인정 글 배제 |
| 최근 수강변경 공지를 알려줘 | `registration.change` | 2026-02-26 변경·정정 안내 |
| 2026학년도 2학기 캡스톤디자인 공지 | `capstone.general` | 현재 1학기 근거뿐이므로 `no_answer` |
| 최근 취업 프로그램을 알려줘 | `career.general` | 최신 career 글이 학생 취업 프로그램 직접 근거가 아니므로 과거 프로그램으로 후퇴하지 않고 `no_answer` |
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

1. 현재 8건 정적 원본의 topic/category 매핑을 검토하고, 범위 밖인 SE·학과 게시판·기타 학과 페이지는 추가하지 않는다.
2. 현재 8건·16청크 local index 기준으로 평가 baseline을 만들고, 감사의 10개 `empty_topic` 경고를 범위 한계로 기록한다.
3. OpenAI provider 검증: provider-matched reindex → 31건 이상 평가 → raw candidate 분포 수집 → threshold calibration을 수행한다.
4. 운영 검증: Docker Compose runtime, 원격 CI, 390px 모바일·다른 브라우저 E2E를 증거와 함께 기록한다.
5. 운영성: 개인정보 없는 검색 지연·intent·거절 사유 telemetry, rate limit, backup/restore, 증분 update/delete를 설계한다.

## 유지보수 규칙

- intent, topic keyword, evidence/exclusion marker, category, notice kind, 추천 질문은 `data/topic_rules.json`에서 함께 관리한다.
- intent 또는 topic 규칙, 원본, 임베딩 provider/model/dimension, collection, 청킹 설정을 바꾸면 `index --reset` 후 평가·감사를 다시 실행한다.
- 인덱스 의미를 바꾸는 metadata/청킹 계약 변경은 `INDEX_SCHEMA_VERSION`과 Pydantic `Literal[...]`을 함께 올린다.
- 데이터·평가·테스트 수치를 재실행하지 않았으면 최신 값처럼 문서에 쓰지 않는다.
- `.env`, API key, password, bearer token은 커밋·문서·로그에 기록하지 않는다.
