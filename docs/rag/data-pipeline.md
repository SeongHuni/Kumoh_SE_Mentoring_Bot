# RAG Data Pipeline

이 문서는 게시판 수집, 원본 스키마, 정규화와 청킹 규칙을 설명한다.

## 데이터 수집 계층

### 학과 게시판

`KumohBoardCrawler`는 `httpx + BeautifulSoup`을 사용한다. 목록의 `articleNo`를 canonical URL로 변환해 고정 공지 중복을 방지한다. 상세 페이지에서 제목, 본문, 작성자, 작성일, 첨부파일 링크를 추출한다. 이미지 전용·삭제·일시 실패 게시글은 텍스트 임베딩 대상에서 제외한다.

### SE 게시판

다음 순서로 선택한다.

1. `SEBOARD_API_URL`이 있으면 공개 JSON API 사용
2. 없으면 headless Selenium으로 렌더링 후 링크와 본문 탐색
3. 두 방식 모두 실패하면 `--allow-partial`로 학과 게시판만 저장

로그인 우회, CAPTCHA 무력화, 접근제어 회피는 범위 밖이다. API 응답 필드는 여러 후보명(`id`, `postId`, `title`, `subject`, `content`, `body` 등)을 허용하지만 실제 API가 확인되면 명시적 스키마로 좁히는 것이 좋다.

## 원본 스키마

`BoardPost`는 다음 정보를 보존한다.

| 필드 | 용도 |
| --- | --- |
| `id`, `source` | 원본 식별 및 중복 제거 |
| `title`, `content` | 검색·답변 본문 |
| `author`, `published_at` | 답변 맥락과 최신성 판단 |
| `url` | 사용자에게 제공할 canonical 출처 |
| `attachments` | 첨부 이름·링크 보존; 현재 본문은 미추출 |
| `crawled_at` | 수집 시점 추적 |

원본은 `data/raw/posts.json`에 UTF-8 JSON으로 저장한다. 벡터 DB를 원본 저장소로 사용하지 않는다.

## 주제 보강과 최신 게시글 계산

`data/topic_rules.json`은 주제 키(`key`), 화면 표시명(`label`), 분류 키워드(`keywords`), 추천 질문(`suggested_questions`)을 관리하는 단일 유지보수 지점이다. `TOPIC_RULES_PATH`로 다른 파일을 지정할 수 있지만, 운영 규칙은 한 파일에서 관리한다. 제목과 본문에 이미 지정된 `topic_key`가 없으면 가장 긴 일치 키워드를 우선해 분류하고, 일치 항목이 없으면 `default_topic_key`인 `general`을 사용한다.

인덱싱 전에 `enrich_posts`가 `topic_key`, `topic_label`, `is_latest_topic`을 파생한다. 주제별 최신 게시글은 다음 우선순위로 결정한다.

1. 파싱 가능한 `published_at`이 있는 게시글을 우선한다.
2. 유효한 게시일끼리는 `published_at`이 가장 늦은 게시글을 선택한다.
3. 게시일이 없거나 잘못된 형식이면 `crawled_at`을 비교값으로 사용한다.
4. 같은 시각이면 `crawled_at`으로 순서를 결정한다.

주제마다 한 게시글만 `is_latest_topic=true`가 되며 그 게시글에서 생성된 모든 청크가 같은 값을 갖는다. 같은 주제의 이전 게시글도 원본과 인덱스에는 보존되지만 온라인 답변 검색에서는 제외된다. 원본 게시글 또는 `data/topic_rules.json`을 변경하면 다음 명령으로 전체 인덱스를 재생성해야 한다.

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

## 정규화와 청킹

`chunking.py`는 공백과 과도한 줄바꿈을 정리한 뒤 다음 헤더를 본문 앞에 추가한다.

```text
제목: <게시글 제목>
작성일: <게시일>
본문: <게시글 본문>
```

기본값은 `chunk_size=900`, `overlap=150` 문자다. 청크 경계는 마지막 180자 안에서 줄바꿈, 문장 끝(`. `, `다. `), 공백 순으로 찾는다. 토큰 기반이 아닌 문자 기반을 선택한 이유는 짧은 한국어 공지와 100건 규모에서 구현·디버깅이 단순하기 때문이다.

선택지와 교체 기준:

| 방식 | 장점 | 단점 | 사용 시점 |
| --- | --- | --- | --- |
| 현재 문자 청킹 | 빠르고 재현 가능 | 표·목록 문맥이 끊길 수 있음 | 프로토타입 |
| 토큰 청킹 | 모델 한도를 정확히 관리 | tokenizer 의존성 | 긴 문서 증가 시 |
| 제목/문단 의미 청킹 | 공지 구조 보존 | 파서 복잡도 증가 | PDF/HWP 포함 시 |
| 문서 단위 임베딩 | 구현이 가장 단순 | 긴 글 검색 정확도 저하 | 매우 짧은 게시글만 있을 때 |

청크 크기·overlap·본문 정제 방식이 바뀌면 전체 인덱스를 재생성한다.
