import httpx
import pytest
from backend.app.crawling.kumoh_static import (
    KUMOH_STATIC_PAGES,
    KumohStaticCrawler,
    StaticPage,
)

STATIC_HTML = """
<html><body>
  <main id="jwxe_main_content">
    <div class="board-area">
      <div class="search_box">게시글 검색 검색분류선택 제목 내용 작성자</div>
      <div class="professors-wrapper">
        <h2>교수</h2>
        <h3>김테스트</h3>
        <p>소속 : 컴퓨터공학부 소프트웨어전공</p>
        <p>연락처 : 054-478-7544</p>
        <p>이메일 : faculty@example.com</p>
        <p>전공 : 인공지능, 정보검색</p>
      </div>
    </div>
  </main>
</body></html>
"""

CLUB_HTML = """
<html><body>
  <main id="jwxe_main_content">
    <div class="contents-area">
      <h4>셈틀꾼</h4>
      <div class="half-wrap"><div class="half-cont"><div class="table-type01">
        <table><tbody>
          <tr><th>회장</th><td>홍길동</td></tr>
          <tr><th>동아리 소개</th><td>
            알고리즘 문제 해결과 스터디를 진행합니다. 연락처: 054-478-7544
          </td></tr>
        </tbody></table>
      </div></div></div>
    </div>
    <div class="contents-area">
      <h4>ACM</h4>
      <div class="half-wrap"><div class="half-cont"><div class="table-type01">
        <table><tbody>
          <tr><th>동아리 소개</th><td>프로그래밍과 소프트웨어 개발 활동을 함께 합니다.</td></tr>
        </tbody></table>
      </div></div></div>
    </div>
  </main>
</body></html>
"""

INTRODUCTION_HTML = """
<html><body>
  <main id="jwxe_main_content">
    <div class="contents-area">
      <h4>전공소개</h4>
      <p>소프트웨어 개발에 참여할 실천적인 프로그래머를 양성한다.</p>
      <p>다양한 프로그래밍 언어와 시스템 설계 역량을 기른다.</p>
    </div>
    <div class="contents-area">
      <h4>교육목표</h4>
      <p>소프트웨어 개발에 참여할 실천적인 프로그래머 양성을 교육의 목표로 한다.</p>
    </div>
    <div class="contents-area">
      <h4>주소 및 연락처</h4>
      <p>054-478-7000</p>
    </div>
  </main>
</body></html>
"""

OBJECTIVES_HTML = """
<html><body>
  <main id="jwxe_main_content">
    <div class="contents-area">
      <h4>교육목표</h4>
      <p>소프트웨어 개발에 참여할 실천적인 프로그래머 양성을 교육의 목표로 한다.</p>
      <p>프로젝트 기반 실무 역량을 강화한다.</p>
    </div>
  </main>
</body></html>
"""


