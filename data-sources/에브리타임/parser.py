"""에브리타임 강의평가 HTML(article.html, overview.html)을 과목별 JSON으로 변환하는 스크립트.

==============================================================================
실제 확인한 HTML 구조 (2026-07-21, html/인공지능_김영우/article.html 기준)
==============================================================================
article.html은 <head>/<body> 없이 아래 조각으로만 저장되어 있었음
(BeautifulSoup는 head/body 없이도 문제없이 파싱 가능):

    <div class="articles">
      <div class="article">
        <div class="article_header">
          <div class="title">
            <div class="rate">
              <span class="star"><span class="on" style="width: 100%;"></span></span>
            </div>
            <div class="info">
              <span class="semester">25년 1학기 수강자</span>
            </div>
          </div>
          <div class="buttons">
            <button class="posvote">추천</button>   <!-- 숫자가 있으면 "추천 N" 형태로 추정 -->
            <button>신고</button>                    <!-- class 없음, 데이터 아님 -->
          </div>
        </div>
        <div class="text">리뷰 본문...</div>
      </div>
      ...
    </div>

- 별점: span.star > span.on 의 style="width:N%" (N은 20% 단위, 0~100)
- 추천수: button.posvote 의 텍스트. 숫자가 없으면(예: "추천") 0으로 간주
- 신고 버튼은 class가 없고 데이터가 아니므로 무시

==============================================================================
실제 확인한 HTML 구조 (2026-07-22, 에브리타임 "자료구조/이현아" 강의실 라이브 페이지
document.querySelector("body > div:nth-child(1) > div > div.pane > div > section.review")
기준 — 사용자가 직접 지목해준 컨테이너)
==============================================================================
overview.html에 해당하는 정보는 강의실 상세 페이지(개요 탭)의 section.review 안에 있다.

    section.review
      div.rating
        div.title
          span.average          -> "4.42"
          span.star > span.on   -> style="width:N%" (전체 평균 별점, 참고용)
          span.count            -> "(36개)" 형태, 총 리뷰 개수
        div.rates
          div.rate (5개, 5점~1점 순서)
            span.value(.winner)   -> 별점 숫자 ("5".."1"), 최빈값이면 winner 클래스 추가
            div.bar > div.gauge
            div.vote(.winner)     -> "78%" 형태의 비율, 최빈값이면 winner 클래스 추가
      div.assessment
        div.detail.subjective (과제 / 조모임 / 성적, 3개)
          h3                     -> 제목 텍스트 ("과제"/"조모임"/"성적")
          div.items > div.item (3개, 각 항목 안에)
            div.bar > div.[positive|neutral|negative](.winner).gauge
            div.[positive|neutral|negative](.winner).vote  -> "78%" 형태
          -> positive/neutral/negative 는 각각 (없음/보통/많음) 또는
             (너그러움/보통/깐깐함)에 대응. winner 클래스가 붙은 쪽이 최빈값.
        div.detail.objective (출결 / 시험, 2개)
          h3                     -> "출결" / "시험"
          div.options > span(.majority) -> 선택된(표시된) 값. majority 클래스 없는
             span은 후보일 뿐 실제 값 아님 (출결은 3개 후보 중 majority 1개,
             시험은 후보 1개뿐이라 그게 곧 majority)
      div.articles  (미리보기 리뷰 2개 + "강의평 더 보기" 링크 — 전체 리뷰 아님,
                     전체 리뷰는 "강의평" 탭(article.html에 해당)에 별도로 있음)

   위 구조는 실제 라이브 DOM을 스크립트로 순회해 확인한 것이며, 저장된 정적
   overview.html 파일로 재확인한 것은 아니다. 실제 저장 파일이 생기면 class명이
   동일한지 한 번 더 대조할 것.
==============================================================================
"""

import json
import math
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass  # 콘솔이 재구성을 지원하지 않으면 기본 인코딩 유지 (파일 출력은 영향 없음)

HTML_ROOT = Path("html")
OUTPUT_ROOT = Path("data")

