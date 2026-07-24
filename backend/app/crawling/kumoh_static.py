from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Literal

import httpx
from bs4 import BeautifulSoup, Tag

from backend.app.crawling.common import clean_text
from backend.app.crawling.kumoh_policy import ensure_kumoh_collection_allowed
from backend.app.crawling.semantic_dedup import remove_semantic_duplicates
from backend.app.domain import BoardPost


@dataclass(frozen=True)
class StaticPage:
    id: str
    title: str
    url: str
    section_headings: tuple[str, ...] | None = None
    semantic_reference_ids: tuple[str, ...] = ()
    document_type: Literal["static", "historical"] = "static"
    content_selector: str | None = None
    content_kind: Literal["standard", "club_introductions"] = "standard"


KUMOH_STATIC_PAGES: tuple[StaticPage, ...] = (
    StaticPage(
        id="static-department-introduction",
        title="소프트웨어전공 소개",
        url="https://cs.kumoh.ac.kr/cs/sub0101.do",
        section_headings=("전공소개",),
        semantic_reference_ids=(
            "static-education-objectives",
            "static-curriculum",
        ),
    ),
    StaticPage(
        id="static-education-objectives",
        title="소프트웨어전공 교육목표",
        url="https://cs.kumoh.ac.kr/cs/sub0102.do",
    ),
    StaticPage(
        id="static-curriculum",
        title="소프트웨어전공 교육과정",
        url="https://cs.kumoh.ac.kr/cs/sub0105_2.do",
    ),
    StaticPage(
        id="static-career",
        title="소프트웨어전공 졸업 후 진로",
        url="https://cs.kumoh.ac.kr/cs/sub0104.do",
        document_type="historical",
    ),
    StaticPage(
        id="static-faculty",
        title="소프트웨어전공 교수진",
        url="https://cs.kumoh.ac.kr/cs/sub0401.do",
        content_selector="#jwxe_main_content .professors-wrapper",
    ),
    StaticPage(
        id="static-clubs",
        title="소프트웨어전공 동아리 소개",
        url="https://cs.kumoh.ac.kr/cs/sub0504.do",
        content_kind="club_introductions",
    ),
)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+82[-\s]?)?0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
_CONTACT_LABEL = re.compile(
    r"(?:연락처|전화(?:번호)?|휴대(?:전화)?|이메일|e-?mail)\s*[:：]?\s*",
    re.IGNORECASE,
)


class KumohStaticCrawler:
    def __init__(
        self,
        *,
        delay_seconds: float = 1.0,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
        pages: tuple[StaticPage, ...] = KUMOH_STATIC_PAGES,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.pages = pages
        for page in self.pages:
            ensure_kumoh_collection_allowed(page.url)
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "SE-MentorBot-Prototype/1.0 (educational project; polite crawler)"
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    @staticmethod
    def _content_nodes(soup: BeautifulSoup, page: StaticPage) -> list[Tag]:
        if page.content_selector:
            selected = [
                node for node in soup.select(page.content_selector) if isinstance(node, Tag)
            ]
            if selected:
                return selected
        main = soup.select_one("#jwxe_main_content")
        if isinstance(main, Tag):
            if page.section_headings:
                sections = [
                    node
                    for node in main.find_all(class_="contents-area", recursive=False)
                    if isinstance(node, Tag)
                    and (
                        heading := node.select_one("h2, h3, h4, h5")
                    ) is not None
                    and clean_text(heading.get_text(" ", strip=True))
                    in page.section_headings
                ]
                if sections:
                    return sections
                raise ValueError(f"허용된 정적 안내 섹션을 찾지 못했습니다: {page.url}")
            direct_content = [
                node
                for node in main.find_all(class_="contents-area", recursive=False)
                if isinstance(node, Tag)
            ]
            if direct_content:
                return direct_content
            return [main]

        for selector in (".contents-area", "main", "article"):
            nodes = [node for node in soup.select(selector) if isinstance(node, Tag)]
            if nodes:
                return nodes
        return []

    @staticmethod
    def _clean_static_content(nodes: list[Tag]) -> str:
        lines: list[str] = []
        for node in nodes:
            for raw_line in node.get_text("\n", strip=True).splitlines():
                line = _EMAIL.sub("", raw_line)
                line = _PHONE.sub("", line)
                line = _CONTACT_LABEL.sub("", line)
                cleaned = clean_text(line).strip(" -,:：")
                if cleaned:
                    lines.append(cleaned)
        return "\n".join(lines)

    @classmethod
    def _club_introductions(cls, soup: BeautifulSoup, page: StaticPage) -> str:
        main = soup.select_one("#jwxe_main_content")
        if not isinstance(main, Tag):
            raise ValueError(f"정적 안내 본문을 찾지 못했습니다: {page.url}")

        descriptions: list[str] = []
        for block in main.find_all(class_="contents-area", recursive=False):
            if not isinstance(block, Tag):
                continue
            heading = block.select_one("h4")
            club_name = clean_text(heading.get_text(" ", strip=True)) if heading else ""
            introduction: Tag | None = None
            for label in block.select("th"):
                if clean_text(label.get_text(" ", strip=True)) == "동아리 소개":
                    sibling = label.find_next_sibling("td")
                    if isinstance(sibling, Tag):
                        introduction = sibling
                    break
            if not club_name or introduction is None:
                continue
            description = cls._clean_static_content([introduction])
            if description:
                descriptions.append(
                    f"동아리명: {club_name}\n동아리 소개: {description}"
                )

        if not descriptions:
            raise ValueError(f"동아리 소개 본문을 찾지 못했습니다: {page.url}")
        return "\n\n".join(descriptions)

    @classmethod
    def parse_page(cls, html: str, page: StaticPage) -> BoardPost:
        soup = BeautifulSoup(html, "html.parser")
        if page.content_kind == "club_introductions":
            content = cls._club_introductions(soup, page)
        else:
            if page.id == "static-faculty":
                for heading in soup.select("#jwxe_main_content h3, #jwxe_main_content h4"):
                    heading.decompose()
            content = cls._clean_static_content(cls._content_nodes(soup, page))
        if len(content) < 20:
            raise ValueError(f"정적 안내 본문을 찾지 못했습니다: {page.url}")
        return BoardPost(
            id=page.id,
            source="kumoh",
            title=page.title,
            content=content,
            author="금오공과대학교 컴퓨터공학부 소프트웨어전공",
            published_at=None,
            url=page.url,
            document_type=page.document_type,
        )

    def _deduplicate_semantic_content(self, posts: list[BoardPost]) -> list[BoardPost]:
        posts_by_id = {post.id: post for post in posts}
        pages_by_id = {page.id: page for page in self.pages}
        cleaned_posts: list[BoardPost] = []
        for post in posts:
            page = pages_by_id[post.id]
            references = [
                posts_by_id[reference_id].content
                for reference_id in page.semantic_reference_ids
                if reference_id in posts_by_id
            ]
            if references:
                post = post.model_copy(
                    update={
                        "content": remove_semantic_duplicates(post.content, references)
                    }
                )
            cleaned_posts.append(post)
        return cleaned_posts

    def crawl(self) -> list[BoardPost]:
        posts: list[BoardPost] = []
        try:
            for index, page in enumerate(self.pages):
                response = self.client.get(page.url)
                response.raise_for_status()
                posts.append(self.parse_page(response.text, page))
                if self.delay_seconds and index < len(self.pages) - 1:
                    time.sleep(self.delay_seconds)
        finally:
            self.close()
        return self._deduplicate_semantic_content(posts)