def test_static_crawler_uses_content_area_and_removes_contact_details() -> None:
    page = StaticPage(
        id="static-faculty",
        title="소프트웨어전공 교수진",
        url="https://cs.kumoh.ac.kr/cs/sub0401.do",
        content_selector="#jwxe_main_content .professors-wrapper",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == page.url
        return httpx.Response(200, text=STATIC_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    crawler = KumohStaticCrawler(delay_seconds=0, client=client, pages=(page,))

    posts = crawler.crawl()

    assert len(posts) == 1
    assert posts[0].id == "static-faculty"
    assert posts[0].source == "kumoh"
    assert posts[0].title == "소프트웨어전공 교수진"
    assert posts[0].document_type == "static"
    assert posts[0].published_at is None
    assert "김테스트" not in posts[0].content
    assert "인공지능" in posts[0].content
    assert "게시글 검색" not in posts[0].content
    assert "054-478-7544" not in posts[0].content
    assert "faculty@example.com" not in posts[0].content


def test_static_scope_contains_only_allowed_department_pages() -> None:
    urls = {page.url for page in KUMOH_STATIC_PAGES}

    assert urls == {
        "https://cs.kumoh.ac.kr/cs/sub0101.do",
        "https://cs.kumoh.ac.kr/cs/sub0102.do",
        "https://cs.kumoh.ac.kr/cs/sub0105_2.do",
        "https://cs.kumoh.ac.kr/cs/sub0104.do",
        "https://cs.kumoh.ac.kr/cs/sub0401.do",
        "https://cs.kumoh.ac.kr/cs/sub0504.do",
    }

    pages = {page.id: page for page in KUMOH_STATIC_PAGES}
    assert pages["static-department-introduction"].section_headings == ("전공소개",)
    assert pages["static-department-introduction"].semantic_reference_ids == (
        "static-education-objectives",
        "static-curriculum",
    )
    assert pages["static-career"].document_type == "historical"


def test_static_crawler_keeps_intro_section_and_semantically_deduplicates_it() -> None:
    introduction = StaticPage(
        id="static-department-introduction",
        title="소프트웨어전공 소개",
        url="https://cs.kumoh.ac.kr/cs/sub0101.do",
        section_headings=("전공소개",),
        semantic_reference_ids=("static-education-objectives",),
    )
    objectives = StaticPage(
        id="static-education-objectives",
        title="소프트웨어전공 교육목표",
        url="https://cs.kumoh.ac.kr/cs/sub0102.do",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        html = INTRODUCTION_HTML if request.url.path.endswith("sub0101.do") else OBJECTIVES_HTML
        return httpx.Response(200, text=html)

    crawler = KumohStaticCrawler(
        delay_seconds=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        pages=(introduction, objectives),
    )

    posts = {post.id: post for post in crawler.crawl()}

    assert "다양한 프로그래밍 언어와 시스템 설계 역량" in posts[
        "static-department-introduction"
    ].content
    assert "실천적인 프로그래머를 양성한다" not in posts[
        "static-department-introduction"
    ].content
    assert "교육목표" not in posts["static-department-introduction"].content
    assert "주소 및 연락처" not in posts["static-department-introduction"].content
    assert "프로젝트 기반 실무 역량" in posts["static-education-objectives"].content


def test_static_crawler_marks_historical_static_page() -> None:
    page = StaticPage(
        id="static-career",
        title="소프트웨어전공 졸업 후 진로",
        url="https://cs.kumoh.ac.kr/cs/sub0104.do",
        document_type="historical",
    )

    post = KumohStaticCrawler.parse_page(
        "<main id='jwxe_main_content'><p>과거 취업률과 진로 예시를 안내합니다.</p></main>",
        page,
    )

    assert post.document_type == "historical"


def test_static_crawler_keeps_only_club_name_and_introduction() -> None:
    page = StaticPage(
        id="static-clubs",
        title="소프트웨어전공 동아리 소개",
        url="https://cs.kumoh.ac.kr/cs/sub0504.do",
        content_kind="club_introductions",
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=CLUB_HTML)

    crawler = KumohStaticCrawler(
        delay_seconds=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        pages=(page,),
    )

    posts = crawler.crawl()

    assert posts[0].content == (
        "동아리명: 셈틀꾼\n동아리 소개: 알고리즘 문제 해결과 스터디를 진행합니다.\n\n"
        "동아리명: ACM\n동아리 소개: 프로그래밍과 소프트웨어 개발 활동을 함께 합니다."
    )
    assert "홍길동" not in posts[0].content
    assert "회장" not in posts[0].content
    assert "054-478-7544" not in posts[0].content


def test_static_crawler_rejects_university_academic_guidance_pages() -> None:
    page = StaticPage(
        id="academic-guidance",
        title="학사안내",
        url="https://www.kumoh.ac.kr/ko/sub06_01_01_01.do?foo=bar",
    )

    with pytest.raises(ValueError, match="학사안내"):
        KumohStaticCrawler(delay_seconds=0, pages=(page,))


@pytest.mark.parametrize(
    ("page_id", "title", "url"),
    [
        (
            "static-education-objectives",
            "소프트웨어전공 교육목표",
            "https://cs.kumoh.ac.kr/cs/sub0102.do",
        ),
        (
            "static-career",
            "소프트웨어전공 졸업 후 진로",
            "https://cs.kumoh.ac.kr/cs/sub0104.do",
        ),
    ],
)
def test_static_crawler_allows_mentoring_relevant_department_pages(
    page_id: str,
    title: str,
    url: str,
) -> None:
    page = StaticPage(
        id=page_id,
        title=title,
        url=url,
    )

    crawler = KumohStaticCrawler(delay_seconds=0, pages=(page,))

    crawler.close()


def test_static_crawler_rejects_major_achievements_outside_allowlist() -> None:
    page = StaticPage(
        id="static-major-achievements",
        title="소프트웨어전공 주요성과",
        url="https://cs.kumoh.ac.kr/cs/sub0103.do",
    )

    with pytest.raises(ValueError, match="수집 범위"):
        KumohStaticCrawler(delay_seconds=0, pages=(page,))
