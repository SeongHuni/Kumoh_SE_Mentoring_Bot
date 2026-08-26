# 원천 데이터와 수집 도구

최종 코퍼스(`data/document통합파일(에타리뷰분리).json`)가 어떻게 만들어졌는지 남겨둔 곳이다.
챗봇을 돌리는 데는 필요 없다. 데이터가 어디서 왔는지 확인하거나 다시 만들 때 본다.

## 에브리타임 강의평

```
html/ ──parser.py──> 과목별json/ ──convert_everytime_reviews.js──> converted/
```

| 경로 | 내용 |
| --- | --- |
| `에브리타임/html/` | 에브리타임에서 받은 원본 HTML (과목별 article/overview) |
| `에브리타임/parser.py` | HTML을 과목별 JSON으로 변환 |
| `에브리타임/과목별json/` | 과목 32개의 강의평 JSON |
| `에브리타임/convert_everytime_reviews.js` | 과목별 JSON을 문서 형식으로 변환 |
| `에브리타임/converted/` | 변환 결과. 최종 코퍼스에 합쳐졌다 |

실명 교수명이 들어 있다. 공개 저장소나 외부 서비스에 올리지 않는다.

## 학과 게시판

| 경로 | 내용 |
| --- | --- |
| `게시판/kumoh_crawler.py` | 학교 공지 수집 |
| `게시판/kumoh_notices.json` | 초기 수집분 |
| `게시판/classify_board_posts.py` | 제목 기준 분류 라벨링 |
| `게시판/apply_review.py` | 검토 체크리스트에서 제외 대상을 걸러내는 스크립트 |

지금 게시판 데이터를 갱신할 때는 이 스크립트가 아니라
`scripts/collect/fetch-new-posts.js` 를 쓴다. seboard 공개 API 를 쓰는 쪽이 더 안정적이다.

## 강의 정보

| 경로 | 내용 |
| --- | --- |
| `강의정보/generate_course_info.py` | 개설강좌 엑셀을 JSON으로 |
| `강의정보/course_info.json` | 변환 결과 |
| `강의정보/개설강좌 26-*.xlsx` | 학사 시스템에서 받은 개설강좌 목록 |

## 학사 FAQ

여기 없다. `scripts/collect/fetch-faq.js` 가 대학 홈페이지에서 직접 받아온다.
수집 결과는 `outputs/faq_raw.json`, 변환 결과는 `outputs/faq_converted.json` 이다.

## 저장소에 없는 것

아래는 용량이 크고 최종 코퍼스로 이미 대체돼서 `../../_archive/` 에 두었다(깃 제외).

- `sw-rag-share/` — 팀원 배포용 옛 스냅샷 (101MB)
- `크롤원본/` — 게시판 크롤 중간 산출물 3종 (22MB, 약 2,000파일)
- `전처리/` — 통합 전 단계별 산출물 (9.8MB)
- `zip/` — 위 폴더들의 압축 중복본
