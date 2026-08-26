from urllib.parse import parse_qs, urlparse

import httpx
from backend.app.crawling.kumoh import KumohBoardCrawler

LIST_HTML = """
<html><body>
  <a href="/cs/sub0601.do?article.offset=0&amp;articleLimit=10&amp;articleNo=123&amp;mode=view">
    2026학년도 수강신청 안내
  </a>
</body></html>
"""

DETAIL_HTML = """
<html><body><main>
  <h4>2026학년도 수강신청 안내</h4>
  <div class="board-info">작성자 소프트웨어전공 작성일 2026.02.11</div>
  <div class="board-view-content">
    수강신청은 지정된 기간 안에 통합정보시스템에서 진행합니다.
    자세한 일정은 첨부 문서를 확인하세요.
  </div>
  <a href="/files/registration.pdf">수강신청 안내.pdf</a>
</main></body></html>
"""


def test_crawl_parses_list_and_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        article_no = parse_qs(urlparse(str(request.url)).query).get("articleNo")
        return httpx.Response(200, text=DETAIL_HTML if article_no else LIST_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    crawler = KumohBoardCrawler(delay_seconds=0, client=client)

    posts = crawler.crawl(1)

    assert len(posts) == 1
    assert posts[0].id == "123"
    assert posts[0].title == "2026학년도 수강신청 안내"
    assert posts[0].published_at == "2026-02-11"
    assert posts[0].attachments[0].name == "수강신청 안내.pdf"


def test_detail_link_is_canonicalized_by_article_number() -> None:
    links = KumohBoardCrawler._detail_links(LIST_HTML, KumohBoardCrawler.base_url)

    assert links == [
        "https://cs.kumoh.ac.kr/cs/sub0601.do?mode=view&articleNo=123"
    ]
