from __future__ import annotations

import json
from pathlib import Path

from backend.app.domain import BoardPost


def deduplicate_posts(posts: list[BoardPost]) -> list[BoardPost]:
    unique: dict[tuple[str, str], BoardPost] = {}
    seen_urls: set[str] = set()
    for post in posts:
        key = (post.source, post.id)
        if key in unique or post.url in seen_urls:
            continue
        unique[key] = post
        seen_urls.add(post.url)
    return list(unique.values())


def save_posts(posts: list[BoardPost], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [post.model_dump(mode="json") for post in deduplicate_posts(posts)]
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def load_posts(path: Path) -> list[BoardPost]:
    if not path.exists():
        raise FileNotFoundError(f"게시글 데이터 파일이 없습니다: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("게시글 데이터는 JSON 배열이어야 합니다.")
    return [BoardPost.model_validate(item) for item in payload]
