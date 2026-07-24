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
backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-static --candidate-output data/raw/candidates/kumoh-community-2024.json --seboard-limit 0
```

학과 사이트는 allowlist에 있는 정적 페이지 8개만 수집한다: 전공소개(`sub0101`), 교육목표(`sub0102`), 교육과정(`sub0105_2`), 주요성과(`sub0103`), 졸업 후 진로(`sub0104`), 비식별 교수소개(`sub0401`), 비식별 조교소개(`sub0402`), 동아리명·동아리 소개(`sub0504`). `--kumoh-limit`, `--kumoh-all`, `--kumoh-all-boards`는 학과 게시판 수집을 재개할 수 없도록 오류로 종료한다. 학과 홈페이지 공지사항(`sub0601`), 취업·행사·수상 게시판, 대학원·학생회·퇴임교수 페이지를 포함한 나머지 학과 URL은 정책 위반으로 거절된다. 금오공과대학교 학사안내 URL 계열(`www.kumoh.ac.kr/ko/sub06_01_*`)도 수집·저장하지 않는다. 허용 수집은 기존 운영 원본을 덮어쓰지 않도록 `--candidate-output`과 함께 사용한다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-static --candidate-output data/raw/candidates/kumoh-allowlist.json --seboard-limit 0
```

## 학과 게시판 차단

`KumohBoardCrawler`는 과거 파서 호환성을 위해 남아 있지만, 현 정책에서는 allowlist 밖 URL이므로 게시판 시작 URL과 상세 링크 모두 거절한다. 학과 게시판 수집을 CLI로 실행하는 옵션도 오류로 종료한다. 이 차단은 학과 홈페이지 공지사항과 수상실적뿐 아니라 취업게시판·학과행사까지 포함한다.

## 학과 정적 안내

`KumohStaticCrawler`는 `--kumoh-static`에서 전공소개·교육목표·교육과정·주요성과·졸업 후 진로·비식별 교수·조교 소개·동아리 소개 8개 공개 페이지만 수집한다. `sub0101`은 `#jwxe_main_content` 안의 전공소개·교육목표·교육과정·연혁·오시는길 본문 블록을 보존하고, `주소 및 연락처` 블록과 전화·이메일은 제거한다. 전공소개의 본문 줄은 상세 교육목표(`sub0102`)·교육과정(`sub0105_2`)과 정규화한 의미어·포함도·문자 유사도를 비교해 중복이면 제거하고, 제목·섹션 heading·고유 문맥은 보존한다. 의미 중복 제거로 줄이 다시 인접한 뒤에도 전화·이메일·연락처를 한 번 더 제거한다. 교수·조교 페이지는 profile 이름·전화·이메일·검색 UI를 제거하고 역할·소속·전공 분야만 보존한다. 동아리 페이지는 각 `h4` 동아리명과 표의 `동아리 소개` 값만 저장하며 회장·부회장·연락처·이미지는 저장하지 않는다. 첨부파일 본문은 수집하지 않는다.

일반 정적 문서는 `document_type=static`, `published_at=null`로 저장한다. 주요성과(`sub0103`)와 졸업 후 진로(`sub0104`)는 원문에 과거 성과·취업률·기업 사례가 포함돼 `document_type=historical`, `published_at=null`로 저장한다. `static`과 `historical` 문서는 검색 근거가 될 수 있지만 최근 공지 및 intent별 최신 공지 경쟁에는 참여하지 않으며, 역사 청크의 header에는 “현재 수치·현황 아님”을 명시한다. 둘 다 데이터 감사의 게시일 누락 경고 대상이 아니다.

## 원본 스키마와 보존

`BoardPost`는 다음 정보를 보존한다.

| 필드 | 용도 |
| --- | --- |
| `id`, `source` | 원본 식별과 중복 제거 |
| `title`, `content` | 검색과 답변 본문 |
| `author`, `published_at` | 답변 맥락과 공지 최신성 판단; 정적·역사 문서는 게시일이 없음 |
| `document_type` | `notice`, `static`, `historical`; `static`·`historical`은 최근 공지·최신성 경쟁에서 제외 |
| `url` | 사용자에게 제공할 canonical 출처 |
| `attachments` | 첨부 이름·링크 보존; 현재 첨부 본문은 미추출 |
| `crawled_at` | 수집 시점과 게시일 fallback |
| `topic_key`, `topic_label`, `intent_key` | 검색용 topic/intent; 원본 override 또는 인덱싱 전 파생 metadata |
| `category_key`, `category_label` | 멘토링 업무 분류: 수업, 학적·졸업, 장학금, 취업·진로, 비교과·행사, 연구·캡스톤, 대학원, 학생회, 행정·안내, 기타 |
| `llm_category` | 외부 수집·LLM 분류 입력값; 위 10개 `category_label` 중 하나만 허용하며 인덱싱 전에 대응하는 `category_key`·`category_label`로 정규화 |
| `notice_kind` | 신청·모집, 제도·행정, 행사·프로그램, 운영·이용 안내, 일반 안내의 공지 성격 |
| `is_latest_topic` | 최근 공지 보조 목록용 topic 최신 표시; 답변 검색의 단독 필터가 아님 |

