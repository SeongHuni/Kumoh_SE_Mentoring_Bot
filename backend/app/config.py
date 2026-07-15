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


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name}는 정수여야 합니다.") from exc


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
    embedding_dimensions: int = 1536
    chunk_size: int = 900
    chunk_overlap: int = 150

    def __post_init__(self) -> None:
        if self.ai_provider not in {"auto", "local", "openai"}:
            raise ValueError("AI_PROVIDER는 auto, local, openai 중 하나여야 합니다.")
        if self.embedding_dimensions < 256:
            raise ValueError("EMBEDDING_DIMENSIONS는 256 이상이어야 합니다.")
        if self.chunk_size < 200:
            raise ValueError("CHUNK_SIZE는 200 이상이어야 합니다.")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP은 0 이상 CHUNK_SIZE 미만이어야 합니다.")


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
        rag_min_score=float(os.getenv("RAG_MIN_SCORE", "0.10")),
        crawler_delay_seconds=max(0.0, float(os.getenv("CRAWLER_DELAY_SECONDS", "1.0"))),
        crawler_timeout_seconds=max(1.0, float(os.getenv("CRAWLER_TIMEOUT_SECONDS", "20.0"))),
        seboard_api_url=os.getenv("SEBOARD_API_URL") or None,
        seboard_headless=_as_bool(os.getenv("SEBOARD_HEADLESS"), default=True),
        cors_origins=origins,
        embedding_dimensions=_as_int("EMBEDDING_DIMENSIONS", 1536),
        chunk_size=_as_int("CHUNK_SIZE", 900),
        chunk_overlap=_as_int("CHUNK_OVERLAP", 150),
    )
