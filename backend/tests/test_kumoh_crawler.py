from datetime import date
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from backend.app.crawling.kumoh import KumohBoardCrawler

LIST_HTML = """
<html><body>
  <a href="/cs/sub0101.do?article.offset=0&amp;articleLimit=10&amp;articleNo=123&amp;mode=view">
    전공소개
  </a>
</body></html>
"""

DETAIL_HTML = """
<html><body><main>
  <h4>전공소개</h4>
  <div class="board-info">작성자 소프트웨어전공 작성일 2026.02.11</div>
  <div class="board-view-content">
    소프트웨어전공의 교육 목표와 학습 내용을 소개합니다.
    자세한 내용은 원문을 확인하세요.
  </div>
  <a href="/files/introduction.pdf">전공소개.pdf</a>
</main></body></html>
"""


def test_crawl_parses_list_and_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        article_no = parse_qs(urlparse(str(request.url)).query).get("articleNo")
        return httpx.Response(200, text=DETAIL_HTML if article_no else LIST_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    crawler = KumohBoardCrawler(
        delay_seconds=0,
        client=client,
        base_url="https://cs.kumoh.ac.kr/cs/sub0101.do",
    )

    posts = crawler.crawl(1)

    assert len(posts) == 1
    assert posts[0].id == "123"
    assert posts[0].title == "전공소개"
    assert posts[0].published_at == "2026-02-11"
    assert posts[0].attachments[0].name == "전공소개.pdf"


def test_detail_link_is_canonicalized_by_article_number() -> None:
    links = KumohBoardCrawler._detail_links(
        LIST_HTML,
        "https://cs.kumoh.ac.kr/cs/sub0101.do",
    )

    assert links == [
        "https://cs.kumoh.ac.kr/cs/sub0101.do?mode=view&articleNo=123"
    ]


def test_department_notice_board_is_rejected_by_policy() -> None:
    with pytest.raises(ValueError, match="공지사항"):
        KumohBoardCrawler(
            delay_seconds=0,
            base_url="https://cs.kumoh.ac.kr/cs/sub0601.do",
        )


def test_community_job_board_is_rejected_by_allowlist_policy() -> None:
    with pytest.raises(ValueError, match="수집 범위"):
        KumohBoardCrawler(
            delay_seconds=0,
            base_url="https://cs.kumoh.ac.kr/cs/sub0602.do",
        )


def test_university_academic_guidance_site_is_rejected_by_policy() -> None:
    with pytest.raises(ValueError, match="학사안내"):
        KumohBoardCrawler(
            delay_seconds=0,
            base_url="https://www.kumoh.ac.kr/ko/sub06_01_01_01.do",
        )


def test_detail_links_skip_academic_guidance_site() -> None:
    html = """
    <a href="https://www.kumoh.ac.kr/ko/sub06_01_01_01.do?mode=view&amp;articleNo=123">
      학사안내
    </a>
    """

    assert KumohBoardCrawler._detail_links(
        html,
        "https://cs.kumoh.ac.kr/cs/sub0101.do",
    ) == []


def test_crawl_filters_posts_before_the_requested_date() -> None:
    current_list = """
    <html><body>
      <a href="?mode=view&amp;articleNo=124">current</a>
    </body></html>
    """
    older_list = """
    <html><body>
      <a href="?mode=view&amp;articleNo=123">older</a>
    </body></html>
    """
    current_detail = DETAIL_HTML.replace("2026.02.11", "2024.01.01")
    older_detail = DETAIL_HTML.replace("2026.02.11", "2023.12.31")

    requested_offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(urlparse(str(request.url)).query)
        if article_no := params.get("articleNo"):
            return httpx.Response(
                200,
                text=current_detail if article_no == ["124"] else older_detail,
            )
        requested_offsets.append(params["article.offset"][0])
        return httpx.Response(
            200,
            text=current_list if params.get("article.offset") == ["0"] else older_list,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    crawler = KumohBoardCrawler(
        delay_seconds=0,
        client=client,
        base_url="https://cs.kumoh.ac.kr/cs/sub0101.do",
    )

    posts = crawler.crawl(None, published_from=date(2024, 1, 1))

    assert [post.id for post in posts] == ["124"]
    assert requested_offsets == ["0", "10"]


def test_crawler_uses_the_requested_board_url() -> None:
    crawler = KumohBoardCrawler(
        delay_seconds=0,
        base_url="https://cs.kumoh.ac.kr/cs/sub0105_2.do",
    )

    assert crawler._list_url(20).startswith(
        "https://cs.kumoh.ac.kr/cs/sub0105_2.do?"
    )
