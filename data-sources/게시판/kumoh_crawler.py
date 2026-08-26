# -*- coding: utf-8 -*-
"""
금오공과대학교 공지사항 게시판(sub06_01_01_01.do) 최근 게시글 크롤러
"""
import json
import re
import time

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.kumoh.ac.kr/ko/sub06_01_01_01.do"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kumoh-notice-crawler/1.0"}

N_POSTS = 10  # 최근 몇 건을 수집할지


def fetch(url, params=None):
    resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def get_recent_article_numbers(n):
    """목록 페이지를 offset 0부터 순서대로 읽어 상단 고정(공지) 글을 제외한
    실제 최신 게시글의 articleNo를 n개 모을 때까지 수집한다."""
    article_nos = []
    offset = 0
    while len(article_nos) < n:
        html = fetch(BASE_URL, params={"mode": "list", "articleLimit": 10, "article.offset": offset})
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table tbody tr")
        found_any = False
        for row in rows:
            classes = row.get("class") or []
            if "notice" in classes:
                continue  # 상단 고정 공지는 "최근" 목록에서 제외
            link = row.select_one("td.title a")
            if not link:
                continue
            found_any = True
            m = re.search(r"articleNo=(\d+)", link.get("href", ""))
            if m:
                article_nos.append(m.group(1))
                if len(article_nos) >= n:
                    break
        if not found_any:
            break
        offset += 10
    return article_nos[:n]


def parse_detail(article_no):
    html = fetch(BASE_URL, params={"mode": "view", "articleNo": article_no,
                                    "article.offset": 0, "articleLimit": 10})
    soup = BeautifulSoup(html, "html.parser")

    view = soup.select_one(".board-view")

    category_tag = view.select_one(".title-area .category")
    category = category_tag.get_text(strip=True) if category_tag else None

    title_tag = view.select_one(".title-area h4")
    title = title_tag.get_text(" ", strip=True) if title_tag else None
    if category and title:
        title = title.replace(category, "", 1).strip()

    info = {}
    for dl in view.select(".board-view-information dl"):
        key = dl.select_one("dt").get_text(strip=True)
        val = dl.select_one("dd").get_text(strip=True)
        info[key] = val

    attachments = []
    for a in view.select(".attached-file-wrapper a.file-down-btn"):
        attachments.append({
            "file_name": a.get_text(strip=True),
            "download_url": BASE_URL + a.get("href"),
        })

    content_tag = view.select_one(".board-contents")
    content_text = content_tag.get_text("\n", strip=True) if content_tag else None

    return {
        "article_no": article_no,
        "category": category,
        "title": title,
        "writer": info.get("작성자"),
        "date": info.get("작성일"),
        "views": info.get("조회"),
        "attachments": attachments,
        "content": content_text,
        "url": f"{BASE_URL}?mode=view&articleNo={article_no}",
    }


def main():
    article_nos = get_recent_article_numbers(N_POSTS)
    print(f"수집 대상 articleNo ({len(article_nos)}건): {article_nos}")

    results = []
    for i, no in enumerate(article_nos, 1):
        print(f"[{i}/{len(article_nos)}] articleNo={no} 수집 중...")
        try:
            results.append(parse_detail(no))
        except Exception as e:
            print(f"  실패: {e}")
        time.sleep(0.5)  # 서버 부담 방지용 딜레이

    out_path = "kumoh_notices.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"완료: {len(results)}건을 {out_path} 에 저장했습니다.")


if __name__ == "__main__":
    main()