RATING_DEVIATION_THRESHOLD = 5  # 별점 분포 5개 합이 100에서 이 이상 벗어나면 경고

# div.assessment > div.detail.subjective 의 h3 제목 -> (positive, neutral, negative) 라벨
SUBJECTIVE_LABELS: Dict[str, Tuple[str, str, str]] = {
    "과제": ("없음", "보통", "많음"),
    "조모임": ("없음", "보통", "많음"),
    "성적": ("너그러움", "보통", "깐깐함"),
}
POLARITY_ORDER: Tuple[str, str, str] = ("positive", "neutral", "negative")


# ==============================================================================
# 공통 유틸
# ==============================================================================

def clean_text(text: Optional[str]) -> str:
    """공백(줄바꿈, NBSP 포함)을 정리해 하나의 공백으로 축약하고 앞뒤를 자른다."""
    if text is None:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sanitize_filename(name: str) -> str:
    """Windows에서 금지된 파일명 문자(\\ / : * ? " < > |)를 전부 밑줄로 치환한다."""
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def read_html(path: Path) -> BeautifulSoup:
    """HTML 파일을 읽어 BeautifulSoup 객체로 반환한다."""
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    return BeautifulSoup(html, "html.parser")


def extract_number(text: Optional[str]) -> int:
    """문자열에서 첫 번째로 나오는 숫자를 추출한다. 없으면 0을 반환한다."""
    if text is None:
        return 0
    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    return 0


def style_width_to_rating(style: Optional[str]) -> int:
    """style="width:N%" 형태의 문자열을 1~5 별점으로 변환한다.

    은행가 반올림(round)이 아닌 일반적인 사사오입을 사용한다.
    (width=50%일 때 round()는 2.5->2로 잘못 내림할 수 있어 floor(x+0.5) 사용)
    """
    if style is None:
        return 0
    m = re.search(r"width\s*:\s*([\d.]+)%", style)
    if m is None:
        return 0
    width = float(m.group(1))
    return math.floor(width / 20 + 0.5)


# ==============================================================================
# 과목 폴더 탐색
# ==============================================================================

def discover_course_folders(html_root: Path) -> List[Path]:
    """html_root 아래의 과목 폴더(html/{과목명}_{교수명}/) 목록을 정렬해 반환한다."""
    if not html_root.exists():
        return []
    return sorted(p for p in html_root.iterdir() if p.is_dir())


def parse_course_professor(folder_name: str) -> Tuple[str, str]:
    """폴더명 "{과목명}_{교수명}"을 과목명과 교수명으로 분리한다.

    마지막 밑줄을 기준으로 나눈다 (과목명 자체에 밑줄이 들어갈 가능성은 낮다고 가정).
    """
    if "_" not in folder_name:
        raise ValueError(
            f'폴더명 "{folder_name}"이 "{{과목명}}_{{교수명}}" 형식이 아닙니다.'
        )
    course_name, professor = folder_name.rsplit("_", 1)
    course_name = course_name.strip()
    professor = professor.strip()
    if not course_name or not professor:
        raise ValueError(
            f'폴더명 "{folder_name}"에서 과목명 또는 교수명을 추출할 수 없습니다.'
        )
    return course_name, professor


# ==============================================================================
# article.html 파서 (리뷰 목록)
# ==============================================================================

def parse_article_html(
    article_path: Path, course_name: str, professor: str
) -> List[Dict]:
    """article.html에서 리뷰 목록을 추출한다.

    본문이 비어있는 리뷰는 결과에서 제외한다.
    id는 "{과목명}_{교수명}_{순번}" 형태로, 여러 과목을 합쳐도 겹치지 않게 만든다.
    """
    soup = read_html(article_path)
    reviews: List[Dict] = []
    seq = 1

    for article in soup.select(".article"):
        star = article.select_one(".star .on")
        rating = style_width_to_rating(star.get("style") if star else None)

        semester_node = article.select_one(".semester")
        semester = clean_text(semester_node.get_text()) if semester_node else ""

        posvote_node = article.select_one(".posvote")
        likes = extract_number(posvote_node.get_text()) if posvote_node else 0

        text_node = article.select_one(".text")
        content = ""
        if text_node is not None:
            content = text_node.get_text("\n")
            content = re.sub(r"\n+", "\n", content).strip()

        if len(content) == 0:
            continue

        reviews.append(
            {
                "id": f"{course_name}_{professor}_{seq}",
                "rating": rating,
                "semester": semester,
                "likes": likes,
                "content": content,
            }
        )
        seq += 1

    return reviews


