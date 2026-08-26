"""se게시판 data 게시글을 제목 기준으로 라벨링하고, 불필요한 라벨(취업·진로, 대학원)의
게시글을 _removed/ 로 이동한다. '기타'로 분류된 글은 삭제하지 않고 검토 체크리스트만 만든다.

사용법:
    ANTHROPIC_API_KEY=... python classify_board_posts.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from anthropic import Anthropic

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

BOARD_ROOT = Path("se게시판 data")
MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 30

LABELS = [
    "수업",
    "학적·졸업",
    "장학금",
    "취업·진로",
    "비교과·행사",
    "연구·캡스톤",
    "대학원",
    "학생회",
    "행정·안내",
    "기타",
]
DELETE_LABELS = {"취업·진로", "대학원"}
REVIEW_LABEL = "기타"

SYSTEM_PROMPT = """\
너는 대학교 컴퓨터공학부 SE(소프트웨어전공) 학과 게시판 공지글의 제목만 보고
아래 10개 라벨 중 하나로 분류하는 분류기다.

라벨 목록과 기준:
- 수업: 수강신청/수강정정/수강지도, 강의평가, 성적, 출결, 봉사활동 교과목, 개설강좌 변경/증원 등
  "수업 운영"과 직접 관련된 글. 제목에 [수업] 태그가 있어도 실제로는 다른 라벨이 맞을 수 있으니
  본문 성격을 기준으로 판단할 것.
- 학적·졸업: 졸업요건, 졸업사정, 마이크로디그리, 복수전공/부전공, 조기졸업, 휴학/복학, 전과 등
- 장학금: 각종 장학금 신청/선발/지급 안내
- 취업·진로: 채용공고, 채용설명회, 인턴십, 취업 관련 특강/캠프 등 "취업" 자체가 목적인 글.
  단, 졸업요건으로 지정된 "취업진로교육/취업진로상담 교과목" 이수 안내처럼 실제로는 학사 필수
  이수 절차인 경우는 "수업" 또는 "학적·졸업"으로 분류하고 이 라벨을 쓰지 말 것.
- 비교과·행사: 학과 주최 비교과 프로그램(멘토링, 튜터링, 홈커밍데이, MT, 동아리 모집 등),
  교내 행사, 대회, 공모전 등. 채용/취업 목적이 아닌 일반 행사.
- 연구·캡스톤: 캡스톤디자인 운영/분반/멘토링, 학부연구생 모집, 연구실 모집, 학술대회 참가비 지원,
  논문 장려금 등 연구·캡스톤 활동
- 대학원: 대학원 입학/진학, 학·석사연계과정, 대학원생 대상 장학금/지원 등 "대학원" 자체가
  핵심 주제인 글
- 학생회: 학생회(SERVER 등) 임원 모집, 학생회비, 학생회 주관 공지 등 학생회 자체 운영 관련 글
- 행정·안내: 사물함 배정, 시설 공사, 안전 안내, 개인정보 주의, 증명서 발급, IT 서비스 안내 등
  행정 처리·시설·안전 관련 공지
- 기타: 위 9개 어디에도 명확히 들어맞지 않거나 애매한 글

각 게시글은 "articleNo | [categoryName] 제목" 형태로 주어진다. categoryName은 참고용 힌트일 뿐
그대로 라벨이 되는 것은 아니다 (예: categoryName이 "일반"이어도 학생회 관련 내용이면 "학생회").

