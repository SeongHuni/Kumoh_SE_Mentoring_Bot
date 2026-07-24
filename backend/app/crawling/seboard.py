from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.app.crawling.common import clean_text, extract_attachments, extract_date, select_text
from backend.app.domain import BoardPost


class SeBoardCrawler:
    base_url = "https://seboard.site/"

    def __init__(
        self,
        *,
        api_url: str | None = None,
        delay_seconds: float = 1.0,
        timeout_seconds: float = 20.0,
        headless: bool = True,
    ) -> None:
        self.api_url = api_url
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.headless = headless

    @staticmethod
    def _items(payload: object) -> list[dict[str, object]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("content", "items", "posts", "articles", "results", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, dict):
                    nested = SeBoardCrawler._items(value)
                    if nested:
                        return nested
        return []

    @staticmethod
    def _first(item: dict[str, object], keys: Iterable[str]) -> str:
        for key in keys:
            value = item.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _from_api_item(self, item: dict[str, object]) -> BoardPost | None:
        post_id = self._first(item, ("id", "postId", "articleNo", "seq", "uuid"))
        title = self._first(item, ("title", "subject", "name"))
        content = self._first(item, ("content", "body", "text", "description"))
        if not post_id or not title or not content:
            return None
        item_url = self._first(item, ("url", "link", "href"))
        url = (
            urljoin(self.base_url, item_url)
            if item_url
            else urljoin(self.base_url, f"posts/{post_id}")
        )
        date = self._first(item, ("createdAt", "created_at", "publishedAt", "date", "regDate"))
        llm_category = self._first(item, ("llm_category", "llmCategory"))
        return BoardPost(
            id=post_id,
            source="seboard",
            title=clean_text(title),
            content=clean_text(BeautifulSoup(content, "html.parser").get_text(" ", strip=True)),
            author=self._first(item, ("author", "writer", "nickname", "userName")),
            published_at=extract_date(date),
            url=url,
            llm_category=llm_category or None,
        )

    def _crawl_api(self, limit: int) -> list[BoardPost]:
        assert self.api_url
        posts: list[BoardPost] = []
        page = 0
        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "SE-MentorBot-Prototype/1.0 (educational project)"},
        ) as client:
            while len(posts) < limit:
                response = client.get(self.api_url, params={"page": page, "size": min(50, limit)})
                response.raise_for_status()
                try:
                    payload = response.json()
                except json.JSONDecodeError as exc:
                    raise RuntimeError("SEBOARD_API_URL이 JSON을 반환하지 않습니다.") from exc
                items = self._items(payload)
                if not items:
                    break
                before = len(posts)
                for item in items:
                    post = self._from_api_item(item)
                    if post and all(existing.id != post.id for existing in posts):
                        posts.append(post)
                        if len(posts) >= limit:
                            break
                if len(posts) == before or len(items) < min(50, limit):
                    break
                page += 1
                if self.delay_seconds:
                    time.sleep(self.delay_seconds)
        return posts

    @staticmethod
    def _candidate_links(html: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[tuple[int, str, str]] = []
        seen: set[str] = set()
        excluded = ("login", "signup", "register", "about", "privacy", "terms")
        for anchor in soup.select("a[href]"):
            url = urljoin(SeBoardCrawler.base_url, str(anchor.get("href", "")))
            parsed = urlparse(url)
            if parsed.netloc != urlparse(SeBoardCrawler.base_url).netloc:
                continue
            text = clean_text(anchor.get_text(" ", strip=True))
            lowered = url.lower()
            is_home = url.rstrip("/") == SeBoardCrawler.base_url.rstrip("/")
            if is_home or any(item in lowered for item in excluded):
                continue
            score = 0
            if re.search(r"post|board|article|view|detail", lowered):
                score += 3
            if re.search(r"\d{2,}", lowered):
                score += 2
            if len(text) >= 6:
                score += 1
            if score >= 2 and url not in seen:
                seen.add(url)
                candidates.append((score, url, text))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [(url, text) for _, url, text in candidates]

    @staticmethod
    def _parse_rendered_detail(html: str, url: str, fallback_title: str) -> BoardPost | None:
        soup = BeautifulSoup(html, "html.parser")
        title = select_text(
            soup,
            ("article h1", "main h1", ".post-title", ".board-title", "article h2", "main h2"),
        ) or fallback_title
        content = select_text(
            soup,
            (
                "article .post-content",
                "article .content",
                ".post-content",
                ".board-content",
                ".article-content",
                "article",
                "main",
            ),
        )
        if not title or len(content) < 40:
            return None
        parsed = urlparse(url)
        post_id_match = re.findall(r"[\w-]+", parsed.path.rstrip("/").rsplit("/", 1)[-1])
        post_id = post_id_match[-1] if post_id_match else url
        page_text = clean_text(soup.get_text(" ", strip=True))
        return BoardPost(
            id=post_id,
            source="seboard",
            title=title,
            content=content,
            published_at=extract_date(page_text),
            url=url,
            attachments=extract_attachments(soup, url),
        )

    def _crawl_selenium(self, limit: int) -> list[BoardPost]:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise RuntimeError(
                "Selenium이 설치되지 않았습니다. requirements.txt를 설치해 주세요."
            ) from exc

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1440,1200")
        options.add_argument(
            "--user-agent=SE-MentorBot-Prototype/1.0 (educational project; public pages only)"
        )
        driver = webdriver.Chrome(options=options)
        posts: list[BoardPost] = []
        try:
            driver.get(self.base_url)
            WebDriverWait(driver, self.timeout_seconds).until(
                lambda current: current.execute_script("return document.readyState") == "complete"
            )
            for _ in range(8):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(max(0.5, self.delay_seconds))
            links = self._candidate_links(driver.page_source)
            if not links:
                raise RuntimeError(
                    "SE 게시글 링크를 찾지 못했습니다. 공개 API 주소를 "
                    "SEBOARD_API_URL에 지정하거나 "
                    "사이트 선택자를 갱신해 주세요."
                )
            for url, fallback_title in links:
                if len(posts) >= limit:
                    break
                driver.get(url)
                WebDriverWait(driver, self.timeout_seconds).until(
                    lambda current: current.execute_script("return document.readyState")
                    == "complete"
                )
                time.sleep(max(0.5, self.delay_seconds))
                post = self._parse_rendered_detail(
                    driver.page_source, driver.current_url, fallback_title
                )
                if post and all(existing.url != post.url for existing in posts):
                    posts.append(post)
        finally:
            driver.quit()
        return posts

    def crawl(self, limit: int) -> list[BoardPost]:
        if limit <= 0:
            return []
        posts = self._crawl_api(limit) if self.api_url else self._crawl_selenium(limit)
        if not posts:
            raise RuntimeError("SE 게시판에서 유효한 공개 게시글을 수집하지 못했습니다.")
        return posts
