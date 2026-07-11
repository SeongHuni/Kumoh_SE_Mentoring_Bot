from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from backend.app.domain import Attachment

SPACE = re.compile(r"\s+")
DATE = re.compile(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})")


def clean_text(value: str) -> str:
    return SPACE.sub(" ", value).strip()


def select_text(soup: BeautifulSoup | Tag, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def extract_date(text: str) -> str | None:
    match = DATE.search(text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def extract_attachments(soup: BeautifulSoup, base_url: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    seen: set[str] = set()
    extensions = (".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".zip")
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href", ""))
        name = clean_text(anchor.get_text(" ", strip=True))
        lowered = f"{href} {name}".lower()
        if not any(extension in lowered for extension in extensions):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        attachments.append(Attachment(name=name or url.rsplit("/", 1)[-1], url=url))
    return attachments
