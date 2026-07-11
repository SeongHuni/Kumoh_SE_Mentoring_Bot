from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from backend.app.crawling.common import clean_text, extract_attachments, extract_date, select_text
from backend.app.domain import BoardPost


class KumohBoardCrawler:
    base_url = "https://cs.kumoh.ac.kr/cs/sub0601.do"

    def __init__(
        self,
        *,
        delay_seconds: float = 1.0,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.delay_seconds = delay_seconds
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

    def _list_url(self, offset: int) -> str:
        params = {"article.offset": offset, "articleLimit": 10, "mode": "list"}
        return f"{self.base_url}?{urlencode(params)}"

    @staticmethod
    def _detail_links(html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []
        seen: set[str] = set()
        for anchor in soup.select("a[href]"):
            url = urljoin(page_url, str(anchor.get("href", "")))
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "articleNo" not in params or params.get("mode") != ["view"]:
                continue
            canonical_query = urlencode(
                {"mode": "view", "articleNo": params["articleNo"][0]}
            )
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{canonical_query}"
            if normalized not in seen:
                seen.add(normalized)
                links.append(normalized)
        return links

    @staticmethod
    def _content_node(soup: BeautifulSoup) -> Tag | None:
        selectors = (
            ".board-contents",
            ".board-view-content",
            ".board_view_content",
            ".view-content",
            ".view_content",
            ".board-view-con",
            ".board_view_con",
            ".article-content",
            ".article_content",
            ".fr-view",
            "article .content",
        )
        for selector in selectors:
            node = soup.select_one(selector)
            if isinstance(node, Tag) and len(clean_text(node.get_text(" ", strip=True))) >= 20:
                return node

        candidates: list[tuple[int, Tag]] = []
        for node in soup.select("main div, article div, td"):
            if not isinstance(node, Tag):
                continue
            classes = " ".join(node.get("class", []))
            marker = f"{node.get('id', '')} {classes}".lower()
            text = clean_text(node.get_text(" ", strip=True))
            if len(text) >= 80 and re.search(r"content|view|board|article|contents", marker):
                candidates.append((len(text), node))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

    @classmethod
    def parse_detail(cls, html: str, url: str) -> BoardPost:
        soup = BeautifulSoup(html, "html.parser")
        title = select_text(
            soup,
            (
                ".board-view-title",
                ".board_view_title",
                ".title-area",
                ".view-title",
                ".view_subject",
                ".subject",
                "article h1",
                "article h2",
                "main h4",
            ),
        )
        content_node = cls._content_node(soup)
        if not content_node:
            raise ValueError(f"게시글 본문을 찾지 못했습니다: {url}")
        content = clean_text(content_node.get_text("\n", strip=True))
        if not title:
            title = select_text(soup, ("h4", "h3", "title"))

        page_text = clean_text(soup.get_text(" ", strip=True))
        author_match = re.search(r"작성자\s*[:：]?\s*([^\s]+)", page_text)
        date_match = re.search(r"작성일\s*[:：]?\s*([^\s]+)", page_text)
        parsed = urlparse(url)
        article_no = parse_qs(parsed.query).get("articleNo", [url])[0]
        return BoardPost(
            id=str(article_no),
            source="kumoh",
            title=title,
            content=content,
            author=author_match.group(1) if author_match else "",
            published_at=extract_date(date_match.group(1) if date_match else page_text),
            url=url,
            attachments=extract_attachments(soup, url),
        )

    def crawl(self, limit: int) -> list[BoardPost]:
        posts: list[BoardPost] = []
        seen_urls: set[str] = set()
        offset = 0
        try:
            while len(posts) < limit:
                page_url = self._list_url(offset)
                response = self.client.get(page_url)
                response.raise_for_status()
                links = [
                    url
                    for url in self._detail_links(response.text, page_url)
                    if url not in seen_urls
                ]
                if not links:
                    break
                for detail_url in links:
                    if len(posts) >= limit:
                        break
                    seen_urls.add(detail_url)
                    try:
                        detail = self.client.get(detail_url)
                        detail.raise_for_status()
                        posts.append(self.parse_detail(detail.text, detail_url))
                    except (httpx.HTTPError, ValueError):
                        # Image-only, removed, or temporarily unavailable posts are not embeddable.
                        pass
                    if self.delay_seconds:
                        time.sleep(self.delay_seconds)
                offset += 10
                if self.delay_seconds:
                    time.sleep(self.delay_seconds)
        finally:
            self.close()
        return posts
