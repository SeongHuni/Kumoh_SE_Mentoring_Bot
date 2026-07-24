from __future__ import annotations

import re

from backend.app.domain import BoardPost, TextChunk

WHITESPACE = re.compile(r"[ \t]+")
EXCESS_NEWLINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    lines = [WHITESPACE.sub(" ", line).strip() for line in text.replace("\r", "\n").split("\n")]
    return EXCESS_NEWLINES.sub("\n\n", "\n".join(line for line in lines if line)).strip()


def _find_boundary(text: str, start: int, preferred_end: int) -> int:
    if preferred_end >= len(text):
        return len(text)
    search_start = max(start + 1, preferred_end - 180)
    candidates = [
        text.rfind("\n", search_start, preferred_end),
        text.rfind(". ", search_start, preferred_end),
        text.rfind("다. ", search_start, preferred_end),
        text.rfind(" ", search_start, preferred_end),
    ]
    boundary = max(candidates)
    return preferred_end if boundary <= start else boundary + 1


def chunk_post(post: BoardPost, chunk_size: int = 900, overlap: int = 150) -> list[TextChunk]:
    if chunk_size < 200:
        raise ValueError("chunk_size must be at least 200")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size - 1")

    header = f"제목: {post.title}"
    if post.published_at:
        header += f"\n작성일: {post.published_at}"
    if post.document_type == "historical":
        header += "\n문서 상태: 역사 정보 (현재 수치·현황 아님)"
    text = normalize_text(f"{header}\n본문: {post.content}")
    chunks: list[TextChunk] = []
    start = 0

    while start < len(text):
        end = _find_boundary(text, start, min(len(text), start + chunk_size))
        body = text[start:end].strip()
        if body:
            index = len(chunks)
            chunks.append(
                TextChunk(
                    id=f"{post.source}:{post.id}:{index}",
                    post_id=post.id,
                    source=post.source,
                    title=post.title,
                    text=body,
                    url=post.url,
                    published_at=post.published_at,
                    document_type=post.document_type,
                    chunk_index=index,
                    topic_key=post.topic_key or "general",
                    topic_label=post.topic_label or "전체 공지",
                    is_latest_topic=post.is_latest_topic,
                    intent_key=post.intent_key,
                    category_key=post.category_key or "other",
                    category_label=post.category_label or "기타",
                    notice_kind=post.notice_kind,
                )
            )
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)

    return chunks


def chunk_posts(
    posts: list[BoardPost], chunk_size: int = 900, overlap: int = 150
) -> list[TextChunk]:
    return [
        chunk
        for post in posts
        for chunk in chunk_post(post, chunk_size=chunk_size, overlap=overlap)
    ]