반드시 submit_classification 도구를 호출해서, 입력으로 받은 모든 articleNo에 대해
정확히 하나씩 라벨을 지정할 것. 라벨은 위 10개 중 하나여야 한다.
"""

CLASSIFY_TOOL = {
    "name": "submit_classification",
    "description": "게시글 제목들에 대한 분류 라벨을 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "articleNo": {"type": "integer"},
                        "label": {"type": "string", "enum": LABELS},
                    },
                    "required": ["articleNo", "label"],
                },
            }
        },
        "required": ["classifications"],
    },
}


def load_json_lenient(path: Path) -> Optional[Dict]:
    """JSON 파일을 읽는다. 파일 끝에 잡텍스트가 붙어있어도(예: 45887.json)
    첫 번째 유효한 JSON 객체만 추출해 반환한다. 아예 파싱 불가능하면 None."""
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        obj, _end = json.JSONDecoder().raw_decode(text)
        return obj
    except json.JSONDecodeError:
        return None


def discover_posts(board_root: Path) -> List[Dict]:
    """board_root 아래 모든 {기간 폴더}/posts/*.json 을 읽어 목록으로 반환한다."""
    posts: List[Dict] = []
    period_folders = sorted(p for p in board_root.iterdir() if p.is_dir())

    for period_folder in period_folders:
        posts_dir = period_folder / "posts"
        if not posts_dir.exists():
            continue
        for json_path in sorted(posts_dir.glob("*.json")):
            data = load_json_lenient(json_path)
            if data is None:
                print(f"  ⚠ 파싱 실패, 건너뜀: {json_path}")
                continue
            posts.append(
                {
                    "articleNo": data.get("articleNo", json_path.stem),
                    "title": data.get("title", ""),
                    "categoryName": data.get("categoryName", ""),
                    "path": json_path,
                    "period_folder": period_folder.name,
                }
            )
    return posts


def chunked(items: List, size: int) -> List[List]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def classify_batch(client: Anthropic, batch: List[Dict]) -> Dict[int, str]:
    """게시글 배치를 한 번의 API 호출로 분류해 {articleNo: label} 딕셔너리로 반환한다."""
    lines = [f'{p["articleNo"]} | [{p["categoryName"]}] {p["title"]}' for p in batch]
    user_message = "\n".join(lines)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "submit_classification"},
        messages=[{"role": "user", "content": user_message}],
    )

    result: Dict[int, str] = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_classification":
            for item in block.input.get("classifications", []):
                article_no = item.get("articleNo")
                label = item.get("label")
                if label not in LABELS:
                    label = REVIEW_LABEL
                result[article_no] = label
    return result


def run() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("오류: ANTHROPIC_API_KEY 환경변수가 설정되어 있지 않습니다.")
        sys.exit(1)

    client = Anthropic()

    print("=" * 70)
    print("1) 게시글 로드")
    print("=" * 70)
    posts = discover_posts(BOARD_ROOT)
    print(f"총 {len(posts)}개 게시글 로드 완료")

    print()
    print("=" * 70)
    print("2) LLM 분류")
    print("=" * 70)
    batches = chunked(posts, BATCH_SIZE)
    label_by_article_no: Dict[int, str] = {}
    for idx, batch in enumerate(batches, start=1):
        print(f"  배치 {idx}/{len(batches)} ({len(batch)}건) 분류 중...")
        label_by_article_no.update(classify_batch(client, batch))

    missing = [p for p in posts if p["articleNo"] not in label_by_article_no]
    if missing:
        print(f"  ⚠ 라벨을 받지 못한 게시글 {len(missing)}건 -> '{REVIEW_LABEL}'로 처리")
        for p in missing:
            label_by_article_no[p["articleNo"]] = REVIEW_LABEL

    print()
    print("=" * 70)
    print("3) 분류 결과 저장")
    print("=" * 70)
    classification_result = [
        {
            "articleNo": p["articleNo"],
            "folder": p["period_folder"],
            "title": p["title"],
            "label": label_by_article_no[p["articleNo"]],
        }
        for p in posts
    ]
    result_path = BOARD_ROOT / "classification_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(classification_result, f, ensure_ascii=False, indent=2)
    print(f"저장 완료 -> {result_path}")

    print()
    print("=" * 70)
    print("4) 삭제 대상 백업 이동 (취업·진로, 대학원)")
    print("=" * 70)
    removed_count = 0
    for p in posts:
        label = label_by_article_no[p["articleNo"]]
        if label in DELETE_LABELS:
            dest_dir = BOARD_ROOT / "_removed" / p["period_folder"]
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / p["path"].name
            p["path"].rename(dest_path)
            removed_count += 1
    print(f"이동 완료: {removed_count}건 -> {BOARD_ROOT / '_removed'}")

    print()
    print("=" * 70)
    print("5) '기타' 검토 체크리스트 생성")
    print("=" * 70)
    review_posts = [
        p for p in posts if label_by_article_no[p["articleNo"]] == REVIEW_LABEL
    ]
    checklist_path = BOARD_ROOT / "기타_검토_체크리스트.md"
    lines = [
        "# 기타 라벨 검토 체크리스트",
        "",
        "삭제할 게시글 앞의 `[ ]`를 `[x]`로 바꾼 뒤 `apply_review.py`를 실행하세요.",
        "",
        "| 삭제 | articleNo | 폴더 | 제목 |",
        "|---|---|---|---|",
    ]
    for p in review_posts:
        lines.append(
            f"| - [ ] | {p['articleNo']} | {p['period_folder']} | {p['title']} |"
        )
    checklist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"저장 완료 -> {checklist_path} ({len(review_posts)}건)")

    print()
    print("=" * 70)
    print("6) 라벨별 요약")
    print("=" * 70)
    counts: Dict[str, int] = {label: 0 for label in LABELS}
    for label in label_by_article_no.values():
        counts[label] = counts.get(label, 0) + 1
    for label in LABELS:
        marker = " (삭제됨)" if label in DELETE_LABELS else (" (검토 대기)" if label == REVIEW_LABEL else "")
        print(f"  {label:10s} : {counts[label]:4d}건{marker}")
    print(f"  {'합계':10s} : {sum(counts.values()):4d}건")


if __name__ == "__main__":
    run()