정상 수집 원본은 `RAW_POSTS_PATH`가 가리키는 JSON snapshot이며 기본 경로는 `data/raw/posts.json`이다. 이 파일은 운영 원본으로 취급한다. 벡터 DB를 원본 저장소로 사용하지 않고, 부분 결과는 후보 경로에 격리해 raw snapshot의 immutability를 지킨다. 후보를 사람 검토로 승격하거나 게시글을 수정·삭제하면 원본을 갱신하고 전체 인덱스를 다시 만들어 삭제된 청크가 남지 않게 한다.

## 주제 보강과 최신 게시글 계산

SE 게시판처럼 원천 데이터에 `llm_category`가 포함된 경우에는 이 값을 10개 허용 label의 외부 category override로 보존하고, `category_key`와 `category_label`을 함께 파생한다. 값이 없을 때만 제목·본문 규칙 분류를 사용한다. URL·게시일·첨부파일 같은 canonical source 필드는 별도로 검증하며 `llm_category`만으로 원문 출처를 대체하지 않는다.

`data/topic_rules.json`은 검색용 topic key/label, 하위 intent key/label/example, 업무 category, 공지 성격, 분류 keyword, evidence/exclusion marker, suggested question과 retrieval policy를 관리하는 단일 유지보수 지점이다. `TOPIC_RULES_PATH`로 다른 파일을 지정할 수 있지만 운영 규칙은 하나의 파일에서 관리한다. `topic_key` override가 없으면 먼저 제목의 구체 keyword를 판정하고, 제목에 구체 keyword가 없을 때만 `[수업]`·`[학적]`·`[대학원]`·`[장학]`·`[교내행사]` 같은 title marker를 사용한다. 그래도 general이면 본문을 문장·문단 단위로 나눠 같은 범위에 topic keyword와 action marker가 함께 있을 때만 보조 분류한다. 일치가 없으면 `default_topic_key=general`과 `category_key=other`를 사용한다. intent도 override → 제목 → 본문 local context → topic별 fallback 순으로 정하고, `notice_kind`는 제목을 우선한 뒤 문장·문단 단위 본문 보조 판정으로 정한다.

인덱싱 전에 `enrich_posts`가 `topic_key`, `topic_label`, `category_key`, `category_label`, `intent_key`, `notice_kind`, `is_latest_topic`을 파생한다. `document_type=notice`인 같은 topic key 안에서 파싱 가능한 `published_at`을 우선해 가장 늦은 게시글을 계산하고, 게시일이 없거나 파싱되지 않는 공지는 `crawled_at`으로 비교한다. `static`·`historical` 문서는 `is_latest_topic=false`를 유지하고 recent-notice 후보에서도 제외한다. 이 표시는 최근 공지 보조 목록에 사용한다. 답변 검색은 역사 청크를 현재 정보가 아닌 참고 근거로만 포함한 뒤 관련성 판정 후 `intent_key` 단위로 최신 게시글을 다시 선택하므로 `is_latest_topic=true`만으로 검색 범위를 제한하지 않는다. `general.recent`는 예외적으로 모든 category를 탐색해 최신 공식 공지 목록을 만들고, 사용자가 제목의 고유어를 명시한 경우에는 해당 직접 근거를 우선한다. 신청·행사·제도 질의에는 호환되는 `notice_kind`만 남기고 일반 공지 질의는 모든 성격을 허용한다.

원본 게시글, topic rules, source 구성 또는 청킹 결과를 변경하면 다음 전체 재인덱싱을 실행한다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
```

## 정규화와 청킹

`chunking.py`는 공백과 과도한 줄바꿈을 정리한 뒤 다음 header를 본문 앞에 추가한다.

```text
제목: <게시글 제목>
작성일: <게시일>
문서 상태: 역사 정보 (현재 수치·현황 아님)  # historical에만 추가
본문: <게시글 본문>
```

문자 기반 청킹은 짧은 한국어 공지와 현재 prototype 규모에서 구현·디버깅이 단순하고 재현 가능하다. 기본 `CHUNK_SIZE`, `CHUNK_OVERLAP`과 경계 규칙은 `.env.example` 및 코드 설정을 따른다. 청크 경계는 가능한 경우 마지막 구간의 줄바꿈, 문장 끝, 공백에서 선택한다.

| 방식 | 장점 | 단점 | 사용 시점 |
| --- | --- | --- | --- |
| 현재 문자 청킹 | 빠르고 재현 가능 | 표·목록 문맥이 끊길 수 있음 | 현재 prototype |
| 토큰 청킹 | 모델 한도를 정확히 관리 | tokenizer 의존성 | 긴 문서 증가 시 |
| 제목/문단 의미 청킹 | 공지 구조 보존 | parser 복잡도 증가 | PDF/HWP 포함 시 |
| 문서 단위 임베딩 | 구현이 단순 | 긴 글 검색 정확도 저하 | 매우 짧은 게시글만 있을 때 |

`CHUNK_SIZE` 또는 `CHUNK_OVERLAP` 설정값을 바꾸면 signature mismatch로 API와 평가가 자동 fail closed되므로 전체 재인덱싱한다. 현재 schema v5 청크는 `intent_key`, `category_key`, `category_label`, `notice_kind`, `document_type`를 보존하며 `historical` document type을 인식한다. 정규화·청킹·metadata 계약 변경이 index 의미를 바꾸면 maintainer가 `INDEX_SCHEMA_VERSION`과 `IndexSignature.schema_version`의 Pydantic `Literal[...]`/schema validation을 의도적으로 bump한 뒤 전체 `index --reset`을 실행해야 한다. 단순 구현 변경만으로 자동 mismatch가 발생한다고 가정하지 않는다.