# ==============================================================================
# overview.html 파서 (강의 개요, section.review 기준)
# ==============================================================================

def empty_overview_fields() -> Dict:
    """overview.html이 없거나 section.review를 찾지 못했을 때 채울 기본값."""
    return {
        "average_rating": None,
        "review_count": None,
        "rating_distribution": None,
        "assignment": None,
        "assignment_distribution": None,
        "group_project": None,
        "group_project_distribution": None,
        "grading": None,
        "grading_distribution": None,
        "attendance": None,
        "exam": None,
    }


def parse_rating_distribution(review_root) -> Optional[Dict[str, int]]:
    """div.rating .rates .rate 5개에서 별점별 비율(%)을 추출한다."""
    distribution: Dict[str, int] = {}
    for rate in review_root.select(".rating .rates .rate"):
        value_node = rate.select_one(".value")
        vote_node = rate.select_one(".vote")
        if value_node is None or vote_node is None:
            continue
        star = clean_text(value_node.get_text())
        distribution[star] = extract_number(vote_node.get_text())
    return distribution if distribution else None


def parse_subjective_detail(detail) -> Tuple[str, Optional[str], Optional[Dict[str, int]]]:
    """div.detail.subjective 하나(과제/조모임/성적)에서 (제목, 최빈값, 분포)를 추출한다."""
    h3 = detail.select_one("h3")
    title = clean_text(h3.get_text()) if h3 else ""
    labels = SUBJECTIVE_LABELS.get(title)
    if labels is None:
        return title, None, None

    distribution: Dict[str, int] = {}
    winner_label: Optional[str] = None

    for item in detail.select(".items .item"):
        vote_node = item.select_one(".vote")
        if vote_node is None:
            continue
        classes = vote_node.get("class", [])
        polarity = next((p for p in POLARITY_ORDER if p in classes), None)
        if polarity is None:
            continue
        label = labels[POLARITY_ORDER.index(polarity)]
        distribution[label] = extract_number(vote_node.get_text())
        if "winner" in classes:
            winner_label = label

    ordered_distribution = {label: distribution.get(label, 0) for label in labels}
    return title, winner_label, ordered_distribution


def parse_objective_detail(detail) -> Tuple[str, Optional[str]]:
    """div.detail.objective 하나(출결/시험)에서 (제목, 선택된 값)을 추출한다."""
    h3 = detail.select_one("h3")
    title = clean_text(h3.get_text()) if h3 else ""
    majority_node = detail.select_one(".options .majority")
    value = clean_text(majority_node.get_text()) if majority_node else None
    return title, value


