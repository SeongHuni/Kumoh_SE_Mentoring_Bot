from __future__ import annotations

import re
import time
from datetime import date
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from backend.app.crawling.common import clean_text, extract_attachments, extract_date, select_text
from backend.app.crawling.kumoh_policy import (
    ensure_kumoh_collection_allowed,
    kumoh_collection_exclusion_reason,
)
from backend.app.domain import BoardPost


class KumohBoardCrawler:
    base_url = "https://cs.kumoh.ac.kr/cs/sub0602.do"

    def __init__(
        self,
        *,
        delay_seconds: float = 1.0,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
        base_url: str | None = None,
    ) -> None:
        self.base_url = base_url or type(self).base_url
        ensure_kumoh_collection_allowed(self.base_url)
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
            if kumoh_collection_exclusion_reason(normalized):
                continue
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

    @staticmethod
    def _published_date(post: BoardPost) -> date | None:
        try:
            return date.fromisoformat(post.published_at or "")
        except ValueError:
            return None

    @classmethod
    def _is_in_requested_range(
        cls, post: BoardPost, published_from: date | None
    ) -> bool:
        if published_from is None:
            return True
        published_at = cls._published_date(post)
        return published_at is not None and published_at >= published_from

    def crawl(
        self,
        limit: int | None,
        *,
        published_from: date | None = None,
    ) -> list[BoardPost]:
        posts: list[BoardPost] = []
        seen_urls: set[str] = set()
        offset = 0
        try:
            while limit is None or len(posts) < limit:
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
                page_all_before_requested_range = published_from is not None
                for detail_url in links:
                    if limit is not None and len(posts) >= limit:
                        break
                    seen_urls.add(detail_url)
                    try:
                        detail = self.client.get(detail_url)
                        detail.raise_for_status()
                        post = self.parse_detail(detail.text, detail_url)
                        published_at = self._published_date(post)
                        if (
                            published_from is not None
                            and (published_at is None or published_at >= published_from)
                        ):
                            page_all_before_requested_range = False
                        if self._is_in_requested_range(post, published_from):
                            posts.append(post)
                    except (httpx.HTTPError, ValueError):
                        # Image-only, removed, or temporarily unavailable posts are not embeddable.
                        page_all_before_requested_range = False
                    if self.delay_seconds:
                        time.sleep(self.delay_seconds)
                if page_all_before_requested_range:
                    break
                offset += 10
                if self.delay_seconds:
                    time.sleep(self.delay_seconds)
        finally:
            self.close()
        return posts
