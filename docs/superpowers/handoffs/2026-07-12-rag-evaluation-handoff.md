# SE Mentor Bot 자동 평가 작업 인수인계

> 갱신 시점: 2026-07-12, 설계·상세 구현 계획 완료·실행 방식 선택 전

## 작업 목표

현재 Chroma 인덱스와 RAG 경로를 local provider로 실행해 topic·grounded·latest-only·source-title을 검사하는 자동 평가 CLI와 30개 평가셋을 만든다.

## 현재 저장소 상태

- 작업 브랜치: `main`
- 원격: `origin/main`
- 시작 기준 HEAD: `8a3fe15 docs: record main integration status`
- 작업 트리는 시작 시 clean이었다.
- 기존 기능 브랜치는 `8dc3078`에서 main에 병합됐다.

## 확정된 설계

- 선택안: 비용 없는 local End-to-End 평가
- 순수 평가 계층: `backend/app/evaluation.py`
- CLI wiring: `backend/scripts/evaluate.py`
- 평가 데이터: `data/evaluation/questions.json`, 최소 30개
- 보고서: `data/evaluation/reports/latest.json`, `latest.md`; Git 제외
- 종료 코드: 성공 0, 평가 실패 1, 실행 오류 2
- 기본 provider: `local`; `configured`는 명시적으로 선택
- 런타임 API 응답 스키마는 변경하지 않는다.

설계 문서:

- `docs/superpowers/specs/2026-07-12-rag-evaluation-design.md`
- `docs/superpowers/plans/2026-07-12-rag-evaluation-implementation.md`

## 진행도

| 단계 | 상태 | 근거 |
| --- | --- | --- |
| 코드·문서 현황 재검토 | 완료 | main, PROJECT_STATUS, RAG·provider·data interface 확인 |
| 접근안 비교 | 완료 | End-to-End, retrieval-only, provider matrix 비교 |
| 사용자 설계 승인 | 완료 | 사용자가 `승인` 응답 |
| 설계 문서 작성·커밋 | 완료 | `ebb7bbb docs: design automated rag evaluation workflow` |
| 상세 구현 계획 | 완료 | Task 1~6, RED/GREEN·커밋·진행 기록 단계와 self-review 완료 |
| TDD 구현 | 대기 | subagent-driven 또는 inline 실행 방식 선택 후 시작 |
| 전체 검증·최종 리뷰 | 대기 | 구현 완료 후 실행 |

## 다음 작업자 즉시 수행 항목

1. 구현 계획과 인수인계 갱신 커밋 확인
2. 사용자에게 subagent-driven 또는 inline 실행 방식 선택 요청
3. `superpowers:using-git-worktrees`로 `codex/rag-evaluation` 격리 브랜치 준비
4. 격리 worktree baseline 26 backend tests·9 frontend tests·Ruff 확인
5. Task 1 EvaluationCase RED 테스트부터 시작

## TDD 진행 기록 형식

각 작업 뒤 이 문서에 다음을 추가한다.

- 마지막 RED 테스트와 예상 실패 이유
- GREEN 구현 파일과 통과 명령
- 전체 회귀 결과
- 마지막 커밋 hash
- 다음 시작 테스트

## 알려진 주의사항

- 현재 `data/evaluation/questions.json`은 8개이며 6개가 구조화 기대값을 갖지 않는다.
- 현재 데이터에서 `course_openings` 최신 게시일은 2025-08-07이다.
- 데이터 갱신 뒤 `expected_grounded`와 source 제목 baseline을 원문과 다시 대조해야 한다.
- OpenAI, live crawler, CI는 이번 구현 범위 밖이다.
- `.env`, API key, `chroma_db`, 평가 생성 보고서는 커밋하지 않는다.

### Task 1 — EvaluationCase와 loader

- RED: evaluation module 부재로 test collection 실패
- GREEN: 유효 입력, 중복 id, kebab-case, grounded/source 모순 테스트 통과
- 다음 시작점: topic·grounded·latest source 평가 실패 테스트