def parse_overview_html(overview_path: Optional[Path]) -> Dict:
    """overview.html에서 강의 개요 정보를 추출한다 (section.review 기준).

    section.review를 찾지 못하면(파일이 없거나 사이트 구조가 바뀐 경우)
    모든 필드를 None으로 채운 기본값을 반환한다.
    """
    fields = empty_overview_fields()

    if overview_path is None or not overview_path.exists():
        return fields

    soup = read_html(overview_path)
    review_root = soup.select_one("section.review")
    if review_root is None:
        return fields

    average_node = review_root.select_one(".rating .title .average")
    if average_node is not None:
        try:
            fields["average_rating"] = float(clean_text(average_node.get_text()))
        except (ValueError, TypeError):
            fields["average_rating"] = None

    count_node = review_root.select_one(".rating .title .count")
    if count_node is not None:
        fields["review_count"] = extract_number(count_node.get_text())

    fields["rating_distribution"] = parse_rating_distribution(review_root)

    for detail in review_root.select(".assessment .detail.subjective"):
        title, winner_label, distribution = parse_subjective_detail(detail)
        if title == "과제":
            fields["assignment"], fields["assignment_distribution"] = winner_label, distribution
        elif title == "조모임":
            fields["group_project"], fields["group_project_distribution"] = winner_label, distribution
        elif title == "성적":
            fields["grading"], fields["grading_distribution"] = winner_label, distribution

    for detail in review_root.select(".assessment .detail.objective"):
        title, value = parse_objective_detail(detail)
        if title == "출결":
            fields["attendance"] = value
        elif title == "시험":
            fields["exam"] = value

    return fields


# ==============================================================================
# 과목 하나 처리
# ==============================================================================

def process_course(course_folder: Path) -> Tuple[Dict, bool]:
    """과목 폴더 하나를 처리해 최종 JSON dict를 만든다.

    Returns:
        (course_json, overview_parse_failed) 튜플.
        두 번째 값이 True면 overview.html에 내용은 있지만 section.review를 찾지 못해
        (사이트 구조 변경 등으로) 개요 필드가 전부 비어있다는 뜻. 강의평가가 아예
        없어서 overview.html이 빈 파일로 저장된 경우는 실패로 치지 않는다.
    """
    course_name, professor = parse_course_professor(course_folder.name)

    article_path = course_folder / "article.html"
    if not article_path.exists():
        raise FileNotFoundError(f"article.html 없음 ({course_folder})")

    overview_path = course_folder / "overview.html"
    overview_has_content = overview_path.exists() and overview_path.stat().st_size > 0

    course = {
        "name": course_name,
        "professor": professor,
    }
    overview_fields = parse_overview_html(overview_path if overview_has_content else None)
    course.update(overview_fields)

    overview_parse_failed = overview_has_content and overview_fields["average_rating"] is None

    reviews = parse_article_html(article_path, course_name, professor)

    course_json = {
        "source": "Everytime",
        "course": course,
        "reviews": reviews,
    }

    return course_json, overview_parse_failed


def save_course_json(course_json: Dict, output_root: Path) -> Path:
    """과목 JSON을 {과목명}_{교수명}.json 파일로 저장하고 저장 경로를 반환한다."""
    course = course_json["course"]
    filename = sanitize_filename(f"{course['name']}_{course['professor']}.json")
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(course_json, f, ensure_ascii=False, indent=2)
    return output_path


# ==============================================================================
# 사람이 읽기 좋은 출력 (실제 HTML과 대조용)
# ==============================================================================

def print_course_readable(course_json: Dict) -> None:
    """과목 하나의 파싱 결과를 사람이 읽기 좋은 형태로 출력한다."""
    course = course_json["course"]
    reviews = course_json["reviews"]

    print("=" * 70)
    print(f"{course['name']} ({course['professor']})")
    print("-" * 70)
    print(f"평균 평점 : {course['average_rating']}")
    print(f"리뷰 수   : {course['review_count']}")
    print(f"별점 분포 : {course['rating_distribution']}")
    print(f"과제      : {course['assignment']} {course['assignment_distribution']}")
    print(f"조모임    : {course['group_project']} {course['group_project_distribution']}")
    print(f"성적      : {course['grading']} {course['grading_distribution']}")
    print(f"출결      : {course['attendance']}")
    print(f"시험      : {course['exam']}")
    print(f"-- 리뷰 {len(reviews)}건 (최대 5건 표시) --")
    for review in reviews[:5]:
        stars = "★" * review["rating"] + "☆" * (5 - review["rating"])
        print(f"  [{review['id']}] {stars} | {review['semester']} | 추천 {review['likes']}")
        print(f"    {review['content'][:120]}")
    print("=" * 70)


# ==============================================================================
# 실행 후 결과 검증
# ==============================================================================

