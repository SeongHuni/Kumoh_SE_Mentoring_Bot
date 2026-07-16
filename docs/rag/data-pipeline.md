# RAG Data Pipeline

이 문서는 게시판 수집, 원본 snapshot, 최신성, 정규화와 청킹 규칙을 설명한다.

## SE 게시판 실행 경계

SE 게시판은 `seboard.site/robots.txt`의 전체 `Disallow: /` 정책처럼 robots가 자동 수집을 금지하는 동안 실행하지 않는다. 운영자 서면 허가 또는 사용 범위가 문서화된 승인된 공식 API를 확보하기 전에는 public CLI에서 `--seboard-limit`을 양수로 지정하지 않는다.

공용 CLI의 기본값은 `--seboard-limit 0`이다. 양수를 지정하려면 `--seboard-permission-confirmed`가 필요하지만, 이 flag는 운영자가 권한을 확인했다는 의사를 기록할 뿐 실제 허가나 API 이용 권한을 대신하지 않는다.

public CLI가 positive limit에 대해 기술적으로 검증하는 것은 `--seboard-permission-confirmed` acknowledgement뿐이다. CLI는 실행 시 `robots.txt`를 다시 조회하거나, 서면 허가의 진위·범위 또는 `SEBOARD_API_URL`의 allowlist 등록을 자동 검증하지 않는다. 따라서 flag만으로 권한이 생기지 않으며, 실제 permission·API 문서화와 사용 범위 확인은 operator governance 책임이다. crawler internals에 자동 allowlist가 있다고 가정하지 않는다.

권한과 사용 범위가 문서화된 뒤에는 승인된 JSON API를 먼저 사용한다. `SEBOARD_API_URL`이 승인된 API 주소를 가리킬 때 crawler는 JSON 응답을 사용하고, API 경로가 승인되지 않았거나 제공되지 않는 경우에만 허용 범위 안에서 Selenium을 두 번째 선택지로 사용한다. 로그인·인증 우회, CAPTCHA 무력화, 접근제어 회피는 하지 않는다.

부분 수집은 운영 원본으로 바로 승격하지 않는다. `--allow-partial` 결과는 `data/raw/candidates/posts-partial.json` 후보에만 저장하고, 사람이 각 후보의 source·canonical URL·게시일·본문 범위를 검토한 뒤 승인된 것만 `data/raw/posts.json`에 반영한다. 후보 승격이나 원본 변경 후에는 전체 재인덱싱과 평가·감사를 다시 실행한다.

