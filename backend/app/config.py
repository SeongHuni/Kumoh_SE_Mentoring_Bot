from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPOSITORY_ROOT / ".env")


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPOSITORY_ROOT / path).resolve()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    ai_provider: str
    openai_api_key: str | None
    chat_model: str
    embedding_model: str
    chroma_path: Path
    chroma_collection: str
    raw_posts_path: Path
    topic_rules_path: Path
    rag_top_k: int
    rag_min_score: float
    crawler_delay_seconds: float
    crawler_timeout_seconds: float
    seboard_api_url: str | None
    seboard_headless: bool
    cors_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    origins = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    )
    return Settings(
        ai_provider=os.getenv("AI_PROVIDER", "auto").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-luna"),
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        chroma_path=_resolve_path(os.getenv("CHROMA_PATH", "./chroma_db")),
        chroma_collection=os.getenv("CHROMA_COLLECTION", "se_mentor_posts"),
        raw_posts_path=_resolve_path(os.getenv("RAW_POSTS_PATH", "./data/raw/posts.json")),
        topic_rules_path=_resolve_path(os.getenv("TOPIC_RULES_PATH", "./data/topic_rules.json")),
        rag_top_k=max(1, int(os.getenv("RAG_TOP_K", "5"))),
        rag_min_score=float(os.getenv("RAG_MIN_SCORE", "0.20")),
        crawler_delay_seconds=max(0.0, float(os.getenv("CRAWLER_DELAY_SECONDS", "1.0"))),
        crawler_timeout_seconds=max(1.0, float(os.getenv("CRAWLER_TIMEOUT_SECONDS", "20.0"))),
        seboard_api_url=os.getenv("SEBOARD_API_URL") or None,
        seboard_headless=_as_bool(os.getenv("SEBOARD_HEADLESS"), default=True),
        cors_origins=origins,
    )