def run_post_checks(all_course_jsons: List[Dict], total_folders: int) -> None:
    """파싱 결과 전체를 훑어 의심스러운 과목들을 콘솔에 정리해 보여준다."""
    print()
    print("=" * 70)
    print("결과 검증")
    print("=" * 70)

    success = len(all_course_jsons)
    rate = (success / total_folders * 100) if total_folders else 0.0
    print(f"1) 파싱 성공률 : {success}/{total_folders} ({rate:.1f}%)")

    no_rating = [
        cj["course"]["name"]
        for cj in all_course_jsons
        if not cj["course"]["average_rating"]
    ]
    print(f"2) 평균 평점 None/0 의심 과목 ({len(no_rating)}개) : {no_rating}")

    no_reviews = [
        cj["course"]["name"] for cj in all_course_jsons if len(cj["reviews"]) == 0
    ]
    print(f"3) 리뷰 0개 의심 과목 ({len(no_reviews)}개) : {no_reviews}")

    bad_distribution = []
    for cj in all_course_jsons:
        dist = cj["course"]["rating_distribution"]
        if not dist:
            continue
        try:
            total = sum(dist.values())
        except (TypeError, ValueError):
            continue
        if abs(total - 100) > RATING_DEVIATION_THRESHOLD:
            bad_distribution.append((cj["course"]["name"], total))
    print(f"4) 별점 분포 합계 이상 과목 ({len(bad_distribution)}개) : {bad_distribution}")
    print("=" * 70)


# ==============================================================================
# 메인 실행
# ==============================================================================

def run() -> None:
    """html/ 아래 모든 과목 폴더를 순회하며 파싱하고 결과를 요약 출력한다."""
    course_folders = discover_course_folders(HTML_ROOT)

    print("=" * 70)
    print(f"과목 폴더 수 : {len(course_folders)}")
    print("=" * 70)

    success_jsons: List[Dict] = []
    failed: List[Dict] = []
    overview_warnings: List[str] = []

    for idx, folder in enumerate(course_folders, start=1):
        print(f"\n[{idx}/{len(course_folders)}] {folder.name}")
        try:
            course_json, overview_unparsed = process_course(folder)
        except (FileNotFoundError, ValueError) as e:
            print(f"실패 : {e}")
            failed.append({"course": folder.name, "error": str(e)})
            continue

        save_path = save_course_json(course_json, OUTPUT_ROOT)
        print(f"완료 -> {save_path} (리뷰 {len(course_json['reviews'])}건)")
        success_jsons.append(course_json)

        if overview_unparsed:
            overview_warnings.append(folder.name)
            print("  ⚠ overview.html은 있지만 section.review를 찾지 못했습니다 (사이트 구조 변경 의심).")

    print()
    print("=" * 70)
    print("작업 완료 요약")
    print("=" * 70)
    print(f"총 과목 수 : {len(course_folders)}")
    print(f"성공       : {len(success_jsons)}")
    print(f"실패       : {len(failed)}")
    for cj in success_jsons:
        print(f"  - {cj['course']['name']}({cj['course']['professor']}) : 리뷰 {len(cj['reviews'])}건")

    if failed:
        print()
        print("실패 목록")
        for item in failed:
            print(f"  - {item['course']} : {item['error']}")

    if overview_warnings:
        print()
        print(f"overview.html 파싱 실패 의심 과목 ({len(overview_warnings)}개) : {overview_warnings}")
        print("  -> section.review를 못 찾음. 실제 저장된 overview.html을 열어 구조가 바뀌었는지 확인하세요.")

    if success_jsons:
        print()
        print("=" * 70)
        print("무작위 샘플 (사람이 읽기 좋은 형태, 실제 HTML과 대조용)")
        print("=" * 70)
        sample = random.sample(success_jsons, k=min(3, len(success_jsons)))
        for cj in sample:
            print_course_readable(cj)

    run_post_checks(success_jsons, len(course_folders))


if __name__ == "__main__":
    run()