현재 허용된 public 실행 예시는 다음과 같다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-limit 50 --seboard-limit 0
```

## 학과 게시판

`KumohBoardCrawler`는 `httpx + BeautifulSoup`을 사용한다. 목록의 `articleNo`를 canonical URL로 변환해 고정 공지 중복을 줄이고, 상세 페이지에서 제목·본문·작성자·작성일·첨부파일 링크를 추출한다. 이미지 전용·삭제·일시 실패 게시글은 텍스트 임베딩 대상에서 제외한다.

## 원본 스키마와 보존

`BoardPost`는 다음 정보를 보존한다.

| 필드 | 용도 |
| --- | --- |
| `id`, `source` | 원본 식별과 중복 제거 |
| `title`, `content` | 검색과 답변 본문 |
| `author`, `published_at` | 답변 맥락과 최신성 판단 |
| `url` | 사용자에게 제공할 canonical 출처 |
| `attachments` | 첨부 이름·링크 보존; 현재 첨부 본문은 미추출 |
| `crawled_at` | 수집 시점과 게시일 fallback |
| `topic_key`, `topic_label`, `intent_key` | 원본 override 또는 인덱싱 전 파생 분류 metadata |
| `is_latest_topic` | 최근 공지 보조 목록용 topic 최신 표시; 답변 검색의 단독 필터가 아님 |

정상 수집 원본은 `RAW_POSTS_PATH`가 가리키는 JSON snapshot이며 기본 경로는 `data/raw/posts.json`이다. 이 파일은 운영 원본으로 취급한다. 벡터 DB를 원본 저장소로 사용하지 않고, 부분 결과는 후보 경로에 격리해 raw snapshot의 immutability를 지킨다. 후보를 사람 검토로 승격하거나 게시글을 수정·삭제하면 원본을 갱신하고 전체 인덱스를 다시 만들어 삭제된 청크가 남지 않게 한다.

## 주제 보강과 최신 게시글 계산

`data/topic_rules.json`은 topic key/label, 하위 intent key/label/example, 분류 keyword, evidence/exclusion marker, suggested question과 retrieval policy를 관리하는 단일 유지보수 지점이다. `TOPIC_RULES_PATH`로 다른 파일을 지정할 수 있지만 운영 규칙은 하나의 파일에서 관리한다. `topic_key` override가 없으면 제목의 가장 긴 일치 keyword를 먼저 사용하고, 제목이 general이면 제목+본문을 다시 분류한다. 일치가 없으면 `default_topic_key=general`을 사용한다. intent도 override → 제목 → 제목+본문 → topic별 fallback 순으로 정한다.

인덱싱 전에 `enrich_posts`가 `topic_key`, `topic_label`, `intent_key`, `is_latest_topic`을 파생한다. 같은 topic key 안에서 파싱 가능한 `published_at`을 우선해 가장 늦은 게시글을 계산하고, 게시일이 없거나 파싱되지 않는 게시글은 `crawled_at`으로 비교한다. 이 `is_latest_topic`은 최근 공지 보조 목록에 사용한다. 답변 검색은 과거 청크도 topic 후보군에 포함한 뒤 관련성 판정 후 `intent_key` 단위로 최신 게시글을 다시 선택하므로 `is_latest_topic=true`만으로 검색 범위를 제한하지 않는다.

원본 게시글, topic rules, source 구성 또는 청킹 결과를 변경하면 다음 전체 재인덱싱을 실행한다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
```

## 정규화와 청킹

`chunking.py`는 공백과 과도한 줄바꿈을 정리한 뒤 다음 header를 본문 앞에 추가한다.

```text
제목: <게시글 제목>
작성일: <게시일>
본문: <게시글 본문>
```

문자 기반 청킹은 짧은 한국어 공지와 현재 prototype 규모에서 구현·디버깅이 단순하고 재현 가능하다. 기본 `CHUNK_SIZE`, `CHUNK_OVERLAP`과 경계 규칙은 `.env.example` 및 코드 설정을 따른다. 청크 경계는 가능한 경우 마지막 구간의 줄바꿈, 문장 끝, 공백에서 선택한다.

| 방식 | 장점 | 단점 | 사용 시점 |
| --- | --- | --- | --- |
| 현재 문자 청킹 | 빠르고 재현 가능 | 표·목록 문맥이 끊길 수 있음 | 현재 prototype |
| 토큰 청킹 | 모델 한도를 정확히 관리 | tokenizer 의존성 | 긴 문서 증가 시 |
| 제목/문단 의미 청킹 | 공지 구조 보존 | parser 복잡도 증가 | PDF/HWP 포함 시 |
| 문서 단위 임베딩 | 구현이 단순 | 긴 글 검색 정확도 저하 | 매우 짧은 게시글만 있을 때 |

`CHUNK_SIZE` 또는 `CHUNK_OVERLAP` 설정값을 바꾸면 signature mismatch로 API와 평가가 자동 fail closed되므로 전체 재인덱싱한다. 현재 schema v2 청크는 `intent_key`를 보존한다. 정규화·청킹·metadata 계약 변경이 index 의미를 바꾸면 maintainer가 `INDEX_SCHEMA_VERSION`과 `IndexSignature.schema_version`의 Pydantic `Literal[...]`/schema validation을 의도적으로 bump한 뒤 전체 `index --reset`을 실행해야 한다. 단순 구현 변경만으로 자동 mismatch가 발생한다고 가정하지 않는다.
